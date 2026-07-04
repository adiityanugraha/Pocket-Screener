"""Market Breadth - konteks pasar menyeluruh (sehat atau hanya segelintir naik).

Sesuai blueprint Phase 2 (Market Breadth Dashboard), metrik:
  - Jumlah saham naik / turun (advancers / decliners)
  - Bullish Ratio = advancers / (advancers + decliners)
  - Top Gainers & Losers
  - Sector Performance (rata-rata perubahan per sektor)

Modul ini MURNI (tanpa DB/cache). API (market_breadth.py) yang merakit perubahan
harian tiap saham dari market_data lalu menyimpan hasil ke PostgreSQL.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TOP_N = 5


@dataclass(frozen=True)
class StockChange:
    ticker: str
    name: str | None
    sector: str | None
    close: float
    change_pct: float  # rasio harian (0.024 = +2.4%)


@dataclass(frozen=True)
class BreadthResult:
    date: str
    advancers: int
    decliners: int
    unchanged: int
    total: int
    bullish_ratio: float | None  # advancers / (advancers + decliners)
    top_gainers: list[dict]
    top_losers: list[dict]
    sector_performance: list[dict]


def _to_dict(change: StockChange) -> dict:
    return {
        "ticker": change.ticker,
        "name": change.name,
        "close": round(change.close, 2),
        "change_pct": round(change.change_pct, 4),
    }


def compute_breadth(
    changes: list[StockChange], date: str, top_n: int = DEFAULT_TOP_N
) -> BreadthResult:
    """Hitung ringkasan breadth dari perubahan harian seluruh saham."""
    advancers = sum(1 for c in changes if c.change_pct > 0)
    decliners = sum(1 for c in changes if c.change_pct < 0)
    unchanged = sum(1 for c in changes if c.change_pct == 0)
    total = len(changes)

    denom = advancers + decliners
    bullish_ratio = round(advancers / denom, 4) if denom else None

    by_gain = sorted(changes, key=lambda c: c.change_pct, reverse=True)
    top_gainers = [_to_dict(c) for c in by_gain[:top_n] if c.change_pct > 0]
    top_losers = [_to_dict(c) for c in by_gain[::-1][:top_n] if c.change_pct < 0]

    # Performa sektor: rata-rata perubahan, diurutkan terkuat -> terlemah.
    sector_changes: dict[str, list[float]] = {}
    for change in changes:
        sector = change.sector or "Unknown"
        sector_changes.setdefault(sector, []).append(change.change_pct)

    sector_performance = sorted(
        (
            {
                "sector": sector,
                "avg_change_pct": round(sum(values) / len(values), 4),
                "count": len(values),
            }
            for sector, values in sector_changes.items()
        ),
        key=lambda item: item["avg_change_pct"],
        reverse=True,
    )

    return BreadthResult(
        date=date,
        advancers=advancers,
        decliners=decliners,
        unchanged=unchanged,
        total=total,
        bullish_ratio=bullish_ratio,
        top_gainers=top_gainers,
        top_losers=top_losers,
        sector_performance=sector_performance,
    )
