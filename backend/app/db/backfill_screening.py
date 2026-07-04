"""Backfill screening_history dari seluruh data historis market_data.

Untuk tiap ticker, jalankan screener pada setiap "slice" (bar 0..i) sehingga
kandidat yang lolos pada tanggal bar-i tersimpan - meniru akumulasi yang nanti
dihasilkan scheduler harian (Day 13). Idempoten: upsert per (date, ticker, strategy).

Jalankan (dari backend/, venv aktif, DATABASE_URL terisi):
    python -m app.db.backfill_screening
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core import screener as screener_core
from app.core.instruments import is_index
from app.db.models import MarketData, ScreeningHistory
from app.db.session import SessionLocal


def _bars_by_ticker(db) -> dict[str, list[MarketData]]:
    rows = db.scalars(select(MarketData).order_by(MarketData.ticker, MarketData.date))
    grouped: dict[str, list[MarketData]] = {}
    for row in rows:
        grouped.setdefault(row.ticker, []).append(row)
    return grouped


def backfill() -> int:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL belum diset di backend/.env.")

    with SessionLocal() as db:
        grouped = _bars_by_ticker(db)
        rows: list[dict] = []

        for ticker, bars in grouped.items():
            if is_index(ticker):  # indeks tidak di-screen
                continue
            # Slice 0..i; screen_bars menilai bar terakhir (= bar ke-i).
            for i in range(screener_core.MIN_BARS - 1, len(bars)):
                window = bars[: i + 1]
                candidates = screener_core.screen_bars(ticker, window)
                if not candidates:
                    continue
                screen_date = window[-1].date
                for candidate in candidates:
                    rows.append(
                        {
                            "date": screen_date,
                            "ticker": ticker,
                            "score": candidate.score,
                            "strategy": candidate.strategy,
                        }
                    )

        if not rows:
            print("Tidak ada kandidat historis yang lolos screener.")
            return 0

        # Upsert berkelompok agar idempoten.
        stmt = pg_insert(ScreeningHistory).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_screening_date_ticker_strategy",
            set_={"score": stmt.excluded.score},
        )
        db.execute(stmt)
        db.commit()
        return len(rows)


def main() -> None:
    print("Backfilling screening_history dari market_data...")
    count = backfill()
    with SessionLocal() as db:
        distinct_dates = db.scalar(
            select(func.count(func.distinct(ScreeningHistory.date)))
        )
    print(f"  OK: {count} baris kandidat disimpan, {distinct_dates} tanggal berbeda.")


if __name__ == "__main__":
    main()
