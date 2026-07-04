"""Rekonstruksi histori strategy_results point-in-time (Phase 4, Day 2).

Fondasi semua fitur quant (Replay, Performance, Equity Curve, Monte Carlo,
Walk-Forward). Tabel strategy_results (Phase 3) hanya menumpuk sejak aplikasi
live, jadi belum cukup untuk backtest. Modul ini MENJALANKAN ULANG strategi
Phase 3 yang ASLI (dari registry - jaminan logika identik) atas SETIAP tanggal
historis di market_data, lalu mengisi strategy_results untuk seluruh rentang.

ATURAN ANTI LOOK-AHEAD (wajib):
  Saat menilai tanggal T, strategi hanya melihat bar dengan date <= T. Caranya:
  potong daftar bar menjadi window trailing yang BERAKHIR di T sebelum
  menjalankan strategi. Strategi teknikal Phase 3 hanya membaca bar terakhir
  (= hari berjalan), bar sebelumnya, dan MA inklusif dari window - sehingga
  evaluasi atas window <= T identik dengan "seandainya T adalah hari ini".
  Bar setelah T TIDAK pernah terlihat. Diuji di test_phase4_day2_reconstruct.

CAKUPAN: hanya 5 strategi TEKNIKAL (bsjp, bpjs, breakout, trend_following,
potential_reversal). Strategi fundamental DIKECUALIKAN dari backtest historis
(keputusan 2026-06-12): tidak ada snapshot fundamental point-in-time dari
Yahoo, sehingga menjalankannya atas tanggal lampau memakai laporan keuangan
TERKINI = look-ahead bias. Lihat app/quant/__init__.py.

Penyimpanan: untuk menjaga ukuran DB (Neon free) hanya baris yang LOLOS yang
disimpan secara default (only_passed=True) - backtest/replay/equity hanya butuh
kandidat yang lolos beserta return forward-nya (Day 3). Baris gagal historis
tak pernah di-query (Strategy Matrix Day 8 hanya memakai tanggal terbaru/live).

Jalankan (sekali, offline; setelah re-ingest 10y):
    python -m app.quant.reconstruct                 # seluruh universe, full range
    python -m app.quant.reconstruct --ticker BBCA   # satu ticker
    python -m app.quant.reconstruct --limit 5       # 5 ticker pertama (uji cepat)
    python -m app.quant.reconstruct --start 2024-01-01 --end 2024-12-31
    python -m app.quant.reconstruct --all           # simpan juga baris GAGAL
"""

from __future__ import annotations

import argparse
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.instruments import is_index
from app.core.strategies import registry
from app.core.strategies.base import StockData, Strategy
from app.core.strategy_screener import _persist_strategy_results
from app.db.models import MarketData, Stock
from app.db.session import SessionLocal

#: Strategi yang divalidasi historis (5 teknikal). Urut sesuai registry.
TECHNICAL_KEYS: tuple[str, ...] = (
    "bsjp",
    "bpjs",
    "breakout",
    "trend_following",
    "potential_reversal",
)

#: Window trailing (bar) yang berakhir di tanggal yang dievaluasi. Cukup untuk
#: MA200 (lookback terpanjang) + buffer; menjaga biaya per-tanggal tetap bounded
#: alih-alih O(seluruh sejarah) di tiap langkah.
LOOKBACK = 220


def get_technical_strategies() -> list[Strategy]:
    """Objek strategi teknikal dari registry (urut TECHNICAL_KEYS)."""
    out: list[Strategy] = []
    for key in TECHNICAL_KEYS:
        strat = registry.get(key)
        if strat is None:  # registry tak lengkap → konfigurasi salah
            raise KeyError(f"Strategi '{key}' tidak terdaftar di registry.")
        out.append(strat)
    return out


def reconstruct_ticker(
    ticker: str,
    bars: list[MarketData],
    strategies: list[Strategy],
    *,
    start: date | None = None,
    end: date | None = None,
    only_passed: bool = True,
) -> tuple[int, int, list[dict]]:
    """Jalankan strategi point-in-time atas seluruh tanggal SATU ticker (DB-free).

    Mengembalikan (evaluations, passes, rows) di mana `rows` siap di-upsert ke
    strategy_results. `evaluations` = total (tanggal × strategi) yang bisa
    dinilai; `passes` = yang lolos.
    """
    rows: list[dict] = []
    evaluations = 0
    passes = 0

    # i = indeks bar "hari ini"; mulai 1 agar selalu ada bar sebelumnya.
    for i in range(1, len(bars)):
        d = bars[i].date
        if start is not None and d < start:
            continue
        if end is not None and d > end:
            break  # bar urut kronologis → sisanya pasti > end

        window = bars[max(0, i - LOOKBACK + 1) : i + 1]
        data = StockData(ticker=ticker, bars=window, fundamentals=None)

        for strat in strategies:
            result = strat.run(data)
            if not result.evaluated:
                continue
            evaluations += 1
            if result.passed:
                passes += 1
            elif only_passed:
                continue
            rows.append(
                {
                    "date": d,
                    "ticker": ticker,
                    "strategy": strat.key,
                    "passed": result.passed,
                    "matched_criteria": result.matched_criteria,
                    "skipped_criteria": result.skipped_criteria,
                }
            )

    return evaluations, passes, rows


