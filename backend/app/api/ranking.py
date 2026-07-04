"""Ranking API - Composite Score Engine (Day 7).

GET /api/ranking
  Untuk tiap saham di universe: rakit indikator bar terakhir (dari market_data)
  + prediksi ML -> hitung Overall Score 0-100 (app.core.composite_score) ->
  urutkan menurun -> kembalikan top-N. Hasil di-cache di Redis (TTL_RANKING).

Query params:
  limit    : jumlah saham teratas (default 20)
  use_ml   : sertakan komponen ML 15% (default true)
  refresh  : abaikan cache & hitung ulang (default false)
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cache import redis_client
from app.core import composite_score as cs
from app.core import indicators
from app.core.instruments import is_index
from app.db.models import MarketData, Stock
from app.db.queries import load_recent_bars_by_ticker
from app.db.session import get_db
from app.ml import inference
from app.ml.features import build_feature_vector

router = APIRouter(prefix="/api/ranking", tags=["ranking"])

CACHE_KEY = "ranking:limit={limit}:ml={ml}"

# Minimal bar untuk menghitung return 5-hari + indikator dasar.
MIN_BARS = 6

# Composite hanya butuh bar-bar terakhir (indikator pre-computed + return 5-hari +
# baseline volume 20-hari + fitur ML). 90 hari kalender (~62 bar bursa) jauh lebih
# dari cukup, tapi mencegah memuat seluruh histori 10 tahun ke memori.
RANKING_LOOKBACK_DAYS = 90


# --------------------------------------------------------------------------- #
# Response schema
# --------------------------------------------------------------------------- #
class BreakdownOut(BaseModel):
    technical: float
    momentum: float
    volume: float
    volatility: float
    ml: float | None = None


class RankingItemOut(BaseModel):
    rank: int
    ticker: str
    name: str | None = None
    sector: str | None = None
    date: str
    close: float | None = None
    overall_score: float
    breakdown: BreakdownOut


class RankingResponse(BaseModel):
    generated_at: str
    universe: int
    ranked: int
    use_ml: bool
    cached: bool
    items: list[RankingItemOut]


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def _load_bars_by_ticker(db: Session) -> dict[str, list[MarketData]]:
    return load_recent_bars_by_ticker(db, lookback_days=RANKING_LOOKBACK_DAYS)


def _predict_up(bars: list[MarketData]) -> float | None:
    feature_vector = build_feature_vector(bars)
    if feature_vector is None:
        return None
    try:
        return inference.predict_from_features(feature_vector).probability_up
    except Exception:  # noqa: BLE001 - ML opsional; ranking tetap jalan tanpa ML
        return None


def build_composite_input(
    bars: list[MarketData], probability_up: float | None
) -> cs.CompositeInput:
    """Rakit CompositeInput dari indikator bar terakhir (pre-computed di Day 3)."""
    latest = bars[-1]
    previous = bars[-2]
    close = latest.close

    return_1d = (close / previous.close - 1) if close and previous.close else None
    close_5d_ago = bars[-6].close if len(bars) >= 6 else None
    return_5d = (close / close_5d_ago - 1) if close and close_5d_ago else None

    bb_position: float | None = None
    if latest.bb_upper is not None and latest.bb_lower is not None and close is not None:
        band_range = latest.bb_upper - latest.bb_lower
        if band_range:
            bb_position = (close - latest.bb_lower) / band_range

    # Rasio volume vs baseline 20-hari; fallback ke volume hari sebelumnya.
    volumes = [float(bar.volume or 0) for bar in bars]
    volume_ratio = indicators.calculate_volume_spike(volumes)[-1].ratio
    if volume_ratio is None and previous.volume:
        volume_ratio = float(latest.volume or 0) / float(previous.volume)

    atr_pct = (latest.atr / close) if (latest.atr is not None and close) else None

    return cs.CompositeInput(
        rsi=latest.rsi,
        macd_histogram=latest.macd_histogram,
        bb_position=bb_position,
        return_1d=return_1d,
        return_5d=return_5d,
        volume_ratio=volume_ratio,
        atr_pct=atr_pct,
        probability_up=probability_up,
    )


def run_ranking(db: Session, limit: int, use_ml: bool) -> dict:
    bars_by_ticker = _load_bars_by_ticker(db)
    stock_map = {stock.ticker: stock for stock in db.scalars(select(Stock))}

    scored: list[dict] = []
    for ticker, bars in bars_by_ticker.items():
        if is_index(ticker):  # indeks = konteks, bukan kandidat ranking
            continue
        if len(bars) < MIN_BARS:
            continue
        probability_up = _predict_up(bars) if use_ml else None
        inp = build_composite_input(bars, probability_up)
        result = cs.compute_composite(inp)
        stock = stock_map.get(ticker)
        latest = bars[-1]
        scored.append(
            {
                "ticker": ticker,
                "name": stock.name if stock else None,
                "sector": stock.sector if stock else None,
                "date": latest.date.isoformat(),
                "close": latest.close,
                "overall_score": result.overall,
                "breakdown": {
                    "technical": result.technical,
                    "momentum": result.momentum,
                    "volume": result.volume,
                    "volatility": result.volatility,
                    "ml": result.ml,
                },
            }
        )

    scored.sort(key=lambda item: item["overall_score"], reverse=True)
    top = scored[:limit]
    for index, item in enumerate(top, start=1):
        item["rank"] = index

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universe": len(bars_by_ticker),
        "ranked": len(scored),
        "use_ml": use_ml,
        "cached": False,
        "items": top,
    }


@router.get("", response_model=RankingResponse)
def get_ranking(
    limit: int = Query(20, ge=1, le=80),
    use_ml: bool = Query(True),
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict:
    cache_key = CACHE_KEY.format(limit=limit, ml=use_ml)

    if not refresh:
        cached = redis_client.cache_get_json(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    result = run_ranking(db, limit=limit, use_ml=use_ml)
    redis_client.cache_set_json(cache_key, result, ttl=redis_client.TTL_RANKING)
    return result
