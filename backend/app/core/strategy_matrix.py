"""Strategy Comparison Matrix (Phase 3 Day 8).

Membangun matriks saham x strategi dari tabel strategy_results (diisi
/api/screener/all, Day 7). Tiap sel punya TIGA keadaan, bukan dua:
  - True  : lolos strategi
  - False : dinilai tapi gagal
  - None  : TIDAK dinilai (data kurang, mis. saham tanpa fundamental) - beda
            makna dari "gagal", konsisten dgn flag `evaluated` di Strategy.

Logika murni (assemble_matrix) dipisah dari I/O DB (build_strategy_matrix) agar
mudah diuji tanpa database.
"""

from __future__ import annotations

from datetime import date as date_cls

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.strategies import registry
from app.db.models import Stock, StrategyResultRow


def assemble_matrix(
    rows: list,
    stock_map: dict,
    strategy_keys: list[str],
    min_passed: int = 1,
) -> tuple[list[dict], int]:
    """Rakit baris matriks dari hasil strategi (fungsi murni).

    rows         : objek dengan atribut .ticker, .strategy, .passed.
    stock_map    : ticker -> objek punya .name & .sector (boleh kosong).
    strategy_keys: urutan kolom strategi.
    min_passed   : saring saham yang lolos minimal N strategi.

    Mengembalikan (matrix, universe_evaluated).
    """
    by_ticker: dict[str, dict[str, bool]] = {}
    for row in rows:
        by_ticker.setdefault(row.ticker, {})[row.strategy] = row.passed

    matrix: list[dict] = []
    for ticker, results in by_ticker.items():
        # None untuk strategi yang tak punya baris (tidak dievaluasi).
        cells = {key: results.get(key) for key in strategy_keys}
        passed_strategies = [key for key in strategy_keys if results.get(key) is True]
        if len(passed_strategies) < min_passed:
            continue
        stock = stock_map.get(ticker)
        matrix.append(
            {
                "ticker": ticker,
                "name": stock.name if stock else None,
                "sector": stock.sector if stock else None,
                "results": cells,
                "passed_count": len(passed_strategies),
                "passed_strategies": passed_strategies,
            }
        )

    # Urut: terbanyak lolos dulu, lalu alfabetis ticker (stabil).
    matrix.sort(key=lambda m: (-m["passed_count"], m["ticker"]))
    return matrix, len(by_ticker)


def latest_result_date(db: Session) -> date_cls | None:
    return db.scalar(select(func.max(StrategyResultRow.date)))


def build_strategy_matrix(db: Session, min_passed: int = 1) -> dict:
    """Bangun matriks dari strategy_results tanggal TERBARU."""
    strategies = registry.all_strategies()
    strategy_keys = [s.key for s in strategies]
    columns = [s.describe() for s in strategies]

    target = latest_result_date(db)
    if target is None:  # belum ada hasil (screener/all belum pernah jalan)
        return {
            "date": None,
            "strategies": columns,
            "universe_evaluated": 0,
            "matrix": [],
        }

    rows = list(
        db.scalars(select(StrategyResultRow).where(StrategyResultRow.date == target))
    )
    stock_map = {stock.ticker: stock for stock in db.scalars(select(Stock))}
    matrix, universe = assemble_matrix(rows, stock_map, strategy_keys, min_passed)

    return {
        "date": target.isoformat(),
        "strategies": columns,
        "universe_evaluated": universe,
        "matrix": matrix,
    }
