"""Explainable AI API (Phase 3 Day 10).

GET /api/explain/{ticker}
  Penjelasan manusiawi: confidence (probabilitas model) + bullish factors
  (matched_criteria strategi yang lolos + interpretasi sinyal teknikal) + risk
  factors (sinyal teknikal negatif). Lihat app.core.explain_engine.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.cache import redis_client
from app.core import explain_engine
from app.core import screener as screener_core
from app.core import strategy_screener
from app.db.models import MarketData, Stock
from app.db.session import get_db
from app.ml import inference
from app.ml.features import build_feature_vector

router = APIRouter(prefix="/api/explain", tags=["explain"])

CACHE_KEY = "explain:{ticker}"

# Batasi jumlah faktor rule-based agar penjelasan tetap ringkas.
MAX_MATCHED_FACTORS = 8


class ExplainResponse(BaseModel):
    ticker: str
    name: str | None = None
    sector: str | None = None
    date: str | None = None
    confidence: int
    bullish_factors: list[str]
    risk_factors: list[str]
    passed_strategies: list[str]
    cached: bool
    generated_at: str


def snapshot_from_bars(bars: list[MarketData]) -> explain_engine.ExplainSnapshot | None:
    """Bangun ExplainSnapshot dari bar via indikator screener (perlu >= 6 bar)."""
    inp = screener_core.build_screener_input(bars)
    if inp is None:
        return None

    bb_position = None
    if inp.bb_upper is not None and inp.bb_lower is not None:
        band_range = inp.bb_upper - inp.bb_lower
        if band_range > 0:
            bb_position = (inp.current_close - inp.bb_lower) / band_range

    atr_pct = (inp.atr / inp.current_close) if (inp.atr and inp.current_close) else None
    vwap_ratio = (inp.current_close / inp.vwap - 1) if inp.vwap else None

    return explain_engine.ExplainSnapshot(
        close=inp.current_close,
        rsi=inp.rsi,
        macd=inp.macd,
        macd_signal=inp.macd_signal,
        macd_histogram=inp.macd_histogram,
        bb_position=bb_position,
        atr_pct=atr_pct,
        vwap_ratio=vwap_ratio,
        volume_spike_ratio=inp.volume_spike_ratio,
    )


def predict_up(bars: list[MarketData]) -> float | None:
    """Probabilitas P(naik) dari model ONNX. None bila data kurang / ML gagal."""
    feature_vector = build_feature_vector(bars)
    if feature_vector is None:
        return None
    try:
        return inference.predict_from_features(feature_vector).probability_up
    except Exception:  # noqa: BLE001 - ML opsional; penjelasan tetap jalan
        return None


def collect_matched_factors(results: dict) -> tuple[list[str], list[str]]:
    """Dari hasil strategi: (faktor rule-based, daftar strategi yang lolos)."""
    passed: list[str] = []
    factors: list[str] = []
    for key, result in results.items():
        if result.passed:
            passed.append(key)
            factors.extend(result.matched_criteria)
    return factors, passed


@router.get("/{ticker}", response_model=ExplainResponse)
def get_explain(
    ticker: str,
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict:
    ticker = ticker.strip().upper()
    cache_key = CACHE_KEY.format(ticker=ticker)

    if not refresh:
        cached = redis_client.cache_get_json(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    evaluated = strategy_screener.evaluate_ticker(db, ticker)
    if evaluated is None:
        raise HTTPException(
            status_code=404, detail=f"Tidak ada market_data untuk '{ticker}'."
        )
    bars, _view, results = evaluated

    matched_factors, passed = collect_matched_factors(results)
    snapshot = snapshot_from_bars(bars)
    probability = predict_up(bars)

    explanation = explain_engine.build_explanation(
        snapshot, probability, matched_factors[:MAX_MATCHED_FACTORS]
    )

    stock = db.get(Stock, ticker)
    payload = ExplainResponse(
        ticker=ticker,
        name=stock.name if stock else None,
        sector=stock.sector if stock else None,
        date=bars[-1].date.isoformat(),
        confidence=explanation.confidence,
        bullish_factors=explanation.bullish_factors,
        risk_factors=explanation.risk_factors,
        passed_strategies=passed,
        cached=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
    ).model_dump()

    redis_client.cache_set_json(cache_key, payload, ttl=redis_client.TTL_REPORT)
    return payload
