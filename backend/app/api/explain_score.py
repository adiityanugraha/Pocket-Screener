"""Explainable AI 2.0 API (Phase 5 Day 6).

GET /api/explain-score/{ticker}
  Breakdown pembentukan Composite Score per komponen (Technical/Momentum/Volume/
  Volatility/ML) + kontribusi tiap komponen ke skor akhir, dinarasikan LLM.
  Angka dari sistem (engine Composite Score Phase 2); LLM hanya menarasikan.

Cache-only (Redis); tidak ada tabel khusus - explain adalah turunan Composite
Score. Query: refresh (abaikan cache).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai import explain_score
from app.cache import redis_client
from app.db.session import get_db  # noqa: F401 - konsistensi DI (analyze pakai session via tools)

router = APIRouter(prefix="/api/explain-score", tags=["explain-score"])

CACHE_KEY = "explain-score:{ticker}"


class ComponentOut(BaseModel):
    component: str
    label: str
    score: float
    weight: float
    effective_weight: float
    contribution: float


class ExplainScoreResponse(BaseModel):
    ticker: str
    date: str | None = None
    overall_score: float | None = None
    ml_available: bool = True
    breakdown: list[ComponentOut] = []
    summary: str | None = None
    bullish_factors: list[str] = []
    risk_factors: list[str] = []
    ai_generated: bool = False
    note: str | None = None
    disclaimer: str
    cached: bool = False
    generated_at: str | None = None


@router.get("/{ticker}", response_model=ExplainScoreResponse)
def get_explain_score(
    ticker: str,
    refresh: bool = Query(False),
    db: Session = Depends(get_db),  # noqa: ARG001 - tools membuka session sendiri
) -> dict:
    ticker = ticker.strip().upper()
    cache_key = CACHE_KEY.format(ticker=ticker)

    if not refresh:
        cached = redis_client.cache_get_json(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    result = explain_score.explain(ticker)
    if "error" in result and result.get("overall_score") is None:
        raise HTTPException(status_code=404, detail=result["error"])

    note = result.get("note") or result.get("error")
    payload = ExplainScoreResponse(
        ticker=result["ticker"],
        date=result.get("date"),
        overall_score=result.get("overall_score"),
        ml_available=result.get("ml_available", True),
        breakdown=[ComponentOut(**c) for c in result.get("breakdown", [])],
        summary=result.get("summary"),
        bullish_factors=result.get("bullish_factors", []),
        risk_factors=result.get("risk_factors", []),
        ai_generated=result.get("ai_generated", False),
        note=note,
        disclaimer=result.get("disclaimer", ""),
        cached=False,
        generated_at=result.get("generated_at"),
    ).model_dump()

    if payload["ai_generated"]:
        redis_client.cache_set_json(cache_key, payload, ttl=redis_client.TTL_REPORT)
    return payload
