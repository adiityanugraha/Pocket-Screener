"""Inferensi Probability Forecast multi-horizon (Phase 3 Day 12).

Memuat 3 model ONNX terkalibrasi (forecast_1d/5d/20d.onnx, hasil Day 11) dan
memprediksi P(return > 0) untuk horizon 1D / 5D / 20D dari market_data terbaru.
Konsisten dgn Phase 2: feature engineering & LOOKBACK_BARS sama dengan model
Composite Score, sehingga distribusi fitur identik dengan saat training.

Confidence level (LOW/MEDIUM/HIGH) diturunkan dari KALIBRASI: rata-rata jarak
probabilitas dari 50% (makin jauh dari acak -> makin yakin). Ambang dibaca dari
forecast_metrics.json (confidence_thresholds), dengan fallback default.

Sesi ONNX di-load lazy & dicache (thread-safe) - tiap file ~2.5 MB.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime as ort
from sqlalchemy.orm import Session

from app.ml.features import MIN_BARS, build_feature_vector
from app.ml.inference import LOOKBACK_BARS, _load_recent_bars

HORIZONS = (1, 5, 20)
ML_DIR = Path(__file__).resolve().parent
METRICS_PATH = ML_DIR / "forecast_metrics.json"

_DEFAULT_THRESHOLDS = {"medium": 0.07, "high": 0.18}

_sessions: dict[int, ort.InferenceSession] = {}
_sessions_lock = threading.Lock()
_thresholds: dict[str, float] | None = None


@dataclass(frozen=True)
class ForecastResult:
    prob_1d: float
    prob_5d: float
    prob_20d: float
    confidence: str  # LOW | MEDIUM | HIGH

    def as_prob_dict(self) -> dict[str, float]:
        return {"1d": self.prob_1d, "5d": self.prob_5d, "20d": self.prob_20d}


def _model_path(horizon: int) -> Path:
    return ML_DIR / f"forecast_{horizon}d.onnx"


def _get_session(horizon: int) -> ort.InferenceSession:
    """Sesi ONNX untuk satu horizon (lazy, thread-safe)."""
    session = _sessions.get(horizon)
    if session is not None:
        return session
    with _sessions_lock:
        session = _sessions.get(horizon)
        if session is None:
            path = _model_path(horizon)
            if not path.exists():
                raise FileNotFoundError(
                    f"Model forecast tidak ditemukan: {path}. "
                    "Jalankan `python -m app.ml.train_forecast` dulu."
                )
            session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
            _sessions[horizon] = session
    return session


def _thresholds_config() -> dict[str, float]:
    """Ambang confidence dari forecast_metrics.json (fallback default)."""
    global _thresholds
    if _thresholds is not None:
        return _thresholds
    thresholds = dict(_DEFAULT_THRESHOLDS)
    try:
        metrics = json.loads(METRICS_PATH.read_text())
        loaded = metrics.get("confidence_thresholds") or {}
        thresholds.update({k: float(v) for k, v in loaded.items() if k in thresholds})
    except (OSError, ValueError):
        pass
    _thresholds = thresholds
    return thresholds


def _prob_up(horizon: int, feature_vector: list[float]) -> float:
    session = _get_session(horizon)
    input_name = session.get_inputs()[0].name
    tensor = np.asarray([feature_vector], dtype=np.float32)
    _label, proba = session.run(None, {input_name: tensor})
    probabilities = np.asarray(proba)[0]
    return float(probabilities[1]) if probabilities.shape[0] > 1 else float(probabilities[0])


def confidence_level(probabilities: list[float]) -> str:
    """LOW/MEDIUM/HIGH dari rata-rata jarak |p - 0.5| antar horizon."""
    if not probabilities:
        return "LOW"
    avg_distance = sum(abs(p - 0.5) for p in probabilities) / len(probabilities)
    thresholds = _thresholds_config()
    if avg_distance >= thresholds["high"]:
        return "HIGH"
    if avg_distance >= thresholds["medium"]:
        return "MEDIUM"
    return "LOW"


def predict_from_features(feature_vector: list[float]) -> ForecastResult:
    """Jalankan ketiga model atas satu feature vector (panjang 13)."""
    probs = [_prob_up(h, feature_vector) for h in HORIZONS]
    return ForecastResult(
        prob_1d=probs[0],
        prob_5d=probs[1],
        prob_20d=probs[2],
        confidence=confidence_level(probs),
    )


def predict_ticker(db: Session, ticker: str) -> ForecastResult | None:
    """Forecast untuk satu ticker dari market_data terbaru. None bila data kurang."""
    bars = _load_recent_bars(db, ticker, limit=LOOKBACK_BARS)
    if len(bars) < MIN_BARS:
        return None
    feature_vector = build_feature_vector(bars)
    if feature_vector is None:
        return None
    return predict_from_features(feature_vector)
