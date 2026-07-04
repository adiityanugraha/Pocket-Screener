"""Feature engineering ML - port PERSIS dari frontend/src/lib/mlInference.ts
(`buildModelFeatureVector`).

Menghasilkan 13 fitur dalam URUTAN TEPAT yang diharapkan model RandomForest
(lihat model_metrics.json). Karena indikator dasar (RSI/MACD/BB/ATR/VWAP) sudah
merupakan port baris-per-baris dari frontend (app.core.indicators), feature
vector di sini akan identik dengan yang dihitung browser Phase 1 - sehingga
prediksi server-side konsisten dengan client-side.

Aturan penting yang ditiru dari TS:
  - butuh minimal 30 bar (MIN_BARS), else None
  - current = bar terakhir, previous = bar ke-2 dari belakang,
    closeFiveDaysAgo = bar ke-6 dari belakang
  - bila SMA/Bollinger belum tersedia -> None (tidak bisa membentuk fitur)
  - sanitize: nilai non-finite / None dipetakan ke 0.0 (mirror sanitizeFeature)
"""

from __future__ import annotations

import math
from typing import Protocol

from app.core import indicators

MODEL_FEATURE_COLUMNS: tuple[str, ...] = (
    "return_1d",
    "return_5d",
    "ma5_ratio",
    "ma20_ratio",
    "volume_ratio_20",
    "value_log",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_histogram",
    "bb_position",
    "atr_pct",
    "vwap_ratio",
)

# Minimal bar agar fitur valid (sama dgn frontend: bars.length < 30 -> null).
MIN_BARS = 30


class OhlcvBar(Protocol):
    """Bar OHLCV apa pun (yahoo.Bar atau row db.models.MarketData)."""

    open: float
    high: float
    low: float
    close: float
    volume: float


def _sanitize(value: float | None) -> float:
    """None / NaN / inf -> 0.0 (mirror sanitizeFeature di TS)."""
    if value is None:
        return 0.0
    if not math.isfinite(value):
        return 0.0
    return float(value)


def build_feature_vector(bars: list[OhlcvBar]) -> list[float] | None:
    """Bangun vektor 13 fitur dari deret bar (urut kronologis). None bila data
    kurang. Hasil sudah ter-sanitasi dan siap dikirim ke model ONNX."""
    if len(bars) < MIN_BARS:
        return None

    current = bars[-1]
    previous = bars[-2]
    close_five_days_ago = bars[-6]

    closes = [bar.close for bar in bars]
    volumes = [float(bar.volume) for bar in bars]

    ma5 = indicators.simple_moving_average(closes, 5)
    ma20 = indicators.simple_moving_average(closes, 20)
    volume_ma20 = indicators.simple_moving_average(volumes, 20)
    rsi14 = indicators.calculate_rsi(closes, 14)[-1]
    macd = indicators.calculate_macd(closes)
    bollinger = indicators.calculate_bollinger_bands(closes, 20)[-1]
    atr = indicators.calculate_atr(bars, 14)[-1]
    vwap = indicators.calculate_vwap(bars)[-1]

    # Mirror `if (!ma5 || !ma20 || !volumeMa20 || !bollinger)`: nilai 0/None gagal.
    if not ma5 or not ma20 or not volume_ma20 or bollinger.middle is None:
        return None

    band_range = (
        None
        if bollinger.upper is None or bollinger.lower is None
        else bollinger.upper - bollinger.lower
    )

    bb_position = (
        None
        if band_range is None or band_range == 0 or bollinger.lower is None
        else (current.close - bollinger.lower) / band_range
    )

    features: dict[str, float | None] = {
        "return_1d": current.close / previous.close - 1,
        "return_5d": current.close / close_five_days_ago.close - 1,
        "ma5_ratio": current.close / ma5 - 1,
        "ma20_ratio": current.close / ma20 - 1,
        "volume_ratio_20": current.volume / volume_ma20,
        "value_log": math.log1p(current.close * current.volume),
        "rsi_14": rsi14,
        "macd": macd.macd[-1],
        "macd_signal": macd.signal[-1],
        "macd_histogram": macd.histogram[-1],
        "bb_position": bb_position,
        "atr_pct": None if atr is None else atr / current.close,
        "vwap_ratio": None if vwap is None else current.close / vwap - 1,
    }

    return [_sanitize(features[column]) for column in MODEL_FEATURE_COLUMNS]
