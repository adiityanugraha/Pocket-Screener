"""Market Data API - OHLCV + indikator pre-computed, dilayani dari cache Redis.

GET /api/market-data/{ticker}
  Ambil seri harian (open/high/low/close/volume/value + RSI/MACD/BB/ATR/VWAP)
  dari tabel market_data. Indikator sudah dihitung & disimpan saat data pipeline
  (Day 3), jadi endpoint ini hanya membaca - cepat & cocok di-cache.

  Alur: cek Redis (TTL_PRICE) -> bila miss, query PostgreSQL -> cache -> kembalikan.

Query params:
  limit    : ambil N bar terakhir saja (default: seluruh seri tersimpan)
  refresh  : abaikan cache & baca ulang dari DB (default false)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cache import redis_client
from app.db.models import MarketData, Stock
from app.db.session import get_db

router = APIRouter(prefix="/api/market-data", tags=["market-data"])

CACHE_KEY = "market-data:{ticker}:limit={limit}"


# --------------------------------------------------------------------------- #
# Response schema
# --------------------------------------------------------------------------- #
class BarOut(BaseModel):
    date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = None
    value: float | None = None
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    atr: float | None = None
    vwap: float | None = None


class MarketDataResponse(BaseModel):
    ticker: str
    name: str | None = None
    sector: str | None = None
    count: int
    cached: bool
    bars: list[BarOut]


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def _load_bars(db: Session, ticker: str, limit: int | None) -> list[MarketData]:
    """Seluruh bar ticker, urut kronologis. `limit` -> N bar TERAKHIR."""
    rows = list(
        db.scalars(
            select(MarketData)
            .where(MarketData.ticker == ticker)
            .order_by(MarketData.date)
        )
    )
    if limit is not None and limit > 0:
        rows = rows[-limit:]
    return rows


def _bar_to_out(bar: MarketData) -> BarOut:
    return BarOut(
        date=bar.date.isoformat(),
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
        value=bar.value,
        rsi=bar.rsi,
        macd=bar.macd,
        macd_signal=bar.macd_signal,
        macd_histogram=bar.macd_histogram,
        bb_upper=bar.bb_upper,
        bb_middle=bar.bb_middle,
        bb_lower=bar.bb_lower,
        atr=bar.atr,
        vwap=bar.vwap,
    )


@router.get("/{ticker}", response_model=MarketDataResponse)
def get_market_data(
    ticker: str,
    limit: int | None = Query(None, ge=1, le=1000),
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict:
    ticker = ticker.strip().upper()
    cache_key = CACHE_KEY.format(ticker=ticker, limit=limit)

    if not refresh:
        cached = redis_client.cache_get_json(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    bars = _load_bars(db, ticker, limit)
    if not bars:
        raise HTTPException(
            status_code=404,
            detail=f"Tidak ada market_data untuk ticker '{ticker}'.",
        )

    stock = db.get(Stock, ticker)
    result = MarketDataResponse(
        ticker=ticker,
        name=stock.name if stock else None,
        sector=stock.sector if stock else None,
        count=len(bars),
        cached=False,
        bars=[_bar_to_out(bar) for bar in bars],
    ).model_dump()

    redis_client.cache_set_json(cache_key, result, ttl=redis_client.TTL_PRICE)
    return result
