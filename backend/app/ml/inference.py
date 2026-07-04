"""Inferensi ML server-side - pengganti onnxruntime-web Phase 1.

Memuat model RandomForest (model.onnx) dengan onnxruntime (CPU) dan menjalankan
prediksi probabilitas kenaikan harga keesokan hari (target
`next_day_close_return_positive`). Model & feature engineering identik dengan
client-side, jadi hasilnya konsisten dengan Phase 1.

Kontrak model (lihat introspeksi + model_metrics.json):
  input  : "float_input"   float32 [N, 13]
  outputs: "label"         int64   [N]      -> 0/1
           "probabilities" float32 [N, 2]   -> [prob_turun, prob_naik]

Sesi di-load lazy & dicache (thread-safe) agar file 16 MB hanya dibaca sekali.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime as ort
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import MarketData
from app.ml.features import MIN_BARS, build_feature_vector

# Default: model yang dibundel di backend (self-contained untuk deployment).
_DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "model.onnx"

# Jumlah bar yang diambil dari market_data untuk membentuk fitur. Cukup banyak
# agar indikator slow (MACD EMA-26, dst.) sudah "matang" di bar terakhir.
LOOKBACK_BARS = 60

_session: ort.InferenceSession | None = None
_session_lock = threading.Lock()


@dataclass(frozen=True)
class Prediction:
    """Hasil prediksi satu sampel."""

    label: int
    probability_down: float
    probability_up: float


def _model_path() -> Path:
    override = get_settings().onnx_model_path
    return Path(override) if override else _DEFAULT_MODEL_PATH


def get_session() -> ort.InferenceSession:
    """Kembalikan InferenceSession singleton (lazy, thread-safe)."""
    global _session
    if _session is not None:
        return _session
    with _session_lock:
        if _session is None:
            path = _model_path()
            if not path.exists():
                raise FileNotFoundError(f"Model ONNX tidak ditemukan: {path}")
            _session = ort.InferenceSession(
                str(path), providers=["CPUExecutionProvider"]
            )
    return _session


def predict_from_features(feature_vector: list[float]) -> Prediction:
    """Jalankan model atas satu feature vector (panjang 13)."""
    session = get_session()
    input_name = session.get_inputs()[0].name
    tensor = np.asarray([feature_vector], dtype=np.float32)
    label_out, proba_out = session.run(None, {input_name: tensor})

    probabilities = np.asarray(proba_out)[0]
    prob_down = float(probabilities[0])
    prob_up = float(probabilities[1]) if probabilities.shape[0] > 1 else 0.0
    return Prediction(
        label=int(np.asarray(label_out).reshape(-1)[0]),
        probability_down=prob_down,
        probability_up=prob_up,
    )


def _load_recent_bars(db: Session, ticker: str, limit: int = LOOKBACK_BARS) -> list[MarketData]:
    """Ambil `limit` bar terakhir dari market_data, urut kronologis (lama -> baru)."""
    rows = list(
        db.scalars(
            select(MarketData)
            .where(MarketData.ticker == ticker)
            .order_by(MarketData.date.desc())
            .limit(limit)
        )
    )
    rows.reverse()
    return rows


def predict_ticker(db: Session, ticker: str) -> Prediction | None:
    """Prediksi probabilitas untuk satu ticker dari data market_data terbaru.

    None bila data bar tidak cukup (< MIN_BARS) untuk membentuk fitur.
    """
    bars = _load_recent_bars(db, ticker)
    if len(bars) < MIN_BARS:
        return None
    feature_vector = build_feature_vector(bars)
    if feature_vector is None:
        return None
    return predict_from_features(feature_vector)
