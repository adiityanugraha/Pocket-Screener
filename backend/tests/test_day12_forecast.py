"""Day 12 — Probability Forecast inference & API.

confidence_level (murni) diuji dengan probabilitas sintetis; inferensi ONNX &
endpoint diuji dengan model + DB sungguhan (auto-skip bila artefak/DB tak ada).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ml import forecast_model
from app.ml.forecast_model import HORIZONS, confidence_level


# --------------------------------------------------------------------------- #
# Confidence level (murni)
# --------------------------------------------------------------------------- #
def test_confidence_low_near_half() -> None:
    # Semua dekat 0.5 -> jarak kecil -> LOW.
    assert confidence_level([0.50, 0.49, 0.51]) == "LOW"


def test_confidence_high_far_from_half() -> None:
    # Jauh dari 0.5 -> HIGH (avg dist 0.24 >= 0.18).
    assert confidence_level([0.74, 0.74, 0.74]) == "HIGH"


def test_confidence_medium() -> None:
    # avg dist ~0.10 -> MEDIUM (>= 0.07, < 0.18).
    assert confidence_level([0.60, 0.60, 0.60]) == "MEDIUM"


def test_confidence_symmetric_below_half() -> None:
    # Jarak dihitung absolut: 0.26 dari 0.5 -> HIGH meski di bawah 0.5.
    assert confidence_level([0.24, 0.24, 0.24]) == "HIGH"


def test_confidence_empty() -> None:
    assert confidence_level([]) == "LOW"


def test_horizons_constant() -> None:
    assert HORIZONS == (1, 5, 20)


# --------------------------------------------------------------------------- #
# Inferensi ONNX (butuh artefak forecast_*.onnx)
# --------------------------------------------------------------------------- #
def _require_models():
    ml_dir = Path(forecast_model.__file__).resolve().parent
    if not all((ml_dir / f"forecast_{h}d.onnx").exists() for h in HORIZONS):
        pytest.skip("Model forecast_*.onnx belum dilatih.")


def test_predict_from_features_runs() -> None:
    _require_models()
    # Feature vector netral (semua 0) -> harus mengembalikan 3 probabilitas valid.
    fv = [0.0] * 13
    result = forecast_model.predict_from_features(fv)
    for p in (result.prob_1d, result.prob_5d, result.prob_20d):
        assert 0.0 <= p <= 1.0
    assert result.confidence in ("LOW", "MEDIUM", "HIGH")


# --------------------------------------------------------------------------- #
# Endpoint (butuh DB + model)
# --------------------------------------------------------------------------- #
def _client_or_skip():
    from app.db.session import SessionLocal

    if SessionLocal is None:
        pytest.skip("DATABASE_URL tidak diset — lewati test endpoint.")
    _require_models()
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_api_forecast_structure() -> None:
    client = _client_or_skip()
    resp = client.get("/api/forecast/BBCA", params={"refresh": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "BBCA"
    assert set(data["prob"]) == {"1d", "5d", "20d"}
    for key, p in data["prob"].items():
        assert 0.0 <= p <= 1.0
    assert data["confidence"] in ("LOW", "MEDIUM", "HIGH")
    assert "disclaimer" in data and data["disclaimer"]  # disclaimer wajib ada


def test_api_forecast_unknown_ticker_404() -> None:
    client = _client_or_skip()
    assert client.get("/api/forecast/ZZZZ").status_code == 404


def test_api_forecast_persisted_and_cached() -> None:
    client = _client_or_skip()
    first = client.get("/api/forecast/ASII", params={"refresh": True}).json()
    assert first["cached"] is False
    second = client.get("/api/forecast/ASII").json()  # tanpa refresh -> dari cache
    assert second["cached"] is True
    assert second["prob"] == first["prob"]

    # Tersimpan di tabel forecast.
    from sqlalchemy import select

    from app.db.models import Forecast
    from app.db.session import SessionLocal

    db = SessionLocal()
    # Ambil baris terbaru: tabel bisa berisi forecast tanggal-tanggal lama.
    row = db.scalars(
        select(Forecast).where(Forecast.ticker == "ASII").order_by(Forecast.date.desc())
    ).first()
    db.close()
    assert row is not None
    assert row.confidence == first["confidence"]
