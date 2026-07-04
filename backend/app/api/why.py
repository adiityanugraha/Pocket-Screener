"""Explain Why Selected API (Phase 3 Day 10).

GET /api/why/{ticker}
  Untuk satu saham: strategi apa yang COCOK + alasan spesifiknya. Reasons diambil
  langsung dari matched_criteria tiap strategi (Strategy Registry) sehingga
  OTOMATIS akurat sesuai kriteria yang benar-benar lolos - bukan teks template.
  skipped_criteria juga ditampilkan agar keterbatasan data transparan.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.cache import redis_client
from app.core import strategy_screener
from app.core.strategies import registry
from app.db.models import Stock
from app.db.session import get_db

router = APIRouter(prefix="/api/why", tags=["why"])

CACHE_KEY = "why:{ticker}"


class MatchedStrategyOut(BaseModel):
    key: str
    name: str
    type: str
    reasons: list[str]
    skipped: list[str]


class WhyResponse(BaseModel):
    ticker: str
    name: str | None = None
    sector: str | None = None
    date: str | None = None
    matched: list[str]                 # nama strategi yang cocok (blueprint)
    matched_strategies: list[MatchedStrategyOut]
    reasons: list[str]                 # gabungan semua alasan (blueprint)
    cached: bool
    generated_at: str


@router.get("/{ticker}", response_model=WhyResponse)
def get_why(
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
    meta = {s.key: s for s in registry.all_strategies()}

    matched_strategies: list[MatchedStrategyOut] = []
    matched_names: list[str] = []
    all_reasons: list[str] = []
    for key, result in results.items():
        if not result.passed:
            continue
        strategy = meta[key]
        matched_names.append(strategy.name)
        all_reasons.extend(result.matched_criteria)
        matched_strategies.append(
            MatchedStrategyOut(
                key=key,
                name=strategy.name,
                type=strategy.type.value,
                reasons=result.matched_criteria,
                skipped=result.skipped_criteria,
            )
        )

    stock = db.get(Stock, ticker)
    payload = WhyResponse(
        ticker=ticker,
        name=stock.name if stock else None,
        sector=stock.sector if stock else None,
        date=bars[-1].date.isoformat(),
        matched=matched_names,
        matched_strategies=matched_strategies,
        reasons=all_reasons,
        cached=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
    ).model_dump()

    redis_client.cache_set_json(cache_key, payload, ttl=redis_client.TTL_REPORT)
    return payload
