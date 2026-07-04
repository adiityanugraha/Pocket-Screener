"""Sector Rotation API (Phase 5 Day 2).

GET /api/sector-rotation
  Kekuatan relatif & rotasi sektor pada beberapa horizon (1M/3M/6M) terhadap
  IHSG, plus kuadran rotasi (LEADING/WEAKENING/LAGGING/IMPROVING). Prasyarat
  AI Analyst Engine & Market Narrator (Phase 5).

Desain HEMAT TRANSFER (Neon free tier): hanya memuat window terakhir (≈ window
terbesar + bantalan) dan KOLOM ticker/date/close saja - tidak memuat seluruh
market_data. Hasil di-cache di Redis (cache-only; tidak ada tabel histori, sama
seperti Monte Carlo Phase 4 - snapshot sektor terkini cukup untuk narasi AI).

Query params:
  as_of    : YYYY-MM-DD (default: tanggal terbaru di market_data)
  top      : jumlah leaders/laggards (default 3)
  refresh  : abaikan cache & hitung ulang (default false)
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cache import redis_client
from app.core import sector_rotation as sr
from app.core.instruments import INDEX_TICKERS, is_index
from app.db.models import MarketData, Stock
from app.db.session import get_db

router = APIRouter(prefix="/api/sector-rotation", tags=["sector-rotation"])

CACHE_KEY = "sector-rotation:{as_of}:top={top}"

# IHSG dipakai sebagai pasar untuk relative strength.
MARKET_TICKER = "IHSG"

# Bantalan kalender untuk menutup window hari-bursa terbesar (126 ≈ 6 bulan).
# 126 hari bursa ≈ 180 hari kalender; pakai 230 agar aman terhadap libur panjang.
_LOOKBACK_CALENDAR_DAYS = 230


# --------------------------------------------------------------------------- #
# Response schema
# --------------------------------------------------------------------------- #
class SectorOut(BaseModel):
    sector: str
    members: int
    returns: dict[str, float | None]
    relative_strength: dict[str, float | None]
    momentum: float | None = None
    quadrant: str
    rank: int | None = None


class RotationResponse(BaseModel):
    as_of: str
    windows: dict[str, int]
    market_ticker: str
    market_available: bool
    market_returns: dict[str, float | None]
    sectors: list[SectorOut]
    leaders: list[str]
    laggards: list[str]
    limitations: list[str]
    cached: bool
    generated_at: str


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def _resolve_as_of(db: Session, as_of_param: str | None) -> date_cls:
    if as_of_param:
        try:
            return date_cls.fromisoformat(as_of_param)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Format as_of harus YYYY-MM-DD.") from exc
    latest = db.scalar(select(func.max(MarketData.date)))
    if latest is None:
        raise HTTPException(status_code=404, detail="market_data masih kosong.")
    return latest


def _load_series(db: Session, as_of: date_cls) -> dict[str, list[float]]:
    """Seri close per ticker pada window terakhir (urut tanggal naik). Lean query."""
    lo = as_of - timedelta(days=_LOOKBACK_CALENDAR_DAYS)
    rows = db.execute(
        select(MarketData.ticker, MarketData.close)
        .where(MarketData.date >= lo, MarketData.date <= as_of)
        .order_by(MarketData.ticker, MarketData.date)
    ).all()
    series: dict[str, list[float]] = {}
    for ticker, close in rows:
        if close is None:
            continue
        series.setdefault(ticker, []).append(float(close))
    return series


def _build_sector_inputs(
    db: Session, series: dict[str, list[float]]
) -> list[sr.SectorInput]:
    """Kelompokkan seri close per sektor (kecuali indeks). Sektor tanpa label -> 'Lainnya'."""
    sector_of = {s.ticker: (s.sector or "Lainnya") for s in db.scalars(select(Stock))}
    grouped: dict[str, list[list[float]]] = {}
    for ticker, closes in series.items():
        if is_index(ticker):
            continue
        sector = sector_of.get(ticker, "Lainnya")
        grouped.setdefault(sector, []).append(closes)
    return [sr.SectorInput(sector=name, member_closes=members) for name, members in grouped.items()]


@router.get("", response_model=RotationResponse)
def get_sector_rotation(
    as_of: str | None = Query(None),
    top: int = Query(sr.DEFAULT_TOP_N, ge=1, le=10),
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict:
    target = _resolve_as_of(db, as_of)
    cache_key = CACHE_KEY.format(as_of=target.isoformat(), top=top)

    if not refresh:
        cached = redis_client.cache_get_json(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    series = _load_series(db, target)
    if not series:
        raise HTTPException(
            status_code=404,
            detail=f"Tidak ada data harga pada rentang menuju {target.isoformat()}.",
        )

    market_closes = series.get(MARKET_TICKER, [])
    sector_inputs = _build_sector_inputs(db, series)
    if not sector_inputs:
        raise HTTPException(status_code=404, detail="Tidak ada saham bersektor untuk dihitung.")

    result = sr.compute_rotation(
        sector_inputs, market_closes, as_of=target.isoformat(), top_n=top
    )

    payload = RotationResponse(
        as_of=result.as_of,
        windows=result.windows,
        market_ticker=MARKET_TICKER,
        market_available=result.market_available,
        market_returns=result.market_returns,
        sectors=[
            SectorOut(
                sector=s.sector,
                members=s.members,
                returns=s.returns,
                relative_strength=s.relative_strength,
                momentum=s.momentum,
                quadrant=s.quadrant,
                rank=s.rank,
            )
            for s in result.sectors
        ],
        leaders=result.leaders,
        laggards=result.laggards,
        limitations=result.limitations,
        cached=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
    ).model_dump()

    redis_client.cache_set_json(cache_key, payload, ttl=redis_client.TTL_RANKING)
    return payload


# IHSG sengaja dikecualikan dari grup sektor namun dipakai sebagai pasar.
assert MARKET_TICKER in INDEX_TICKERS, "MARKET_TICKER harus terdaftar sebagai indeks."
