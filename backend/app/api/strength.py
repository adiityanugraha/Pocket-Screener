"""Screener Strength Score API (Phase 3 Day 9).

GET /api/strength/{ticker}
  Gabungkan strategi yang lolos saham (dari strategy_results, tanggal terbaru
  ticker ybs) menjadi skor 0-100 berbobot (app.core.strength_engine). Disimpan
  ke tabel strength_score & di-cache di Redis.

Query params:
  technical_weight   : bobot strategi teknikal (default 1.0)
  fundamental_weight : bobot strategi fundamental (default 1.5)
  full_points        : poin untuk mencapai 100 (default 6.0)
  refresh            : abaikan cache & hitung ulang (default false)
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.cache import redis_client
from app.core import strength_engine
from app.core.strategies import registry
from app.db.models import Stock, StrategyResultRow, StrengthScore
from app.db.session import get_db

router = APIRouter(prefix="/api/strength", tags=["strength"])

CACHE_KEY = "strength:{ticker}:tw={tw}:fw={fw}:fp={fp}"


class ComponentOut(BaseModel):
    strategy: str
    type: str
    weight: float


class StrengthResponse(BaseModel):
    ticker: str
    name: str | None = None
    sector: str | None = None
    date: str | None = None
    strength: int
    points: float
    max_points: float
    passed_strategies: list[str]
    breakdown: list[ComponentOut]
    cached: bool
    generated_at: str


def _strategy_types() -> dict[str, str]:
    return {s.key: s.type.value for s in registry.all_strategies()}


def ticker_latest_date(db: Session, ticker: str) -> date_cls | None:
    """Tanggal strategy_results TERBARU untuk ticker ini (bukan global) - hindari
    artefak saham yang bar terakhirnya tertinggal sehari."""
    return db.scalar(
        select(func.max(StrategyResultRow.date)).where(StrategyResultRow.ticker == ticker)
    )


def passed_strategies(db: Session, ticker: str, on_date: date_cls) -> list[str]:
    rows = db.scalars(
        select(StrategyResultRow.strategy).where(
            StrategyResultRow.ticker == ticker,
            StrategyResultRow.date == on_date,
            StrategyResultRow.passed.is_(True),
        )
    )
    return list(rows)


def compute_for_ticker(
    db: Session,
    ticker: str,
    weights: dict[str, float],
    full_points: float,
    persist: bool = True,
) -> tuple[strength_engine.StrengthResult, date_cls | None]:
    """Hitung Strength Score satu ticker dari strategy_results + simpan."""
    on_date = ticker_latest_date(db, ticker)
    types = _strategy_types()
    passed_keys = passed_strategies(db, ticker, on_date) if on_date else []
    passed = [(key, types.get(key, "technical")) for key in passed_keys]

    result = strength_engine.compute_strength(
        ticker, passed, weights=weights, full_points=full_points
    )

    if persist and on_date is not None:
        stmt = pg_insert(StrengthScore).values(
            date=on_date,
            ticker=ticker,
            passed_strategies=result.passed_strategies,
            strength=result.strength,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_strength_date_ticker",
            set_={
                "passed_strategies": stmt.excluded.passed_strategies,
                "strength": stmt.excluded.strength,
            },
        )
        db.execute(stmt)
        db.commit()

    return result, on_date


@router.get("/{ticker}", response_model=StrengthResponse)
def get_strength(
    ticker: str,
    technical_weight: float = Query(1.0, ge=0),
    fundamental_weight: float = Query(1.5, ge=0),
    full_points: float = Query(6.0, gt=0),
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict:
    ticker = ticker.strip().upper()
    cache_key = CACHE_KEY.format(
        ticker=ticker, tw=technical_weight, fw=fundamental_weight, fp=full_points
    )

    if not refresh:
        cached = redis_client.cache_get_json(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    stock = db.get(Stock, ticker)
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' tidak dikenal.")

    weights = {"technical": technical_weight, "fundamental": fundamental_weight}
    result, on_date = compute_for_ticker(db, ticker, weights, full_points)

    payload = StrengthResponse(
        ticker=ticker,
        name=stock.name,
        sector=stock.sector,
        date=on_date.isoformat() if on_date else None,
        strength=result.strength,
        points=result.points,
        max_points=result.max_points,
        passed_strategies=result.passed_strategies,
        breakdown=[
            ComponentOut(strategy=c.strategy, type=c.type, weight=c.weight)
            for c in result.breakdown
        ],
        cached=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
    ).model_dump()

    redis_client.cache_set_json(cache_key, payload, ttl=redis_client.TTL_RANKING)
    return payload
