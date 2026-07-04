"""Walk-Forward Backtesting (Phase 4, Day 11).

Menguji STABILITAS performa strategi antar periode (out-of-sample) untuk
mendeteksi overfitting / ketergantungan rezim. Skema ANCHORED: train tumbuh,
tiap tahun berikutnya menjadi fold TEST. Hanya periode TEST yang dijahit menjadi
kurva out-of-sample.

CATATAN PENTING: strategi Phase 3 ini RULE-BASED tanpa parameter yang di-fit,
jadi window "train" tidak menyetel apa pun - perannya murni memastikan tiap fold
diuji secara KRONOLOGIS ke depan (data train selalu mendahului test). Nilai
walk-forward di sini = melihat apakah edge KONSISTEN dari tahun ke tahun, bukan
optimasi parameter (blueprint mengakui hal ini).

Memakai seri return kohort 30-hari yang sama dengan Performance/Equity (Day 4-5).
Per fold (tahun test): annual return, winrate, max drawdown, jumlah periode.
Ringkasan OOS: CAGR, total return, max drawdown, winrate, + metrik konsistensi
(rasio tahun positif, deviasi return tahunan, tahun terbaik/terburuk).
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import date

from sqlalchemy.orm import Session

from app.quant import performance_metrics as pm

DEFAULT_MIN_TRAIN_YEARS = 1


def _group_by_year(
    dates: list[date], returns: list[float]
) -> "OrderedDict[int, list[float]]":
    """Return per tahun kalender, mempertahankan urutan kronologis."""
    grouped: OrderedDict[int, list[float]] = OrderedDict()
    for d, r in zip(dates, returns):
        grouped.setdefault(d.year, []).append(r)
    return grouped


def _period_metrics(returns: list[float]) -> dict:
    """Metrik satu fold/tahun: annual return (kompon), winrate, max drawdown."""
    equity = pm.to_equity(returns)
    annual_return = equity[-1] - 1.0 if equity else 0.0
    return {
        "annual_return": annual_return,
        "winrate": pm.winrate(returns),
        "max_drawdown": pm.max_drawdown(equity),
        "n_periods": len(returns),
    }


def _consistency(annual_returns: list[float]) -> dict:
    """Metrik konsistensi antar-tahun untuk mendeteksi ketergantungan rezim."""
    if not annual_returns:
        return {
            "positive_year_ratio": 0.0,
            "annual_return_std": 0.0,
            "best_year": 0.0,
            "worst_year": 0.0,
        }
    positives = sum(1 for r in annual_returns if r > 0)
    return {
        "positive_year_ratio": positives / len(annual_returns),
        "annual_return_std": pm._std(annual_returns),
        "best_year": max(annual_returns),
        "worst_year": min(annual_returns),
    }


def walk_forward(
    db: Session,
    strategy: str,
    *,
    hold: int = pm.DEFAULT_HOLD,
    min_train_years: int = DEFAULT_MIN_TRAIN_YEARS,
    calendar: tuple[list[date], dict[date, int]] | None = None,
) -> dict:
    """Walk-forward anchored: fold test per tahun + ringkasan out-of-sample."""
    calendar = calendar or pm._trading_calendar(db)
    dates, returns = pm.cohort_returns(db, strategy, hold=hold, calendar=calendar)
    by_year = _group_by_year(dates, returns)
    years = list(by_year.keys())

    test_years = years[min_train_years:]
    folds: list[dict] = []
    oos_returns: list[float] = []
    annual_returns: list[float] = []

    for i, year in enumerate(test_years):
        year_returns = by_year[year]
        metrics = _period_metrics(year_returns)
        train_years = years[: min_train_years + i]
        folds.append(
            {
                "period": str(year),
                "train_start": str(train_years[0]),
                "train_end": str(train_years[-1]),
                **metrics,
            }
        )
        oos_returns.extend(year_returns)
        annual_returns.append(metrics["annual_return"])

    # Ringkasan out-of-sample (jahitan seluruh periode test).
    n_years = len(test_years)
    if oos_returns:
        equity = pm.to_equity(oos_returns)
        total_return = equity[-1] - 1.0
        oos_cagr = pm.cagr(equity[-1], n_years) if n_years > 0 else 0.0
        oos_mdd = pm.max_drawdown(equity)
        oos_winrate = pm.winrate(oos_returns)
    else:
        total_return = oos_cagr = oos_mdd = oos_winrate = 0.0

    return {
        "strategy": strategy,
        "name": pm.strategy_display_name(strategy),
        "hold": hold,
        "mode": "anchored",
        "min_train_years": min_train_years,
        "folds": folds,
        "out_of_sample": {
            "start": str(test_years[0]) if test_years else None,
            "end": str(test_years[-1]) if test_years else None,
            "total_years": n_years,
            "cagr": oos_cagr,
            "total_return": total_return,
            "max_drawdown": oos_mdd,
            "winrate": oos_winrate,
            "n_periods": len(oos_returns),
            "consistency": _consistency(annual_returns),
        },
    }


def _main() -> None:
    import sys

    from app.db.session import SessionLocal

    if SessionLocal is None:
        raise SystemExit("DATABASE_URL belum diset di backend/.env")
    strat = sys.argv[1] if len(sys.argv) > 1 else "trend_following"
    db = SessionLocal()
    try:
        r = walk_forward(db, strat)
        print(f"Walk-Forward {strat} (anchored, hold={r['hold']}):")
        print(f"  {'Tahun':<6}{'Return':>9}{'Winrate':>9}{'MaxDD':>9}{'n':>4}")
        for f in r["folds"]:
            print(
                f"  {f['period']:<6}{f['annual_return']*100:>8.1f}%"
                f"{f['winrate']*100:>8.0f}%{f['max_drawdown']*100:>8.1f}%{f['n_periods']:>4}"
            )
        oos = r["out_of_sample"]
        c = oos["consistency"]
        print(
            f"  OOS {oos['start']}-{oos['end']}: CAGR={oos['cagr']*100:+.1f}% "
            f"MaxDD={oos['max_drawdown']*100:+.1f}% "
            f"tahun_positif={c['positive_year_ratio']*100:.0f}%"
        )
    finally:
        db.close()


if __name__ == "__main__":
    _main()