def _ticker_universe(db: Session, tickers: list[str] | None, limit: int | None) -> list[str]:
    if tickers:
        return [t.strip().upper() for t in tickers if not is_index(t)]
    stmt = select(Stock.ticker).order_by(Stock.ticker)
    if limit:
        stmt = stmt.limit(limit)
    return [t for t in db.scalars(stmt) if not is_index(t)]


def _load_bars(db: Session, ticker: str) -> list[MarketData]:
    return list(
        db.scalars(
            select(MarketData).where(MarketData.ticker == ticker).order_by(MarketData.date)
        )
    )


def reconstruct(
    db: Session,
    *,
    tickers: list[str] | None = None,
    limit: int | None = None,
    start: date | None = None,
    end: date | None = None,
    only_passed: bool = True,
    persist: bool = True,
    batch_size: int = 5000,
    progress: bool = True,
) -> dict:
    """Rekonstruksi seluruh universe. Memuat & memproses per-ticker (hemat memori),
    mem-persist baris dalam batch agar idempoten & tidak menahan transaksi besar.
    """
    strategies = get_technical_strategies()
    universe = _ticker_universe(db, tickers, limit)

    total_eval = 0
    total_pass = 0
    total_persisted = 0
    batch: list[dict] = []

    for idx, ticker in enumerate(universe, start=1):
        bars = _load_bars(db, ticker)
        evals, passes, rows = reconstruct_ticker(
            ticker, bars, strategies, start=start, end=end, only_passed=only_passed
        )
        total_eval += evals
        total_pass += passes
        if persist:
            batch.extend(rows)
            if len(batch) >= batch_size:
                total_persisted += _persist_strategy_results(db, batch)
                batch = []
        else:
            total_persisted += len(rows)
        if progress:
            print(
                f"  [{idx:>3}/{len(universe)}] {ticker:<6} "
                f"bars={len(bars):<5} eval={evals:<6} pass={passes}"
            )

    if persist and batch:
        total_persisted += _persist_strategy_results(db, batch)

    return {
        "tickers": len(universe),
        "evaluations": total_eval,
        "passes": total_pass,
        "persisted": total_persisted,
        "only_passed": only_passed,
    }


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Rekonstruksi strategy_results point-in-time (Phase 4 Day 2)."
    )
    parser.add_argument("--ticker", nargs="+", help="Ticker spesifik (mis. BBCA BMRI).")
    parser.add_argument("--limit", type=int, help="Batasi N ticker pertama dari stocks.")
    parser.add_argument("--start", type=date.fromisoformat, help="Tanggal mulai (YYYY-MM-DD).")
    parser.add_argument("--end", type=date.fromisoformat, help="Tanggal akhir (YYYY-MM-DD).")
    parser.add_argument(
        "--all",
        dest="all_rows",
        action="store_true",
        help="Simpan juga baris GAGAL (default: hanya yang lolos).",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Hitung saja, jangan tulis ke DB."
    )
    args = parser.parse_args()

    if SessionLocal is None:
        raise SystemExit("DATABASE_URL belum diset di backend/.env")

    db = SessionLocal()
    try:
        print("Mulai rekonstruksi histori (5 strategi teknikal, point-in-time)...")
        summary = reconstruct(
            db,
            tickers=args.ticker,
            limit=args.limit,
            start=args.start,
            end=args.end,
            only_passed=not args.all_rows,
            persist=not args.dry_run,
        )
        print(
            f"\nSelesai: {summary['tickers']} ticker, "
            f"{summary['evaluations']:,} evaluasi, {summary['passes']:,} lolos, "
            f"{summary['persisted']:,} baris {'dihitung' if args.dry_run else 'tersimpan'}."
        )
    finally:
        db.close()


if __name__ == "__main__":
    _main()
