"""AI Stock Report API (Day 8).

GET /api/stock-report/{ticker}
  Rakit indikator bar terakhir (dari market_data) + prediksi ML -> hasilkan
  laporan analisis (Bullish/Bearish summary, bullish factors, risk factors,
  confidence score) via app.core.ai_report. Hasil di-cache di Redis (TTL_REPORT).

Query params:
  use_ml   : sertakan komponen ML pada confidence & faktor (default true)
  refresh  : abaikan cache & hitung ulang (default false)
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cache import redis_client
from app.core import ai_report
from app.core import indicators
from app.db.models import MarketData, Stock
from app.db.session import get_db
from app.ml import inference
from app.ml.features import build_feature_vector

router = APIRouter(prefix="/api/stock-report", tags=["stock-report"])

CACHE_KEY = "stock-report:{ticker}:ml={ml}"

# Minimal bar untuk return 5-hari + indikator dasar (selaras /api/ranking).
MIN_BARS = 6


# --------------------------------------------------------------------------- #
# Response schema
# --------------------------------------------------------------------------- #
class StockReportResponse(BaseModel):
    ticker: str
    name: str | None = None
    sector: str | None = None
    date: str
    close: float | None = None
    score: int  # AI Confidence 0-100
    sentiment: str
    summary: str
    bullishFactors: list[str]
    riskFactors: list[str]
    use_ml: bool
    cached: bool
    generated_at: str


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def _load_bars(db: Session, ticker: str) -> list[MarketData]:
    return list(
        db.scalars(
            select(MarketData)
            .where(MarketData.ticker == ticker)
            .order_by(MarketData.date)
        )
    )


def _predict_up(bars: list[MarketData]) -> float | None:
    feature_vector = build_feature_vector(bars)
    if feature_vector is None:
        return None
    try:
        return inference.predict_from_features(feature_vector).probability_up
    except Exception:  # noqa: BLE001 - ML opsional; report tetap jalan tanpa ML
        return None


def build_report_input(
    bars: list[MarketData], probability_up: float | None
) -> ai_report.ReportInput:
    """Rakit ReportInput dari indikator bar terakhir (pre-computed di Day 3)."""
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

    volumes = [float(bar.volume or 0) for bar in bars]
    volume_ratio = indicators.calculate_volume_spike(volumes)[-1].ratio
    if volume_ratio is None and previous.volume:
        volume_ratio = float(latest.volume or 0) / float(previous.volume)

    atr_pct = (latest.atr / close) if (latest.atr is not None and close) else None

    return ai_report.ReportInput(
        rsi=latest.rsi,
        macd_histogram=latest.macd_histogram,
        prev_macd_histogram=previous.macd_histogram,
        bb_position=bb_position,
        close=close,
        bb_upper=latest.bb_upper,
        bb_lower=latest.bb_lower,
        return_1d=return_1d,
        return_5d=return_5d,
        volume_ratio=volume_ratio,
        atr_pct=atr_pct,
        probability_up=probability_up,
    )


def assemble_report_payload(
    db: Session, ticker: str, bars: list[MarketData], use_ml: bool
) -> dict:
    """Rakit payload report dari bar yang SUDAH divalidasi (>= MIN_BARS).

    Dipakai bersama oleh endpoint & job scheduler (Day 13) agar bentuk cache identik.
    """
    probability_up = _predict_up(bars) if use_ml else None
    report = ai_report.generate_report(ticker, build_report_input(bars, probability_up))

    stock = db.get(Stock, ticker)
    latest = bars[-1]
    return StockReportResponse(
        ticker=ticker,
        name=stock.name if stock else None,
        sector=stock.sector if stock else None,
        date=latest.date.isoformat(),
        close=latest.close,
        score=report.score,
        sentiment=report.sentiment,
        summary=report.summary,
        bullishFactors=report.bullish_factors,
        riskFactors=report.risk_factors,
        use_ml=use_ml,
        cached=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
    ).model_dump()


@router.get("/{ticker}", response_model=StockReportResponse)
def get_stock_report(
    ticker: str,
    use_ml: bool = Query(True),
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict:
    ticker = ticker.strip().upper()
    cache_key = CACHE_KEY.format(ticker=ticker, ml=use_ml)

    if not refresh:
        cached = redis_client.cache_get_json(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    bars = _load_bars(db, ticker)
    if not bars:
        raise HTTPException(
            status_code=404,
            detail=f"Tidak ada market_data untuk ticker '{ticker}'.",
        )
    if len(bars) < MIN_BARS:
        raise HTTPException(
            status_code=422,
            detail=f"Data '{ticker}' belum cukup ({len(bars)} bar, minimal {MIN_BARS}).",
        )

    result = assemble_report_payload(db, ticker, bars, use_ml)
    redis_client.cache_set_json(cache_key, result, ttl=redis_client.TTL_REPORT)
    return result
