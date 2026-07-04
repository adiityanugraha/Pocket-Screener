"""Strategy Benchmark Engine (Phase 4, Day 6).

Menggabungkan metrik SEMUA strategi tervalidasi (dari performance_metrics) ke
satu tabel berdampingan + baris pembanding PASAR (IHSG buy-and-hold) agar
terlihat strategi mana yang benar-benar mengalahkan pasar.

Pembanding IHSG dihitung dengan basis SAMA (kohort non-overlap H hari,
anualisasi 252/H) namun TANPA biaya transaksi - karena buy-and-hold hanya
sekali beli & sekali jual (cost amortisasi ~nol), berbeda dari strategi yang
trading berulang. Ini membuat perbandingan adil: "apakah trading aktif (setelah
biaya) mengalahkan memegang indeks secara pasif?".

Hasil di-persist ke strategy_performance (termasuk baris strategy='ihsg').
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MarketData
from app.quant import performance_metrics as pm

MARKET_TICKER = "IHSG"
MARKET_LABEL = "IHSG (Buy & Hold)"


def index_cohort_returns(
    db: Session,
    ticker: str = MARKET_TICKER,
    *,
    hold: int = pm.DEFAULT_HOLD,
    calendar: tuple[list, dict] | None = None,
) -> tuple[list, list[float]]:
    """Return buy-and-hold indeks, di-sample tiap `hold` hari bursa (no cost).

    Mengikuti grid blok yang sama dengan strategi: sampel pada indeks kalender
    0, hold, 2*hold, ...; return antar-sampel = close[t+1]/close[t]-1.
    """
    cal_dates, _ = calendar if calendar is not None else pm._trading_calendar(db)
    rows = db.execute(
        select(MarketData.date, MarketData.close)
        .where(MarketData.ticker == ticker)
        .order_by(MarketData.date)
    ).all()
    close_by_date = {d: c for d, c in rows if c is not None}

    samples = []
    for i in range(0, len(cal_dates), hold):
        d = cal_dates[i]
        c = close_by_date.get(d)
        if c is not None:
            samples.append((d, c))

    dates, returns = [], []
    for k in range(1, len(samples)):
        (_, c0), (d1, c1) = samples[k - 1], samples[k]
        if c0 and c0 > 0:
            dates.append(d1)
            returns.append(c1 / c0 - 1.0)
    return dates, returns


def _row(strategy: str, name: str | None, metrics: dict, n_periods: int, is_benchmark: bool) -> dict:
    return {
        "strategy": strategy,
        "name": name,
        "is_benchmark": is_benchmark,
        "n_periods": n_periods,
        "metrics": metrics,
    }


def compute_benchmark(
    db: Session, *, hold: int = pm.DEFAULT_HOLD, persist: bool = True
) -> dict:
    """Rakit tabel benchmark: tiap strategi vs IHSG, plus flag mengalahkan pasar."""
    calendar = pm._trading_calendar(db)

    rows: list[dict] = []
    for strategy in pm.VALIDATED_STRATEGIES:
        res = pm.compute_for_strategy(db, strategy, hold=hold, calendar=calendar)
        if persist:
            pm.persist_performance(db, strategy, res["metrics"], period="ALL")
        rows.append(
            _row(strategy, pm.strategy_display_name(strategy), res["metrics"],
                 res["n_periods"], is_benchmark=False)
        )

    idates, irets = index_cohort_returns(db, hold=hold, calendar=calendar)
    imetrics = pm.compute_metrics(irets, pm.TRADING_DAYS / hold)
    if persist:
        pm.persist_performance(db, "ihsg", imetrics, period="ALL")
    market = _row("ihsg", MARKET_LABEL, imetrics, len(irets), is_benchmark=True)

    # Flag mengalahkan pasar (CAGR & risk-adjusted).
    for r in rows:
        r["beats_market_cagr"] = r["metrics"]["cagr"] > imetrics["cagr"]
        r["beats_market_sharpe"] = r["metrics"]["sharpe_ratio"] > imetrics["sharpe_ratio"]

    rows.sort(key=lambda r: r["metrics"]["cagr"], reverse=True)
    return {"hold": hold, "market": market, "strategies": rows}


def _main() -> None:
    from app.db.session import SessionLocal

    if SessionLocal is None:
        raise SystemExit("DATABASE_URL belum diset di backend/.env")
    db = SessionLocal()
    try:
        print(f"Menghitung benchmark (hold={pm.DEFAULT_HOLD})...")
        result = compute_benchmark(db, persist=True)
        m = result["market"]["metrics"]
        print(f"  {'PASAR IHSG':<20} CAGR={m['cagr']*100:6.2f}% Sharpe={m['sharpe_ratio']:5.2f}")
        for r in result["strategies"]:
            mm = r["metrics"]
            beat = "BEAT" if r["beats_market_cagr"] else "----"
            print(
                f"  {r['strategy']:<20} CAGR={mm['cagr']*100:6.2f}% "
                f"Sharpe={mm['sharpe_ratio']:5.2f} [{beat} market]"
            )
        print("Selesai. Tersimpan ke strategy_performance (+baris ihsg).")
    finally:
        db.close()


if __name__ == "__main__":
    _main()
