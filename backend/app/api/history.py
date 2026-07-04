"""Screener History & Performance Tracking API (Day 12).

GET /api/history
  Riwayat saham yang lolos screener per tanggal (dari screening_history) +
  tracking performa forward (return `horizon` hari setelah screening) + ringkasan
  winrate per strategi atas entri yang ditampilkan.

GET /api/history/dates
  Daftar tanggal yang punya hasil screener + jumlah kandidat (untuk date picker).

GET /api/history/performance
  Analisis akurasi strategi atas SELURUH riwayat (winrate, avg/cumulative return,
  max drawdown per strategi). ?persist=true menyimpan ringkasan ke tabel backtesting.
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import performance
from app.db.models import Backtesting, MarketData, ScreeningHistory, Stock
from app.db.queries import load_recent_bars_by_ticker
from app.db.session import get_db

router = APIRouter(prefix="/api/history", tags=["history"])

DEFAULT_HORIZON = 7  # hari bursa untuk mengukur performa forward


# --------------------------------------------------------------------------- #
# Response schema
# --------------------------------------------------------------------------- #
class HistoryEntryOut(BaseModel):
    date: str
    ticker: str
    name: str | None = None
    strategy: str
    score: float | None = None
    entry_close: float
    forward_close: float | None = None
    forward_return: float | None = None
    outcome: str  # WIN | LOSS | FLAT | PENDING


class PerformanceOut(BaseModel):
    strategy: str
    total: int
    evaluated: int
    wins: int
    losses: int
    flat: int
    winrate: float | None = None
    avg_return: float | None = None
    cumulative_return: float | None = None
    max_drawdown: float | None = None


class HistoryResponse(BaseModel):
    horizon: int
    count: int
    entries: list[HistoryEntryOut]
    summary: list[PerformanceOut]
    generated_at: str


class DateCountOut(BaseModel):
    date: str
    count: int


class DatesResponse(BaseModel):
    count: int
    dates: list[DateCountOut]


class PerformanceResponse(BaseModel):
    horizon: int
    persisted: bool
    strategies: list[PerformanceOut]
    generated_at: str


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _bars_by_ticker(
    db: Session, history_rows: list[ScreeningHistory]
) -> dict[str, list[MarketData]]:
    """Hanya muat bar yang menjangkau rentang tanggal entri riwayat + horizon
    (dari tanggal pick tertua sampai tanggal terbaru) - bukan seluruh histori.
    Hasil tracking IDENTIK karena semua bar yang dibutuhkan tetap termuat.
    """
    if not history_rows:
        return {}
    latest = db.scalar(select(func.max(MarketData.date)))
    if latest is None:
        return {}
    oldest = min(row.date for row in history_rows)
    lookback = (latest - oldest).days + 10  # +buffer untuk bar forward
    return load_recent_bars_by_ticker(db, lookback_days=lookback)


def _date_index(bars: list[MarketData]) -> dict[date_cls, int]:
    return {bar.date: i for i, bar in enumerate(bars)}


def _track(
    history_rows: list[ScreeningHistory],
    bars_by_ticker: dict[str, list[MarketData]],
    stock_map: dict[str, Stock],
    horizon: int,
) -> list[performance.TrackedTrade]:
    """Hitung performa forward tiap entri riwayat."""
    index_cache: dict[str, dict[date_cls, int]] = {}
    trades: list[performance.TrackedTrade] = []

    for row in history_rows:
        bars = bars_by_ticker.get(row.ticker)
        if not bars:
            continue
        idx_map = index_cache.setdefault(row.ticker, _date_index(bars))
        idx = idx_map.get(row.date)
        if idx is None or bars[idx].close is None:
            continue
        entry_close = float(bars[idx].close)

        forward_idx = idx + horizon
        forward_close = (
            float(bars[forward_idx].close)
            if forward_idx < len(bars) and bars[forward_idx].close is not None
            else None
        )
        trades.append(
            performance.make_trade(
                date=row.date.isoformat(),
                ticker=row.ticker,
                strategy=row.strategy,
                score=row.score,
                entry_close=entry_close,
                forward_close=forward_close,
            )
        )
    return trades


def _entry_out(trade: performance.TrackedTrade, stock_map: dict[str, Stock]) -> HistoryEntryOut:
    stock = stock_map.get(trade.ticker)
    return HistoryEntryOut(
        date=trade.date,
        ticker=trade.ticker,
        name=stock.name if stock else None,
        strategy=trade.strategy,
        score=trade.score,
        entry_close=trade.entry_close,
        forward_close=trade.forward_close,
        forward_return=trade.forward_return,
        outcome=trade.outcome,
    )


def _perf_out(perf: performance.StrategyPerformance) -> PerformanceOut:
    return PerformanceOut(
        strategy=perf.strategy,
        total=perf.total,
        evaluated=perf.evaluated,
        wins=perf.wins,
        losses=perf.losses,
        flat=perf.flat,
        winrate=perf.winrate,
        avg_return=perf.avg_return,
        cumulative_return=perf.cumulative_return,
        max_drawdown=perf.max_drawdown,
    )


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.get("", response_model=HistoryResponse)
def get_history(
    date: str | None = Query(None, description="Filter satu tanggal (YYYY-MM-DD)."),
    strategy: str | None = Query(None, description="Filter BSJP | BPJS."),
    horizon: int = Query(DEFAULT_HORIZON, ge=1, le=60),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(ScreeningHistory)
    if date:
        try:
            stmt = stmt.where(ScreeningHistory.date == date_cls.fromisoformat(date))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Format date harus YYYY-MM-DD.") from exc
    if strategy:
        stmt = stmt.where(ScreeningHistory.strategy == strategy.strip().upper())
    stmt = stmt.order_by(ScreeningHistory.date.desc(), ScreeningHistory.score.desc()).limit(limit)

    history_rows = list(db.scalars(stmt))
    bars_by_ticker = _bars_by_ticker(db, history_rows)
    stock_map = {stock.ticker: stock for stock in db.scalars(select(Stock))}

    trades = _track(history_rows, bars_by_ticker, stock_map, horizon)
    summary = [
        _perf_out(performance.summarize(trades, strat))
        for strat in ("BSJP", "BPJS")
        if any(t.strategy == strat for t in trades)
    ]

    return HistoryResponse(
        horizon=horizon,
        count=len(trades),
        entries=[_entry_out(t, stock_map) for t in trades],
        summary=summary,
        generated_at=datetime.now(timezone.utc).isoformat(),
    ).model_dump()


@router.get("/dates", response_model=DatesResponse)
def get_history_dates(db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        select(ScreeningHistory.date, func.count())
        .group_by(ScreeningHistory.date)
        .order_by(ScreeningHistory.date.desc())
    ).all()
    dates = [DateCountOut(date=row[0].isoformat(), count=row[1]) for row in rows]
    return DatesResponse(count=len(dates), dates=dates).model_dump()


@router.get("/performance", response_model=PerformanceResponse)
def get_history_performance(
    horizon: int = Query(DEFAULT_HORIZON, ge=1, le=60),
    persist: bool = Query(False, description="Simpan ringkasan ke tabel backtesting."),
    db: Session = Depends(get_db),
) -> dict:
    history_rows = list(db.scalars(select(ScreeningHistory)))
    bars_by_ticker = _bars_by_ticker(db, history_rows)
    stock_map = {stock.ticker: stock for stock in db.scalars(select(Stock))}

    trades = _track(history_rows, bars_by_ticker, stock_map, horizon)
    perfs = [performance.summarize(trades, strat) for strat in ("BSJP", "BPJS")]

    if persist:
        for perf in perfs:
            db.add(
                Backtesting(
                    strategy=perf.strategy,
                    winrate=perf.winrate,
                    cumulative_return=perf.cumulative_return,
                    max_drawdown=perf.max_drawdown,
                )
            )
        db.commit()

    return PerformanceResponse(
        horizon=horizon,
        persisted=persist,
        strategies=[_perf_out(p) for p in perfs],
        generated_at=datetime.now(timezone.utc).isoformat(),
    ).model_dump()
