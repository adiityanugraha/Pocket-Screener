"""Composite Score Engine - gabungkan banyak indikator jadi SATU skor 0-100.

Sesuai blueprint Phase 2 (Composite Score Engine), bobot komponen:

  | Komponen            | Bobot |
  |---------------------|-------|
  | Technical Strength  | 30%   |
  | Momentum            | 25%   |
  | Volume Activity     | 20%   |
  | Volatility          | 10%   |
  | ML Prediction       | 15%   |

Pendekatan: **heuristik absolut**. Tiap komponen dipetakan ke 0-100 lewat
ambang tetap yang masuk akal (deterministik, tidak bergantung saham lain),
lalu dijumlah berbobot menjadi Overall Score 0-100.

Modul ini MURNI (tanpa DB/ML/cache) agar mudah diuji. API (ranking.py) yang
merakit input dari market_data + prediksi ML.
"""

from __future__ import annotations

from dataclasses import dataclass

# Bobot komponen (jumlah = 1.0).
WEIGHT_TECHNICAL = 0.30
WEIGHT_MOMENTUM = 0.25
WEIGHT_VOLUME = 0.20
WEIGHT_VOLATILITY = 0.10
WEIGHT_ML = 0.15


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class CompositeInput:
    """Snapshot satu saham (bar terakhir) untuk perhitungan composite score."""

    rsi: float | None
    macd_histogram: float | None
    bb_position: float | None  # (close - lower) / (upper - lower), 0..1
    return_1d: float | None
    return_5d: float | None
    volume_ratio: float | None  # volume vs baseline (spike ratio / vs previous)
    atr_pct: float | None  # atr / close
    probability_up: float | None  # 0..1 dari model ONNX (None bila ML tak tersedia)


@dataclass(frozen=True)
class CompositeResult:
    overall: float  # 0-100
    technical: float
    momentum: float
    volume: float
    volatility: float
    ml: float | None  # None bila ML tidak dipakai (bobotnya didistribusi ulang)


# --------------------------------------------------------------------------- #
# Skor per komponen (semua mengembalikan 0-100)
# --------------------------------------------------------------------------- #
def technical_score(
    rsi: float | None,
    macd_histogram: float | None,
    bb_position: float | None,
) -> float:
    """Kekuatan teknikal: rata-rata sub-sinyal RSI, MACD, posisi Bollinger.

    - RSI : ideal di ~60 (sehat bullish). Makin jauh dari 60 makin turun.
    - MACD: histogram > 0 (bullish) bernilai tinggi; = 0 netral; < 0 lemah.
    - BB  : posisi ~0.70 ideal (kuat tapi belum overbought ekstrem).
    """
    parts: list[float] = []

    if rsi is not None:
        parts.append(_clamp(100 - abs(rsi - 60) * 2.5))
    if macd_histogram is not None:
        parts.append(80.0 if macd_histogram > 0 else 50.0 if macd_histogram == 0 else 20.0)
    if bb_position is not None:
        parts.append(_clamp(100 - abs(bb_position - 0.70) * 150))

    if not parts:
        return 50.0  # netral bila tak ada data
    return sum(parts) / len(parts)


def momentum_score(return_1d: float | None, return_5d: float | None) -> float:
    """Momentum harga: gabungan return 1 hari & 5 hari (dipetakan ke 0-100).

    Skala: +5% harian -> 100, -5% -> 0 (50 = datar). 5-hari memakai skala
    lebih longgar (~±12.5% -> rentang penuh). Bobot 60% harian, 40% 5-hari.
    """
    parts: list[tuple[float, float]] = []  # (score, weight)

    if return_1d is not None:
        parts.append((_clamp(50 + return_1d * 1000), 0.6))
    if return_5d is not None:
        parts.append((_clamp(50 + return_5d * 400), 0.4))

    if not parts:
        return 50.0
    total_weight = sum(weight for _, weight in parts)
    return sum(score * weight for score, weight in parts) / total_weight


def volume_score(volume_ratio: float | None) -> float:
    """Aktivitas volume: rasio volume vs baseline.

    ratio 1.0 (normal) -> 50, 2.0 -> 80, ~2.67 -> 100, mendekati 0 -> 20.
    """
    if volume_ratio is None:
        return 50.0
    return _clamp(20 + volume_ratio * 30)


def volatility_score(atr_pct: float | None) -> float:
    """Volatilitas: ATR% rendah = lebih stabil = skor tinggi.

    <=2% -> 100 (stabil), linear turun, >=10% -> 0 (sangat volatil/berisiko).
    """
    if atr_pct is None:
        return 50.0
    return _clamp(100 - (atr_pct - 0.02) * 1250)


def ml_score(probability_up: float | None) -> float | None:
    """Prediksi ML: probabilitas naik (0..1) -> 0-100. None bila tak tersedia."""
    if probability_up is None:
        return None
    return _clamp(probability_up * 100)


# --------------------------------------------------------------------------- #
# Agregasi
# --------------------------------------------------------------------------- #
def compute_composite(inp: CompositeInput) -> CompositeResult:
    """Hitung Overall Score 0-100 dari kelima komponen.

    Bila ML tidak tersedia (probability_up None), bobot ML (15%) didistribusi
    ulang secara proporsional ke empat komponen lain agar total tetap 100.
    """
    technical = technical_score(inp.rsi, inp.macd_histogram, inp.bb_position)
    momentum = momentum_score(inp.return_1d, inp.return_5d)
    volume = volume_score(inp.volume_ratio)
    volatility = volatility_score(inp.atr_pct)
    ml = ml_score(inp.probability_up)

    if ml is None:
        # Renormalisasi 4 bobot (jumlah 0.85) menjadi 1.0.
        base = WEIGHT_TECHNICAL + WEIGHT_MOMENTUM + WEIGHT_VOLUME + WEIGHT_VOLATILITY
        overall = (
            technical * WEIGHT_TECHNICAL
            + momentum * WEIGHT_MOMENTUM
            + volume * WEIGHT_VOLUME
            + volatility * WEIGHT_VOLATILITY
        ) / base
    else:
        overall = (
            technical * WEIGHT_TECHNICAL
            + momentum * WEIGHT_MOMENTUM
            + volume * WEIGHT_VOLUME
            + volatility * WEIGHT_VOLATILITY
            + ml * WEIGHT_ML
        )

    return CompositeResult(
        overall=round(_clamp(overall), 2),
        technical=round(technical, 2),
        momentum=round(momentum, 2),
        volume=round(volume, 2),
        volatility=round(volatility, 2),
        ml=None if ml is None else round(ml, 2),
    )
