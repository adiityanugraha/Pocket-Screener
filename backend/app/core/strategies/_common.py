"""Helper bersama untuk strategi TEKNIKAL (Phase 3 Day 2+).

Moving average dihitung ON-THE-FLY dari bar (bukan kolom DB) - konsisten dengan
cara Phase 2 menghitung price_ma5 di build_screener_input, dan menghindari migrasi
skema market_data (create_all tidak meng-ALTER tabel yang sudah ada).

Konvensi MA: simple_moving_average mengambil `period` nilai TERAKHIR termasuk bar
berjalan (inklusif) - sama dengan price_ma5 Phase 2 sehingga kriteria "Price vs
MA" seragam di seluruh strategi.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core import indicators
from app.core.screener import OhlcvBar


@dataclass(frozen=True)
class TechSnapshot:
    """Snapshot teknikal bar terakhir + akses MA harga/volume sesuai kebutuhan."""

    close: float
    volume: float
    value: float  # turnover hari ini = close * volume
    prev_close: float
    prev_volume: float
    _closes: list[float] = field(repr=False, default_factory=list)
    _volumes: list[float] = field(repr=False, default_factory=list)

    def price_ma(self, period: int) -> float | None:
        return indicators.simple_moving_average(self._closes, period)

    def volume_ma(self, period: int) -> float | None:
        return indicators.simple_moving_average(self._volumes, period)


def build_tech_snapshot(bars: list[OhlcvBar]) -> TechSnapshot | None:
    """Rakit snapshot dari bar harian. None bila < 2 bar (perlu current+previous)."""
    if len(bars) < 2:
        return None

    current = bars[-1]
    previous = bars[-2]
    closes = [bar.close for bar in bars]
    volumes = [float(bar.volume) for bar in bars]

    return TechSnapshot(
        close=current.close,
        volume=float(current.volume),
        value=current.close * float(current.volume),
        prev_close=previous.close,
        prev_volume=float(previous.volume),
        _closes=closes,
        _volumes=volumes,
    )


def volume_ma20(bars: list[OhlcvBar]) -> float | None:
    """Volume MA20 dari bar (None bila < 20 bar). Dipakai strategi fundamental
    yang punya syarat likuiditas minimum."""
    if len(bars) < 20:
        return None
    return indicators.simple_moving_average([float(bar.volume) for bar in bars], 20)


def value_ma20(bars: list[OhlcvBar]) -> float | None:
    """MA20 nilai transaksi harian (close*volume). None bila < 20 bar."""
    if len(bars) < 20:
        return None
    values = [bar.close * float(bar.volume) for bar in bars]
    return indicators.simple_moving_average(values, 20)


# --------------------------------------------------------------------------- #
# Komparator None-safe - kriteria fundamental sering bernilai None (data Yahoo
# tak lengkap). None selalu mengevaluasi ke False (tak bisa dikonfirmasi lolos).
# --------------------------------------------------------------------------- #
def ge(value: float | None, threshold: float) -> bool:
    return value is not None and value >= threshold


def gt(value: float | None, threshold: float) -> bool:
    return value is not None and value > threshold


def lt(value: float | None, threshold: float) -> bool:
    return value is not None and value < threshold
