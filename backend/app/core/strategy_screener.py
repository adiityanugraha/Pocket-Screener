"""Runner generik: jalankan SATU strategi (dari registry) atas seluruh universe.

Dipakai endpoint GET /api/screener?strategy={name} (Day 3) dan menjadi fondasi
GET /api/screener/all + strategy_results (Day 7). Berbeda dari app.api.screener
(jalur Phase 2 BSJP/BPJS + ML + levels), runner ini netral-strategi: ia hanya
mengembalikan kandidat yang LOLOS beserta matched_criteria (penjelasan otomatis).

Indeks (IHSG) dikecualikan - bukan saham tradable.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.fundamentals import FundamentalView, build_fundamental_view
from app.core.instruments import is_index
from app.core.strategies import registry
from app.core.strategies.base import StockData
from app.db.models import Fundamental, MarketData, Stock, StrategyResultRow
from app.db.queries import load_recent_bars_by_ticker

# Strategi terpanjang = Trend Following (MA200 -> butuh >=200 bar). 420 hari
# kalender (~290 bar bursa) memenuhinya dengan margin; price_ma(200) tetap memakai
# 200 bar terakhir sehingga hasil IDENTIK, tanpa memuat seluruh histori 10 tahun.
STRATEGY_LOOKBACK_DAYS = 420


def load_bars_by_ticker(db: Session) -> dict[str, list[MarketData]]:
    """Bar market_data terakhir (jendela ~420 hari) dikelompokkan per ticker."""
    return load_recent_bars_by_ticker(db, lookback_days=STRATEGY_LOOKBACK_DAYS)


def load_fundamentals_by_ticker(db: Session) -> dict[str, list[Fundamental]]:
    """Semua baris fundamentals dikelompokkan per ticker."""
    rows = db.scalars(select(Fundamental))
    grouped: dict[str, list[Fundamental]] = {}
    for row in rows:
        grouped.setdefault(row.ticker, []).append(row)
    return grouped


def evaluate_ticker(
    db: Session, ticker: str
) -> tuple[list[MarketData], FundamentalView | None, dict] | None:
    """Jalankan SEMUA strategi untuk SATU ticker (live, selalu segar).

    Mengembalikan (bars, view, results) di mana results = {strategy_key:
    StrategyResult}. None bila ticker tak punya bar. Dipakai /api/explain &
    /api/why (Day 10) - tak bergantung strategy_results sudah ter-persist.
    """
    bars = list(
        db.scalars(
            select(MarketData).where(MarketData.ticker == ticker).order_by(MarketData.date)
        )
    )
    if not bars:
        return None
    rows = list(db.scalars(select(Fundamental).where(Fundamental.ticker == ticker)))
    view = build_view_for(ticker, bars, rows)
    results = registry.run_all(StockData(ticker=ticker, bars=bars, fundamentals=view))
    return bars, view, results


def build_view_for(ticker: str, bars: list[MarketData], rows: list[Fundamental]) -> FundamentalView | None:
    """FundamentalView untuk satu ticker (None bila tak ada baris fundamentals).

    Metrik harga-sensitif dihitung dari close TERBARU market_data - konsisten
    dengan fundamental_derived (Day 5), tanpa bergantung job derived sudah jalan.
    """
    if not rows or not bars:
        return None
    latest = bars[-1]
    return build_fundamental_view(
        ticker, rows, close=latest.close, as_of=latest.date, price_bars=bars
    )


def _candidate(ticker: str, bars: list[MarketData], matched: list[str], stock: Stock | None) -> dict:
    latest = bars[-1]
    return {
        "ticker": ticker,
        "name": stock.name if stock else None,
        "sector": stock.sector if stock else None,
        "date": latest.date.isoformat(),
        "open": latest.open,
        "close": latest.close,
        "volume": float(latest.volume) if latest.volume is not None else 0.0,
        "value": latest.value if latest.value is not None else 0.0,
        "matched_criteria": matched,
    }


def screen_one_strategy(db: Session, strategy_key: str, limit: int | None = None) -> dict:
    """Jalankan satu strategi atas seluruh ticker.

    Mengembalikan ringkasan (universe/evaluated/passed) + daftar kandidat lolos,
    diurutkan menurun berdasarkan nilai transaksi (turnover) sebagai proxy
    likuiditas yang berlaku universal untuk strategi teknikal & fundamental.

    KeyError bila strategy_key tidak terdaftar (caller -> HTTP 404).
    """
    strategy = registry.get(strategy_key)
    if strategy is None:
        raise KeyError(strategy_key)

    bars_by_ticker = load_bars_by_ticker(db)
    funds_by_ticker = load_fundamentals_by_ticker(db)
    stock_map = {stock.ticker: stock for stock in db.scalars(select(Stock))}

    candidates: list[dict] = []
    evaluated = 0
    for ticker, bars in bars_by_ticker.items():
        if is_index(ticker):
            continue
        view = build_view_for(ticker, bars, funds_by_ticker.get(ticker, []))
        result = strategy.run(StockData(ticker=ticker, bars=bars, fundamentals=view))
        if not result.evaluated:
            continue
        evaluated += 1
        if result.passed:
            candidates.append(
                _candidate(ticker, bars, result.matched_criteria, stock_map.get(ticker))
            )

    candidates.sort(key=lambda c: c["value"] or 0.0, reverse=True)
    passed_count = len(candidates)  # total lolos, sebelum dipangkas limit
    if limit is not None:
        candidates = candidates[:limit]

    return {
        "strategy": strategy.key,
        "name": strategy.name,
        "type": strategy.type.value,
        "output_label": strategy.output_label,
        "universe": sum(1 for t in bars_by_ticker if not is_index(t)),
        "evaluated": evaluated,
        "passed": passed_count,
        "candidates": candidates,
    }


# --------------------------------------------------------------------------- #
# Semua strategi sekaligus (Day 7): /api/screener/all + tabel strategy_results
# --------------------------------------------------------------------------- #
def _persist_strategy_results(db: Session, rows: list[dict]) -> int:
    """Upsert hasil evaluasi (termasuk gagal) ke strategy_results, idempoten
    per (date, ticker, strategy)."""
    if not rows:
        return 0
    stmt = pg_insert(StrategyResultRow).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_strategy_results_date_ticker_strategy",
        set_={
            "passed": stmt.excluded.passed,
            "matched_criteria": stmt.excluded.matched_criteria,
            "skipped_criteria": stmt.excluded.skipped_criteria,
        },
    )
    db.execute(stmt)
    db.commit()
    return len(rows)


def screen_all_strategies(db: Session, limit: int | None = None, persist: bool = True) -> dict:
    """Jalankan SEMUA strategi registry atas seluruh universe dalam satu lintasan.

    Data per ticker (bar + FundamentalView) dibangun SEKALI lalu dipakai semua
    strategi. Hasil evaluasi (pass & fail) di-persist ke strategy_results untuk
    Strategy Matrix (Day 8) / Strength Score (Day 9) / Explain (Day 10).
    """
    bars_by_ticker = load_bars_by_ticker(db)
    funds_by_ticker = load_fundamentals_by_ticker(db)
    stock_map = {stock.ticker: stock for stock in db.scalars(select(Stock))}
    strategies = registry.all_strategies()

    per_strategy: dict[str, dict] = {
        s.key: {
            "strategy": s.key,
            "name": s.name,
            "type": s.type.value,
            "output_label": s.output_label,
            "evaluated": 0,
            "passed": 0,
            "candidates": [],
        }
        for s in strategies
    }
    persist_rows: list[dict] = []
    universe = 0

    for ticker, bars in bars_by_ticker.items():
        if is_index(ticker):
            continue
        universe += 1
        view = build_view_for(ticker, bars, funds_by_ticker.get(ticker, []))
        data = StockData(ticker=ticker, bars=bars, fundamentals=view)
        latest_date = bars[-1].date

        for strategy in strategies:
            result = strategy.run(data)
            if not result.evaluated:
                continue
            bucket = per_strategy[strategy.key]
            bucket["evaluated"] += 1
            if result.passed:
                bucket["passed"] += 1
                bucket["candidates"].append(
                    _candidate(ticker, bars, result.matched_criteria, stock_map.get(ticker))
                )
            persist_rows.append(
                {
                    "date": latest_date,
                    "ticker": ticker,
                    "strategy": strategy.key,
                    "passed": result.passed,
                    "matched_criteria": result.matched_criteria,
                    "skipped_criteria": result.skipped_criteria,
                }
            )

    for bucket in per_strategy.values():
        bucket["candidates"].sort(key=lambda c: c["value"] or 0.0, reverse=True)
        if limit is not None:
            bucket["candidates"] = bucket["candidates"][:limit]

    persisted = _persist_strategy_results(db, persist_rows) if persist else 0

    return {
        "universe": universe,
        "persisted": persisted,
        "strategies": list(per_strategy.values()),
    }
