"""Risk Meter API (Day 9).

GET /api/risk/{ticker}
  Hitung tingkat risiko saham dari empat metrik (Historical Volatility, ATR%,
  Max Drawdown, Beta) -> risk score 0-100 + klasifikasi LOW/MEDIUM/HIGH
  (app.core.risk_meter). Beta diukur vs proxy index equal-weighted seluruh
  universe. Hasil di-cache di Redis (TTL_INDICATORS).

Query params:
  refresh : abaikan cache & hitung ulang (default false)
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cache import redis_client
from app.core import risk_meter
from app.core.instruments import is_index
from app.db.models import MarketData, Stock
from app.db.session import get_db

router = APIRouter(prefix="/api/risk", tags=["risk"])

CACHE_KEY = "risk:{ticker}"

# Minimal bar agar Historical Volatility & drawdown bermakna.
MIN_BARS = 20


# --------------------------------------------------------------------------- #
# Response schema
# --------------------------------------------------------------------------- #
class RiskBreakdownOut(BaseModel):
    atr_pct: float | None = None
    historical_volatility: float | None = None
    max_drawdown: float | None = None
    beta: float | None = None


class RiskResponse(BaseModel):
    ticker: str
    name: str | None = None
    sector: str | None = None
    date: str
    close: float | None = None
    risk: str  # LOW | MEDIUM | HIGH
    score: int  # 0-100 (makin tinggi makin berisiko)
    breakdown: RiskBreakdownOut
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


def _market_returns_by_date(db: Session) -> dict[date_cls, float]:
    """Proxy index: rata-rata return harian seluruh saham, dikunci per tanggal.

    Dipakai sebagai pembanding untuk menghitung Beta (IHSG tak tersimpan).

    Memuat HANYA kolom (ticker, date, close) sebagai tuple ringan - bukan objek
    ORM penuh - agar tidak meledakkan memori (proxy butuh seluruh histori untuk
    menjaga nilai Beta tetap sama; jadi yang dihemat adalah berat per-baris).
    """
    rows = db.execute(
        select(MarketData.ticker, MarketData.date, MarketData.close).order_by(
            MarketData.ticker, MarketData.date
        )
    )
    by_ticker: dict[str, list[tuple[date_cls, float | None]]] = {}
    for ticker, day, close in rows:
        by_ticker.setdefault(ticker, []).append((day, close))

    sums: dict[date_cls, float] = {}
    counts: dict[date_cls, int] = {}
    for ticker, series in by_ticker.items():
        if is_index(ticker):  # jangan masukkan indeks ke proxy pasar
            continue
        for i in range(1, len(series)):
            prev_close = series[i - 1][1]
            cur_close = series[i][1]
            if prev_close and cur_close:
                day = series[i][0]
                sums[day] = sums.get(day, 0.0) + (cur_close / prev_close - 1)
                counts[day] = counts.get(day, 0) + 1
    return {day: sums[day] / counts[day] for day in sums}


def build_risk_input(bars: list[MarketData], market_map: dict[date_cls, float]) -> risk_meter.RiskInput:
    closes = [float(bar.close) for bar in bars if bar.close is not None]
    latest = bars[-1]
    atr_pct = (latest.atr / latest.close) if (latest.atr is not None and latest.close) else None

    # Return pasar selaras tanggal dengan return saham (bars[1:]).
    market_returns = [
        market_map[bars[i].date] for i in range(1, len(bars)) if bars[i].date in market_map
    ]
    return risk_meter.RiskInput(
        closes=closes,
        atr_pct=atr_pct,
        market_returns=market_returns or None,
    )


@router.get("/{ticker}", response_model=RiskResponse)
def get_risk(
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

    market_map = _market_returns_by_date(db)
    result = risk_meter.compute_risk(build_risk_input(bars, market_map))

    stock = db.get(Stock, ticker)
    latest = bars[-1]
    payload = RiskResponse(
        ticker=ticker,
        name=stock.name if stock else None,
        sector=stock.sector if stock else None,
        date=latest.date.isoformat(),
        close=latest.close,
        risk=result.risk,
        score=result.score,
        breakdown=RiskBreakdownOut(
            atr_pct=result.atr_pct,
            historical_volatility=result.historical_volatility,
            max_drawdown=result.max_drawdown,
            beta=result.beta,
        ),
        cached=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
    ).model_dump()

    redis_client.cache_set_json(cache_key, payload, ttl=redis_client.TTL_INDICATORS)
    return payload
