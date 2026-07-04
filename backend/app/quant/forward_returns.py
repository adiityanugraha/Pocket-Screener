"""Return forward & trade log per kandidat (Phase 4, Day 3).

Melengkapi rekonstruksi (Day 2): untuk SETIAP kandidat yang lolos di
strategy_results (5 strategi teknikal), hitung return forward pada horizon
+1 / +3 / +7 / +30 hari bursa dari harga close tanggal screening, lalu
materialisasi ke tabel replay_history. Tabel ini menjadi "trade log" - dasar
Equity Curve (Day 5), Performance Metrics (Day 4), dan Monte Carlo (Day 10).

KONVENSI return:
  - Entry  = close pada tanggal screening T (P).
  - Exit   = close pada bar ke-h SETELAH T (offset HARI BURSA, bukan kalender -
             menghindari celah akhir pekan/libur & bar hilang).
  - gross  = close[T+h] / close[T] - 1.
  - net    = gross - ROUND_TRIP_COST (biaya beli+jual+slippage sekali putar).
             Biaya round-trip sama untuk semua horizon (satu beli + satu jual),
             jadi net = gross - cost di tiap horizon.
  Kerangka close-to-close harian ini DISENGAJA seragam untuk semua strategi
  (termasuk BSJP/BPJS yang aslinya intraday) agar metrik quant lintas-strategi
  apple-to-apple. Disebut sebagai penyederhanaan di disclaimer UI (Day 16).

BUKAN look-ahead: return forward MENGUKUR apa yang terjadi setelah keputusan
screening (yang sudah dibuat point-in-time di Day 2). Ini hasil, bukan input.

LIMITASI (survivorship bias): universe = 81 saham yang MASIH listing. Saham yang
sudah delisting tidak ada di market_data → return historis sedikit bias optimis.
Dicatat sebagai limitasi (sumber data Yahoo gratis tak menyediakan delisted IDX).

Jalankan (sekali, offline; setelah Day 2):
    python -m app.quant.forward_returns                  # seluruh trade log
    python -m app.quant.forward_returns --ticker BBCA
    python -m app.quant.forward_returns --cost 0.005     # asumsi biaya 0.5%
    python -m app.quant.forward_returns --dry-run
"""

from __future__ import annotations

import argparse
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.instruments import is_index
from app.db.models import MarketData, ReplayHistory, StrategyResultRow
from app.db.session import SessionLocal
from app.quant.reconstruct import TECHNICAL_KEYS

#: Horizon return forward (hari bursa). Dipetakan ke kolom ret_1d/3d/7d/30d.
FORWARD_HORIZONS: tuple[int, ...] = (1, 3, 7, 30)

#: Asumsi biaya round-trip (beli + jual + slippage) untuk IDX. 0.3% wajar:
#: fee beli ~0.15% + fee jual ~0.25% (termasuk pajak) sebagian diimbangi, plus
#: slippage tipis. Configurable agar metrik bisa diuji sensitivitasnya.
DEFAULT_ROUND_TRIP_COST = 0.003

_HORIZON_COLUMN = {1: "ret_1d", 3: "ret_3d", 7: "ret_7d", 30: "ret_30d"}
_UPSERT_COLUMNS = ("score", "price", "ret_1d", "ret_3d", "ret_7d", "ret_30d")


def compute_forward_returns(
    closes: list[float],
    j: int,
    horizons: tuple[int, ...] = FORWARD_HORIZONS,
    cost: float = DEFAULT_ROUND_TRIP_COST,
) -> dict[int, float | None]:
    """Return net per horizon dari indeks bar `j` (entry). None bila:
    belum jatuh tempo (j+h di luar seri) atau harga entry tidak valid.
    """
    out: dict[int, float | None] = {}
    p = closes[j] if 0 <= j < len(closes) else None
    for h in horizons:
        k = j + h
        if p is None or p == 0 or k >= len(closes) or closes[k] is None:
            out[h] = None
        else:
            out[h] = (closes[k] / p - 1.0) - cost
    return out


def _load_price_series(db: Session, ticker: str) -> tuple[list[float], dict[date, int]]:
    """(closes urut kronologis, peta date->indeks) untuk satu ticker."""
    rows = list(
        db.execute(
            select(MarketData.date, MarketData.close)
            .where(MarketData.ticker == ticker)
            .order_by(MarketData.date)
        )
    )
    closes = [r[1] for r in rows]
    index = {r[0]: i for i, r in enumerate(rows)}
    return closes, index


