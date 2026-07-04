"""Monte Carlo Simulation (Phase 4, Day 10).

Mengukur SEBARAN kemungkinan hasil masa depan dengan me-resample (bootstrap)
return historis strategi - bukan satu lintasan tunggal. Sumber sampel = seri
return kohort 30-hari (sama dgn Performance/Equity, termasuk blok kas 0%), agar
konsisten dengan metrik lain.

Metode:
  - 1 tahun ≈ 252/hold blok (default 8,4 → dibulatkan per horizon).
  - Tiap lintasan: ambil n_periode return dengan PENGEMBALIAN dari distribusi
    historis, lalu kompon → total return horizon.
  - Ulang ribuan kali → rangkum ke persentil & probabilitas profit.

Seed tetap (default 42) → hasil reproducible (cache stabil). HASIL BUKAN
JAMINAN: berasumsi pola return historis berulang & independen antar-blok.
"""

from __future__ import annotations

import numpy as np
from sqlalchemy.orm import Session

from app.quant import performance_metrics as pm

DEFAULT_SIMULATIONS = 5000
DEFAULT_HORIZON_YEARS = 1.0
DEFAULT_SEED = 42
HISTOGRAM_BINS = 30


def simulate(
    returns: list[float],
    n_periods: int,
    n_sims: int = DEFAULT_SIMULATIONS,
    seed: int = DEFAULT_SEED,
) -> np.ndarray:
    """Bootstrap n_sims lintasan; tiap lintasan kompon n_periods return acak.

    Mengembalikan array total return per lintasan. Kosong bila input tak cukup.
    """
    if not returns or n_periods < 1 or n_sims < 1:
        return np.empty(0)
    base = np.asarray(returns, dtype=float)
    rng = np.random.default_rng(seed)
    draws = rng.choice(base, size=(n_sims, n_periods), replace=True)
    return np.prod(1.0 + draws, axis=1) - 1.0


def summarize(path_returns: np.ndarray) -> dict:
    """Rangkum sebaran: probability of profit, persentil, mean + histogram."""
    if path_returns.size == 0:
        return {
            "probability_of_profit": 0.0,
            "mean": 0.0,
            "percentiles": {k: 0.0 for k in ("p5", "p25", "p50", "p75", "p95")},
            "histogram": [],
        }
    p5, p25, p50, p75, p95 = (
        float(np.percentile(path_returns, q)) for q in (5, 25, 50, 75, 95)
    )
    counts, edges = np.histogram(path_returns, bins=HISTOGRAM_BINS)
    histogram = [
        {"start": round(float(edges[i]), 4), "end": round(float(edges[i + 1]), 4),
         "count": int(counts[i])}
        for i in range(len(counts))
    ]
    return {
        "probability_of_profit": float(np.mean(path_returns > 0)),
        "mean": float(np.mean(path_returns)),
        "percentiles": {
            "p5": p5, "p25": p25, "p50": p50, "p75": p75, "p95": p95,
        },
        "histogram": histogram,
    }


def monte_carlo_strategy(
    db: Session,
    strategy: str,
    *,
    hold: int = pm.DEFAULT_HOLD,
    horizon_years: float = DEFAULT_HORIZON_YEARS,
    n_sims: int = DEFAULT_SIMULATIONS,
    seed: int = DEFAULT_SEED,
    calendar: tuple | None = None,
) -> dict:
    """Jalankan Monte Carlo untuk satu strategi + metadata."""
    calendar = calendar or pm._trading_calendar(db)
    _, returns = pm.cohort_returns(db, strategy, hold=hold, calendar=calendar)
    periods_per_year = pm.TRADING_DAYS / hold
    n_periods = max(1, round(periods_per_year * horizon_years))

    paths = simulate(returns, n_periods, n_sims=n_sims, seed=seed)
    summary = summarize(paths)
    return {
        "strategy": strategy,
        "name": pm.strategy_display_name(strategy),
        "hold": hold,
        "horizon_years": horizon_years,
        "n_periods": n_periods,
        "simulations": int(paths.size),
        "history_periods": len(returns),
        **summary,
    }


def _main() -> None:
    import sys

    from app.db.session import SessionLocal

    if SessionLocal is None:
        raise SystemExit("DATABASE_URL belum diset di backend/.env")
    strat = sys.argv[1] if len(sys.argv) > 1 else "trend_following"
    db = SessionLocal()
    try:
        r = monte_carlo_strategy(db, strat)
        pc = r["percentiles"]
        print(f"Monte Carlo {strat} (horizon {r['horizon_years']}thn, {r['simulations']} sim):")
        print(f"  Probability of Profit : {r['probability_of_profit']*100:.0f}%")
        print(f"  Worst Case (P5)       : {pc['p5']*100:+.1f}%")
        print(f"  Expected (median)     : {pc['p50']*100:+.1f}%")
        print(f"  Best Case (P95)       : {pc['p95']*100:+.1f}%")
    finally:
        db.close()


if __name__ == "__main__":
    _main()
