"""Equity Curve Engine (Phase 4, Day 5).

Memvisualkan pertumbuhan modal strategi dari waktu ke waktu beserta puncak
(high-water mark) dan drawdown. Memakai SERI RETURN YANG SAMA dengan Performance
Metrics (Day 4) - rebalancing kohort non-overlap H hari (lihat
performance_metrics.METODOLOGI) - sehingga nilai akhir equity konsisten dengan
CAGR/MaxDD yang dilaporkan di /api/performance.

Nilai disimpan TER-NORMALISASI (modal awal = 1.0) agар bebas dari asumsi
nominal; endpoint dapat menskala ke rupiah lewat query initial_capital.

Tabel: equity_curve (satu baris per strategy+date blok). Diisi job malam 18:00
(Day 13) atau on-demand via endpoint.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import EquityCurve
from app.quant import performance_metrics as pm

_UPSERT_COLUMNS = ("portfolio_value", "drawdown", "peak")


def build_curve(
    db: Session,
    strategy: str,
    *,
    hold: int = pm.DEFAULT_HOLD,
    calendar: tuple[list[date], dict[date, int]] | None = None,
) -> list[dict]:
    """Titik-titik equity curve (ternormalisasi, base 1.0) untuk satu strategi.

    Mengembalikan list {date, portfolio_value, peak, drawdown} per blok kohort.
    drawdown = portfolio_value/peak - 1 (<= 0). Kosong bila tak ada trade.
    """
    dates, returns = pm.cohort_returns(db, strategy, hold=hold, calendar=calendar)
    if not returns:
        return []

    points: list[dict] = []
    value = 1.0
    peak = 1.0
    for d, r in zip(dates, returns):
        value *= 1.0 + r
        peak = max(peak, value)
        drawdown = value / peak - 1.0 if peak > 0 else 0.0
        points.append(
            {
                "date": d,
                "portfolio_value": value,
                "peak": peak,
                "drawdown": drawdown,
            }
        )
    return points


def persist_curve(db: Session, strategy: str, points: list[dict]) -> int:
    """Upsert titik equity curve ke tabel equity_curve (idempoten per strategy+date)."""
    if not points:
        return 0
    rows = [{"strategy": strategy, **p} for p in points]
    stmt = pg_insert(EquityCurve).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_equity_curve_strategy_date",
        set_={col: stmt.excluded[col] for col in _UPSERT_COLUMNS},
    )
    db.execute(stmt)
    db.commit()
    return len(rows)


def curve_summary(points: list[dict]) -> dict:
    """Ringkasan kurva: nilai akhir, total return, max drawdown, recovery."""
    if not points:
        return {"final_value": 1.0, "total_return": 0.0, "max_drawdown": 0.0}
    final = points[-1]["portfolio_value"]
    mdd = min(p["drawdown"] for p in points)
    return {
        "final_value": final,
        "total_return": final - 1.0,
        "max_drawdown": mdd,
    }


def compute_all(
    db: Session, *, hold: int = pm.DEFAULT_HOLD, persist: bool = True, progress: bool = True
) -> dict[str, int]:
    """Bangun & simpan equity curve seluruh strategi tervalidasi (job malam)."""
    calendar = pm._trading_calendar(db)
    out: dict[str, int] = {}
    for strategy in pm.VALIDATED_STRATEGIES:
        points = build_curve(db, strategy, hold=hold, calendar=calendar)
        out[strategy] = persist_curve(db, strategy, points) if persist else len(points)
        if progress:
            s = curve_summary(points)
            print(
                f"  {strategy:<20} points={len(points):<4} "
                f"final={s['final_value']:.3f} maxDD={s['max_drawdown']*100:+.1f}%"
            )
    return out


def _main() -> None:
    from app.db.session import SessionLocal

    if SessionLocal is None:
        raise SystemExit("DATABASE_URL belum diset di backend/.env")
    db = SessionLocal()
    try:
        print(f"Membangun equity curve (hold={pm.DEFAULT_HOLD})...")
        compute_all(db, persist=True)
        print("Selesai. Tersimpan ke equity_curve.")
    finally:
        db.close()


if __name__ == "__main__":
    _main()
