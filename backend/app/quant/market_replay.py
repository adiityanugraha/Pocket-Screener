"""Market Replay Engine (Phase 4, Day 7).

Memutar ulang hasil screening pada tanggal historis pilihan: untuk tiap strategi
teknikal tervalidasi, tampilkan kandidat yang LOLOS pada tanggal itu beserta
performa forward (+1/+3/+7/+30 hari) - bukti nyata kualitas screener.

Sumber: tabel replay_history (sudah dimaterialisasi Day 3: price tanggal
screening + return forward net). Engine ini hanya membaca & merakit (cepat,
tanpa hitung ulang). Nilai transaksi (turnover) di-join dari market_data sebagai
proxy likuiditas untuk mengurutkan "Top" kandidat.

Strategi fundamental DIKECUALIKAN (tidak divalidasi historis) - lihat
app/quant/__init__.py.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db.models import MarketData, ReplayHistory, Stock
from app.quant.reconstruct import TECHNICAL_KEYS


def replay_date_range(db: Session) -> tuple[date | None, date | None]:
    """(tanggal paling awal, paling akhir) yang punya data replay."""
    row = db.execute(
        select(func.min(ReplayHistory.date), func.max(ReplayHistory.date))
    ).one()
    return row[0], row[1]


def _candidate(rh: ReplayHistory, name: str | None, sector: str | None, value: float | None) -> dict:
    return {
        "ticker": rh.ticker,
        "name": name,
        "sector": sector,
        "price": rh.price,
        "value": value,
        "ret": {
            "1d": rh.ret_1d,
            "3d": rh.ret_3d,
            "7d": rh.ret_7d,
            "30d": rh.ret_30d,
        },
    }


def replay_on_date(db: Session, target_date: date, *, limit: int = 10) -> dict:
    """Rakit hasil replay untuk satu tanggal: kandidat per strategi + return forward.

    Semua strategi teknikal disertakan (list kosong bila tak ada kandidat lolos
    pada tanggal itu). Tiap grup diurutkan menurun berdasarkan turnover.
    """
    stmt = (
        select(ReplayHistory, Stock.name, Stock.sector, MarketData.value)
        .join(Stock, Stock.ticker == ReplayHistory.ticker, isouter=True)
        .join(
            MarketData,
            and_(
                MarketData.ticker == ReplayHistory.ticker,
                MarketData.date == ReplayHistory.date,
            ),
            isouter=True,
        )
        .where(ReplayHistory.date == target_date)
    )

    buckets: dict[str, list[dict]] = {key: [] for key in TECHNICAL_KEYS}
    total = 0
    for rh, name, sector, value in db.execute(stmt):
        if rh.strategy not in buckets:
            continue
        buckets[rh.strategy].append(_candidate(rh, name, sector, value))
        total += 1

    for key, items in buckets.items():
        items.sort(key=lambda c: c["value"] or 0.0, reverse=True)
        buckets[key] = items[:limit]

    return {
        "date": target_date.isoformat(),
        "total_candidates": total,
        "strategies": buckets,
    }


def _main() -> None:
    import sys

    from app.db.session import SessionLocal

    if SessionLocal is None:
        raise SystemExit("DATABASE_URL belum diset di backend/.env")
    if len(sys.argv) < 2:
        raise SystemExit("Pakai: python -m app.quant.market_replay YYYY-MM-DD")

    target = date.fromisoformat(sys.argv[1])
    db = SessionLocal()
    try:
        result = replay_on_date(db, target)
        print(f"Replay {result['date']} - {result['total_candidates']} kandidat:")
        for key, items in result["strategies"].items():
            if items:
                print(f"  {key}:")
                for c in items:
                    r = c["ret"]
                    print(
                        f"    {c['ticker']:<6} price={c['price']:>8.0f} "
                        f"1d={_pct(r['1d'])} 7d={_pct(r['7d'])} 30d={_pct(r['30d'])}"
                    )
    finally:
        db.close()


def _pct(v: float | None) -> str:
    return f"{v*100:+5.1f}%" if v is not None else "  n/a"


if __name__ == "__main__":
    _main()
