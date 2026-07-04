"""Indikator teknikal - port PERSIS dari frontend/src/lib/indicators.ts.

Tujuan utama: hasil identik dengan perhitungan client-side Phase 1 sehingga
feature vector ML (Day 5) & screener konsisten antara browser dan backend.
Implementasi sengaja memakai loop murni (tanpa pandas/numpy) agar setiap angka
mengikuti algoritma TypeScript baris-per-baris:

  - RSI   : Wilder smoothing (seed = SMA gain/loss periode awal)
  - MACD  : EMA(12) - EMA(26); signal = EMA(9) atas nilai MACD non-null; histogram
  - BB    : SMA(20) ± multiplier * population std (deviasi dibagi N, bukan N-1)
  - ATR   : Wilder smoothing atas True Range
  - VWAP  : kumulatif berjalan (typical price * volume) / kumulatif volume

Setiap fungsi seri mengembalikan list sepanjang input; posisi yang belum punya
cukup data berisi None (mirror `null` di TS).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

Series = list[float | None]


class HasOhlc(Protocol):
    """Bar apa pun yang punya field high/low/close/volume (mis. yahoo.Bar)."""

    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class MacdResult:
    macd: Series
    signal: Series
    histogram: Series


@dataclass(frozen=True)
class BollingerBand:
    middle: float | None
    upper: float | None
    lower: float | None


@dataclass(frozen=True)
class VolumeSpike:
    ratio: float | None
    is_spike: bool


# --------------------------------------------------------------------------- #
# Helper internal
# --------------------------------------------------------------------------- #
def _validate_period(period: int) -> None:
    if not isinstance(period, int) or period <= 0:
        raise ValueError("Indicator period must be a positive integer")


def _average(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _null_series(length: int) -> Series:
    return [None] * length


# --------------------------------------------------------------------------- #
# Moving averages
# --------------------------------------------------------------------------- #
def simple_moving_average(values: Sequence[float], period: int) -> float | None:
    """SMA dari `period` nilai TERAKHIR (None bila data kurang)."""
    _validate_period(period)
    if len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / period


def _calculate_ema(values: Sequence[float], period: int) -> Series:
    ema = _null_series(len(values))
    if len(values) < period:
        return ema

    smoothing = 2 / (period + 1)
    previous = _average(values[:period])
    ema[period - 1] = previous

    for index in range(period, len(values)):
        previous = values[index] * smoothing + previous * (1 - smoothing)
        ema[index] = previous

    return ema


def _calculate_nullable_ema(values: Series, period: int) -> Series:
    """EMA atas seri yang mengandung None: None di-skip lalu hasil dipetakan balik
    ke indeks aslinya (sama seperti calculateNullableEma di TS)."""
    ema = _null_series(len(values))
    valid_values: list[float] = []
    valid_indexes: list[int] = []

    for index, value in enumerate(values):
        if value is not None:
            valid_values.append(value)
            valid_indexes.append(index)

    compact_ema = _calculate_ema(valid_values, period)
    for index, value in enumerate(compact_ema):
        ema[valid_indexes[index]] = value

    return ema


# --------------------------------------------------------------------------- #
# RSI
# --------------------------------------------------------------------------- #
def _rsi_value(average_gain: float, average_loss: float) -> float:
    if average_loss == 0:
        return 100.0
    if average_gain == 0:
        return 0.0
    relative_strength = average_gain / average_loss
    return 100 - 100 / (1 + relative_strength)


def calculate_rsi(closes: Sequence[float], period: int = 14) -> Series:
    _validate_period(period)
    rsi = _null_series(len(closes))
    if len(closes) <= period:
        return rsi

    average_gain = 0.0
    average_loss = 0.0
    for index in range(1, period + 1):
        change = closes[index] - closes[index - 1]
        average_gain += max(change, 0.0)
        average_loss += max(-change, 0.0)

    average_gain /= period
    average_loss /= period
    rsi[period] = _rsi_value(average_gain, average_loss)

    for index in range(period + 1, len(closes)):
        change = closes[index] - closes[index - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        average_gain = (average_gain * (period - 1) + gain) / period
        average_loss = (average_loss * (period - 1) + loss) / period
        rsi[index] = _rsi_value(average_gain, average_loss)

    return rsi


# --------------------------------------------------------------------------- #
# MACD
# --------------------------------------------------------------------------- #
def calculate_macd(
    closes: Sequence[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> MacdResult:
    _validate_period(fast_period)
    _validate_period(slow_period)
    _validate_period(signal_period)
    if fast_period >= slow_period:
        raise ValueError("MACD fastPeriod must be lower than slowPeriod")

    fast_ema = _calculate_ema(closes, fast_period)
    slow_ema = _calculate_ema(closes, slow_period)

    macd: Series = []
    for index in range(len(closes)):
        fast = fast_ema[index]
        slow = slow_ema[index]
        macd.append(None if fast is None or slow is None else fast - slow)

    signal = _calculate_nullable_ema(macd, signal_period)

    histogram: Series = []
    for index, value in enumerate(macd):
        signal_value = signal[index]
        histogram.append(
            None if value is None or signal_value is None else value - signal_value
        )

    return MacdResult(macd=macd, signal=signal, histogram=histogram)


# --------------------------------------------------------------------------- #
# Bollinger Bands
# --------------------------------------------------------------------------- #
def calculate_bollinger_bands(
    closes: Sequence[float],
    period: int = 20,
    multiplier: float = 2,
) -> list[BollingerBand]:
    _validate_period(period)

    bands: list[BollingerBand] = []
    for index in range(len(closes)):
        if index + 1 < period:
            bands.append(BollingerBand(middle=None, upper=None, lower=None))
            continue

        window = closes[index + 1 - period : index + 1]
        middle = _average(window)
        standard_deviation = math.sqrt(
            _average([(value - middle) ** 2 for value in window])
        )
        bands.append(
            BollingerBand(
                middle=middle,
                upper=middle + standard_deviation * multiplier,
                lower=middle - standard_deviation * multiplier,
            )
        )

    return bands


# --------------------------------------------------------------------------- #
# ATR & VWAP (butuh OHLC penuh)
# --------------------------------------------------------------------------- #
def calculate_atr(bars: Sequence[HasOhlc], period: int = 14) -> Series:
    _validate_period(period)

    true_ranges: list[float] = []
    for index, bar in enumerate(bars):
        if index == 0:
            true_ranges.append(bar.high - bar.low)
            continue
        previous_close = bars[index - 1].close
        true_ranges.append(
            max(
                bar.high - bar.low,
                abs(bar.high - previous_close),
                abs(bar.low - previous_close),
            )
        )

    atr = _null_series(len(bars))
    if len(true_ranges) < period:
        return atr

    current_atr = _average(true_ranges[:period])
    atr[period - 1] = current_atr

    for index in range(period, len(true_ranges)):
        current_atr = (current_atr * (period - 1) + true_ranges[index]) / period
        atr[index] = current_atr

    return atr


def calculate_vwap(bars: Sequence[HasOhlc]) -> Series:
    cumulative_typical_price_volume = 0.0
    cumulative_volume = 0.0

    vwap = _null_series(len(bars))
    for index, bar in enumerate(bars):
        typical_price = (bar.high + bar.low + bar.close) / 3
        cumulative_typical_price_volume += typical_price * bar.volume
        cumulative_volume += bar.volume
        vwap[index] = (
            None
            if cumulative_volume == 0
            else cumulative_typical_price_volume / cumulative_volume
        )

    return vwap


# --------------------------------------------------------------------------- #
# Volume spike (dipakai screener)
# --------------------------------------------------------------------------- #
def calculate_volume_spike(
    volumes: Sequence[float],
    period: int = 20,
    multiplier: float = 1.5,
) -> list[VolumeSpike]:
    """Rasio volume vs rata-rata `period` hari sebelumnya. Port dari
    calculateVolumeSpike (indicators.ts). Posisi < period -> ratio None."""
    _validate_period(period)

    result: list[VolumeSpike] = []
    for index, volume in enumerate(volumes):
        if index < period:
            result.append(VolumeSpike(ratio=None, is_spike=False))
            continue
        baseline = _average(volumes[index - period : index])
        ratio = None if baseline == 0 else volume / baseline
        result.append(
            VolumeSpike(ratio=ratio, is_spike=ratio is not None and ratio >= multiplier)
        )

    return result
