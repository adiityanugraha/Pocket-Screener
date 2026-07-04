"""Probability Forecast API (Phase 3 Day 12).

GET /api/forecast/{ticker}
  P(return > 0) untuk horizon 1D / 5D / 20D dari 3 model ONNX terkalibrasi
  (app.ml.forecast_model) + confidence level. Disimpan ke tabel forecast &
  di-cache di Redis. SELALU menyertakan disclaimer (alat bantu analisis, bukan
  rekomendasi jual/beli) - sesuai catatan risiko blueprint.

Query params:
  refresh : abaikan cache & hitung ulang (default false)
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.cache import redis_client
from app.db.models import Forecast, MarketData, Stock
from app.db.session import get_db
from app.ml import forecast_model

router = APIRouter(prefix="/api/forecast", tags=["forecast"])

CACHE_KEY = "forecast:{ticker}"

DISCLAIMER = (
    "Probability Forecast adalah alat bantu analisis berbasis model statistik, "
    "BUKAN rekomendasi jual/beli. Akurasi terbatas - gunakan bersama "
    "pertimbangan lain & kelola risiko."
)


class ForecastResponse(BaseModel):
    ticker: str
    name: str | None = None
    sector: str | None = None
    date: str | None = None
    prob: dict[str, float]            # {"1d":.., "5d":.., "20d":..} (sesuai blueprint)
    confidence: str                   # LOW | MEDIUM | HIGH
    disclaimer: str
    cached: bool
    generated_at: str


def _latest_date(db: Session, ticker: str):
    return db.scalar(
        select(MarketData.date)
        .where(MarketData.ticker == ticker)
        .order_by(MarketData.date.desc())
        .limit(1)
    )


def _persist(db: Session, ticker: str, on_date, result: forecast_model.ForecastResult) -> None:
    stmt = pg_insert(Forecast).values(
        date=on_date,
        ticker=ticker,
        prob_1d=result.prob_1d,
        prob_5d=result.prob_5d,
        prob_20d=result.prob_20d,
        confidence=result.confidence,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_forecast_date_ticker",
        set_={
            "prob_1d": stmt.excluded.prob_1d,
            "prob_5d": stmt.excluded.prob_5d,
            "prob_20d": stmt.excluded.prob_20d,
            "confidence": stmt.excluded.confidence,
        },
    )
    db.execute(stmt)
    db.commit()


@router.get("/{ticker}", response_model=ForecastResponse)
def get_forecast(
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

    stock = db.get(Stock, ticker)
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' tidak dikenal.")

    result = forecast_model.predict_ticker(db, ticker)
    if result is None:
        raise HTTPException(
            status_code=422,
            detail=f"Data '{ticker}' belum cukup untuk forecast (< {forecast_model.MIN_BARS} bar).",
        )

    on_date = _latest_date(db, ticker)
    if on_date is not None:
        _persist(db, ticker, on_date, result)

    payload = ForecastResponse(
        ticker=ticker,
        name=stock.name,
        sector=stock.sector,
        date=on_date.isoformat() if on_date else None,
        prob={
            "1d": round(result.prob_1d, 4),
            "5d": round(result.prob_5d, 4),
            "20d": round(result.prob_20d, 4),
        },
        confidence=result.confidence,
        disclaimer=DISCLAIMER,
        cached=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
    ).model_dump()

    redis_client.cache_set_json(cache_key, payload, ttl=redis_client.TTL_RANKING)
    return payload
