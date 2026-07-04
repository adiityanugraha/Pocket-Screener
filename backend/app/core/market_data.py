"""Data pipeline: Yahoo OHLCV -> indikator teknikal -> tabel market_data.

Alur per ticker:
  1. fetch_daily_ohlcv (server-side, range 6mo)
  2. hitung seri indikator (RSI, MACD, BB, ATR, VWAP) - identik dgn frontend
  3. upsert tiap bar ke market_data (ON CONFLICT ticker+date -> update)

Jalankan manual (Day 3 / testing):
    python -m app.core.market_data                # seluruh universe (80 ticker)
    python -m app.core.market_data --limit 5      # 5 ticker pertama
    python -m app.core.market_data --ticker BBCA BMRI
"""

from __future__ import annotations

import argparse
import time
from datetime import date

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core import indicators
from app.core.yahoo import Bar, YahooFetchError, fetch_daily_ohlcv
from app.db.models import MarketData, Stock
from app.db.session import SessionLocal

# Kolom yang di-update saat konflik (semua kecuali PK id & natural key ticker/date).
_UPSERT_COLUMNS = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "value",
    "rsi",
    "macd",
    "macd_signal",
    "macd_histogram",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "atr",
    "vwap",
)


def build_market_rows(ticker: str, bars: list[Bar]) -> list[dict]:
    """Hitung indikator untuk seluruh seri lalu rakit satu dict per tanggal."""
    if not bars:
        return []

    closes = [bar.close for bar in bars]
    rsi = indicators.calculate_rsi(closes, 14)
    macd = indicators.calculate_macd(closes)
    bands = indicators.calculate_bollinger_bands(closes, 20)
    atr = indicators.calculate_atr(bars, 14)
    vwap = indicators.calculate_vwap(bars)

    rows: list[dict] = []
    for index, bar in enumerate(bars):
        band = bands[index]
        rows.append(
            {
                "ticker": ticker,
                "date": date.fromisoformat(bar.date),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "value": bar.close * bar.volume,  # turnover harian
                "rsi": rsi[index],
                "macd": macd.macd[index],
                "macd_signal": macd.signal[index],
                "macd_histogram": macd.histogram[index],
                "bb_upper": band.upper,
                "bb_middle": band.middle,
                "bb_lower": band.lower,
                "atr": atr[index],
                "vwap": vwap[index],
            }
        )
    return rows


def upsert_market_rows(db: Session, rows: list[dict]) -> None:
    """Bulk upsert berdasarkan unique constraint (ticker, date)."""
    if not rows:
        return
    stmt = pg_insert(MarketData).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_market_data_ticker_date",
        set_={column: stmt.excluded[column] for column in _UPSERT_COLUMNS},
    )
    db.execute(stmt)


def ingest_ticker(
    db: Session,
    ticker: str,
    range_: str = "6mo",
    client: httpx.Client | None = None,
) -> int:
    """Fetch + hitung + upsert satu ticker. Mengembalikan jumlah bar tersimpan."""
    bars = fetch_daily_ohlcv(ticker, range_=range_, client=client)
    rows = build_market_rows(ticker, bars)
    upsert_market_rows(db, rows)
    db.commit()
    return len(rows)


def ingest_universe(
    db: Session,
    tickers: list[str] | None = None,
    range_: str = "6mo",
    delay: float = 0.4,
) -> dict[str, int]:
    """Ingest banyak ticker. Error per-ticker di-skip (tidak menggagalkan batch).

    Jika `tickers` None, ambil seluruh isi tabel stocks.
    """
    if tickers is None:
        tickers = list(db.scalars(select(Stock.ticker).order_by(Stock.ticker)))

    results: dict[str, int] = {}
    with httpx.Client(timeout=15.0) as client:
        client.headers.update(
            {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        )
        for index, ticker in enumerate(tickers, start=1):
            try:
                count = ingest_ticker(db, ticker, range_=range_, client=client)
                results[ticker] = count
                print(f"  [{index:>3}/{len(tickers)}] {ticker:<6} -> {count} bar")
            except YahooFetchError as exc:
                db.rollback()
                results[ticker] = 0
                print(f"  [{index:>3}/{len(tickers)}] {ticker:<6} -> SKIP ({exc})")
            if delay:
                time.sleep(delay)

    return results


def _main() -> None:
    parser = argparse.ArgumentParser(description="Ingest market data dari Yahoo Finance")
    parser.add_argument(
        "--ticker", nargs="+", help="Ticker spesifik (mis. BBCA BMRI). Default: semua."
    )
    parser.add_argument("--limit", type=int, help="Batasi N ticker pertama dari stocks.")
    parser.add_argument("--range", default="6mo", help="Range Yahoo (default 6mo).")
    parser.add_argument("--delay", type=float, default=0.4, help="Jeda antar fetch (detik).")
    args = parser.parse_args()

    if SessionLocal is None:
        raise SystemExit("DATABASE_URL belum diset di backend/.env")

    db = SessionLocal()
    try:
        tickers = args.ticker
        if tickers is None and args.limit:
            tickers = list(
                db.scalars(select(Stock.ticker).order_by(Stock.ticker).limit(args.limit))
            )

        print(f"Mulai ingest (range={args.range})...")
        results = ingest_universe(db, tickers=tickers, range_=args.range, delay=args.delay)

        total_bars = sum(results.values())
        ok = sum(1 for count in results.values() if count > 0)
        print(
            f"\nSelesai: {ok}/{len(results)} ticker berhasil, "
            f"{total_bars} bar total tersimpan ke market_data."
        )
    finally:
        db.close()


if __name__ == "__main__":
    _main()