def _load_passed_by_ticker(
    db: Session, tickers: list[str] | None
) -> dict[str, list[tuple[date, str]]]:
    """Kandidat LOLOS (date, strategy) per ticker, hanya 5 strategi teknikal."""
    stmt = (
        select(StrategyResultRow.ticker, StrategyResultRow.date, StrategyResultRow.strategy)
        .where(StrategyResultRow.passed.is_(True))
        .where(StrategyResultRow.strategy.in_(TECHNICAL_KEYS))
        .order_by(StrategyResultRow.ticker, StrategyResultRow.date)
    )
    if tickers:
        stmt = stmt.where(StrategyResultRow.ticker.in_(tickers))
    grouped: dict[str, list[tuple[date, str]]] = {}
    for ticker, d, strategy in db.execute(stmt):
        grouped.setdefault(ticker, []).append((d, strategy))
    return grouped


def _persist_replay(db: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    stmt = pg_insert(ReplayHistory).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_replay_date_ticker_strategy",
        set_={col: stmt.excluded[col] for col in _UPSERT_COLUMNS},
    )
    db.execute(stmt)
    db.commit()
    return len(rows)


def build_replay_history(
    db: Session,
    *,
    tickers: list[str] | None = None,
    cost: float = DEFAULT_ROUND_TRIP_COST,
    persist: bool = True,
    batch_size: int = 5000,
    progress: bool = True,
) -> dict:
    """Materialisasi trade log ke replay_history dari kandidat lolos + harga forward.

    Per ticker: muat seri harga SEKALI, lalu untuk tiap kandidat hitung return
    forward dan rakit baris replay_history (idempoten via upsert).
    """
    if tickers:
        tickers = [t.strip().upper() for t in tickers if not is_index(t)]
    passed_by_ticker = _load_passed_by_ticker(db, tickers)

    total = 0
    matured = 0  # punya minimal ret_1d (sudah jatuh tempo 1 hari)
    persisted = 0
    batch: list[dict] = []
    universe = sorted(passed_by_ticker)

    for idx, ticker in enumerate(universe, start=1):
        closes, index = _load_price_series(db, ticker)
        rows_for_ticker = 0
        for d, strategy in passed_by_ticker[ticker]:
            j = index.get(d)
            if j is None:  # tanggal kandidat tak ada di market_data (mustahil normal)
                continue
            rets = compute_forward_returns(closes, j, FORWARD_HORIZONS, cost)
            row = {
                "date": d,
                "ticker": ticker,
                "strategy": strategy,
                "score": None,  # strategi teknikal tak punya skor historis
                "price": closes[j],
            }
            for h in FORWARD_HORIZONS:
                row[_HORIZON_COLUMN[h]] = rets[h]
            batch.append(row)
            total += 1
            rows_for_ticker += 1
            if rets[1] is not None:
                matured += 1
            if persist and len(batch) >= batch_size:
                persisted += _persist_replay(db, batch)
                batch = []
        if progress:
            print(f"  [{idx:>3}/{len(universe)}] {ticker:<6} trades={rows_for_ticker}")

    if persist and batch:
        persisted += _persist_replay(db, batch)
    if not persist:
        persisted = total

    return {
        "tickers": len(universe),
        "trades": total,
        "matured_1d": matured,
        "persisted": persisted,
        "cost": cost,
    }


def load_return_series(
    db: Session, strategy: str, horizon: int = 1
) -> list[tuple[date, float]]:
    """Seri (date, net_return) untuk satu strategi/horizon - dasar equity & metrik.

    Hanya trade yang sudah jatuh tempo (kolom ret_{h} tidak NULL), urut tanggal.
    """
    column = getattr(ReplayHistory, _HORIZON_COLUMN[horizon])
    rows = db.execute(
        select(ReplayHistory.date, column)
        .where(ReplayHistory.strategy == strategy)
        .where(column.is_not(None))
        .order_by(ReplayHistory.date)
    )
    return [(d, r) for d, r in rows]


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Bangun trade log replay_history (Phase 4 Day 3)."
    )
    parser.add_argument("--ticker", nargs="+", help="Ticker spesifik (mis. BBCA BMRI).")
    parser.add_argument(
        "--cost",
        type=float,
        default=DEFAULT_ROUND_TRIP_COST,
        help=f"Biaya round-trip (default {DEFAULT_ROUND_TRIP_COST}).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Hitung saja, jangan tulis.")
    args = parser.parse_args()

    if SessionLocal is None:
        raise SystemExit("DATABASE_URL belum diset di backend/.env")

    db = SessionLocal()
    try:
        print(f"Membangun trade log (return forward, cost={args.cost})...")
        summary = build_replay_history(
            db, tickers=args.ticker, cost=args.cost, persist=not args.dry_run
        )
        print(
            f"\nSelesai: {summary['tickers']} ticker, {summary['trades']:,} trade, "
            f"{summary['matured_1d']:,} jatuh tempo (>=1d), "
            f"{summary['persisted']:,} baris {'dihitung' if args.dry_run else 'tersimpan'}."
        )
    finally:
        db.close()


if __name__ == "__main__":
    _main()
