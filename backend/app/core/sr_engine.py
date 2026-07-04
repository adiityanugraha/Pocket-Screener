"""Support & Resistance Engine - deteksi area support/resistance otomatis.

Sesuai blueprint Phase 2 (Support & Resistance Engine), tiga metode digabung:

  - Swing High / Low : titik balik lokal (high > k bar kiri-kanan, low < k bar).
  - Pivot Point      : pivot lantai klasik PP=(H+L+C)/3 + R1/R2/S1/S2 dari bar terakhir.
  - ATR Band         : pita dinamis di sekitar harga (close ± mult*ATR).

Hasil disintesis menjadi:
  - Support Level    : level terdekat DI BAWAH harga (dari swing low / pivot S / ATR bawah).
  - Resistance Level : level terdekat DI ATAS harga (dari swing high / pivot R / ATR atas).
  - Breakout Zone    : pita tepat di atas resistance; harga menembusnya = sinyal breakout.

Modul ini MURNI (tanpa DB/cache). API (support_resistance.py) yang merakit input
dari market_data dan menyimpan hasil ke Redis (sering diakses).
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_SWING_WINDOW = 2  # k bar kiri & kanan untuk konfirmasi swing
DEFAULT_ATR_MULT = 1.0  # lebar ATR Band & breakout zone


@dataclass(frozen=True)
class Zone:
    lower: float
    upper: float


@dataclass(frozen=True)
class PivotLevels:
    pivot: float
    r1: float
    r2: float
    s1: float
    s2: float


@dataclass(frozen=True)
class SRInput:
    highs: list[float]
    lows: list[float]
    closes: list[float]
    atr: float | None  # ATR absolut bar terakhir (pre-computed Day 3)


@dataclass(frozen=True)
class SRResult:
    current: float
    support: float | None
    resistance: float | None
    breakout_zone: Zone | None
    pivot: PivotLevels
    swing_high: float | None  # swing high terdekat di atas harga
    swing_low: float | None  # swing low terdekat di bawah harga
    atr_band: Zone | None


# --------------------------------------------------------------------------- #
# Metode dasar
# --------------------------------------------------------------------------- #
def find_swing_points(
    highs: list[float], lows: list[float], window: int = DEFAULT_SWING_WINDOW
) -> tuple[list[float], list[float]]:
    """Swing high/low fractal: titik yang menjadi ekstrem unik dalam jendela ±window.

    `window` bar terakhir tak bisa dikonfirmasi (butuh bar di kanan) - sesuai
    sifat fractal. Mengembalikan (swing_highs, swing_lows) urut kronologis.
    """
    swing_highs: list[float] = []
    swing_lows: list[float] = []
    n = len(highs)
    for i in range(window, n - window):
        win_high = highs[i - window : i + window + 1]
        win_low = lows[i - window : i + window + 1]
        if highs[i] == max(win_high) and win_high.count(highs[i]) == 1:
            swing_highs.append(highs[i])
        if lows[i] == min(win_low) and win_low.count(lows[i]) == 1:
            swing_lows.append(lows[i])
    return swing_highs, swing_lows


def pivot_levels(high: float, low: float, close: float) -> PivotLevels:
    """Pivot lantai klasik dari satu bar (biasanya bar/periode terakhir)."""
    pivot = (high + low + close) / 3
    span = high - low
    return PivotLevels(
        pivot=pivot,
        r1=2 * pivot - low,
        r2=pivot + span,
        s1=2 * pivot - high,
        s2=pivot - span,
    )


def _round(value: float, ndigits: int = 2) -> float:
    return round(value, ndigits)


# --------------------------------------------------------------------------- #
# Sintesis
# --------------------------------------------------------------------------- #
def compute_sr(
    inp: SRInput,
    swing_window: int = DEFAULT_SWING_WINDOW,
    atr_mult: float = DEFAULT_ATR_MULT,
) -> SRResult:
    """Gabungkan swing, pivot, & ATR band jadi support/resistance + breakout zone."""
    current = inp.closes[-1]
    last_high = inp.highs[-1]
    last_low = inp.lows[-1]

    swing_highs, swing_lows = find_swing_points(inp.highs, inp.lows, swing_window)
    pivots = pivot_levels(last_high, last_low, current)

    atr_band: Zone | None = None
    if inp.atr is not None:
        atr_band = Zone(
            lower=_round(current - atr_mult * inp.atr),
            upper=_round(current + atr_mult * inp.atr),
        )

    # Kandidat resistance: semua level DI ATAS harga -> ambil yang terdekat.
    res_candidates = [h for h in swing_highs if h > current]
    res_candidates += [p for p in (pivots.r1, pivots.r2) if p > current]
    if atr_band is not None and atr_band.upper > current:
        res_candidates.append(atr_band.upper)
    resistance = min(res_candidates) if res_candidates else None

    # Kandidat support: semua level DI BAWAH harga -> ambil yang terdekat.
    sup_candidates = [low for low in swing_lows if low < current]
    sup_candidates += [p for p in (pivots.s1, pivots.s2) if p < current]
    if atr_band is not None and atr_band.lower < current:
        sup_candidates.append(atr_band.lower)
    support = max(sup_candidates) if sup_candidates else None

    # Swing terdekat (untuk transparansi metode).
    swing_high_near = min((h for h in swing_highs if h > current), default=None)
    swing_low_near = max((low for low in swing_lows if low < current), default=None)

    # Breakout zone: pita tepat di atas resistance (lebar = ATR, fallback 1% harga).
    breakout_zone: Zone | None = None
    if resistance is not None:
        width = inp.atr * atr_mult if inp.atr is not None else resistance * 0.01
        breakout_zone = Zone(lower=_round(resistance), upper=_round(resistance + width))

    return SRResult(
        current=_round(current),
        support=None if support is None else _round(support),
        resistance=None if resistance is None else _round(resistance),
        breakout_zone=breakout_zone,
        pivot=PivotLevels(
            pivot=_round(pivots.pivot),
            r1=_round(pivots.r1),
            r2=_round(pivots.r2),
            s1=_round(pivots.s1),
            s2=_round(pivots.s2),
        ),
        swing_high=None if swing_high_near is None else _round(swing_high_near),
        swing_low=None if swing_low_near is None else _round(swing_low_near),
        atr_band=atr_band,
    )
