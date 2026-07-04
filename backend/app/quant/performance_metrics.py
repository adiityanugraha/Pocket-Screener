"""Advanced Performance Metrics Engine (Phase 4, Day 4).

Menghitung metrik kualitas strategi dari trade log (replay_history, Day 3):
CAGR, Max Drawdown, Sharpe, Sortino, Calmar, Profit Factor, Recovery Factor,
Winrate. Hasil disimpan ke strategy_performance (period="ALL") dan disajikan
GET /api/performance/{strategy}.

============================================================================
METODOLOGI RETURN SERIES - "rebalancing kohort non-overlap" (transparan)
============================================================================
Trade log hanya punya return pada horizon diskrit (1/3/7/30 hari). Untuk
membentuk seri return yang bisa dianualisasi DENGAN biaya yang adil DAN tanpa
distorsi, dipakai model rebalancing periodik:

  - Kalender bursa dibagi menjadi BLOK non-overlap selebar H hari bursa
    (H = holding horizon, default 30).
  - Return satu blok = RATA-RATA return net r_H seluruh kandidat yang dientry
    dalam blok itu (basket equal-weight; r_H sudah dikurangi satu biaya
    round-trip 0,3% di Day 3). Blok tanpa sinyal = 0% (kas).
  - Equity curve = perkalian kumulatif (1 + return blok). Anualisasi memakai
    periods_per_year = 252 / H.

Mengapa model ini (bukan amortisasi harian):
  - Memakai return H-hari AKTUAL → TIDAK menambah volatility-drag sintetis dari
    memaksa return melewati jalur harian buatan.
  - Non-overlap → tiap trade dihitung sekali, tanpa reweighting akibat posisi
    bertumpuk. Basket equal-weight per blok memberi diversifikasi alami.
  - Biaya dibayar sekali per trade → adil untuk strategi tahan-lama.

Konsekuensi yang DISENGAJA & jujur:
  - H seragam lintas strategi (default 30) agar benchmark apple-to-apple (Day 6).
    Horizon 1/3/7 tersedia via query untuk eksplorasi; strategi teknikal ini
    menunjukkan edge nyata pada ~30 hari (horizon pendek tergerus biaya).
  - Strategi yang jarang memberi sinyal → banyak blok kas → CAGR/volatilitas
    rendah; realistis untuk "strategi yang dijalankan apa adanya".

Rf (risk-free): default 6%/tahun (≈ yield SBN), dikonversi per-blok. Configurable.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date

from sqlalchemy import distinct, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.strategies import registry
from app.db.models import MarketData, ReplayHistory, StrategyPerformance
from app.quant.forward_returns import _HORIZON_COLUMN
from app.quant.reconstruct import TECHNICAL_KEYS

TRADING_DAYS = 252
RISK_FREE_ANNUAL = 0.06
DEFAULT_HOLD = 30  # horizon holding kanonik (hari bursa) - lihat METODOLOGI

# Strategi yang divalidasi historis (alias agar jelas di endpoint).
VALIDATED_STRATEGIES: tuple[str, ...] = TECHNICAL_KEYS


# --------------------------------------------------------------------------- #
# Metrik MURNI (tanpa DB) - beroperasi atas seri return per-periode / equity.
# --------------------------------------------------------------------------- #
def to_equity(returns: list[float], start: float = 1.0) -> list[float]:
    """Equity curve dari seri return (perkalian kumulatif)."""
    equity = []
    value = start
    for r in returns:
        value *= 1.0 + r
        equity.append(value)
    return equity


def max_drawdown(equity: list[float]) -> float:
    """Drawdown terdalam (<= 0) dari puncak berjalan."""
    if not equity:
        return 0.0
    peak = equity[0]
    worst = 0.0
    for v in equity:
        if v > peak:
            peak = v
        if peak > 0:
            dd = v / peak - 1.0
            if dd < worst:
                worst = dd
    return worst


def cagr(equity_end: float, years: float) -> float:
    """Compound Annual Growth Rate. equity_end relatif terhadap modal awal 1.0."""
    if years <= 0 or equity_end <= 0:
        return 0.0
    return equity_end ** (1.0 / years) - 1.0


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float]) -> float:
    """Standar deviasi populasi."""
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def sharpe(returns: list[float], rf_period: float, periods_per_year: float) -> float:
    if len(returns) < 2:
        return 0.0
    excess = [r - rf_period for r in returns]
    sd = _std(returns)
    if sd == 0:
        return 0.0
    return _mean(excess) / sd * math.sqrt(periods_per_year)


def sortino(returns: list[float], rf_period: float, periods_per_year: float) -> float:
    if len(returns) < 2:
        return 0.0
    excess = [r - rf_period for r in returns]
    downside = [min(0.0, r - rf_period) for r in returns]
    dd = math.sqrt(sum(d * d for d in downside) / len(returns))
    if dd == 0:
        return 0.0
    return _mean(excess) / dd * math.sqrt(periods_per_year)


def calmar(cagr_value: float, mdd: float) -> float:
    if mdd == 0:
        return 0.0
    return cagr_value / abs(mdd)


def profit_factor(returns: list[float]) -> float:
    gross_profit = sum(r for r in returns if r > 0)
    gross_loss = -sum(r for r in returns if r < 0)
    if gross_loss == 0:
        return 0.0
    return gross_profit / gross_loss


def recovery_factor(total_return: float, mdd: float) -> float:
    if mdd == 0:
        return 0.0
    return total_return / abs(mdd)


def winrate(returns: list[float]) -> float:
    """Fraksi periode AKTIF (return != 0) yang positif."""
    active = [r for r in returns if r != 0.0]
    if not active:
        return 0.0
    return sum(1 for r in active if r > 0) / len(active)


def compute_metrics(
    returns: list[float],
    periods_per_year: float,
    rf_annual: float = RISK_FREE_ANNUAL,
) -> dict:
    """Rangkai seluruh metrik dari seri return per-periode + frekuensi tahunannya."""
    keys = (
        "cagr", "winrate", "sharpe_ratio", "sortino_ratio", "calmar_ratio",
        "max_drawdown", "profit_factor", "recovery_factor",
    )
    if not returns:
        return {k: 0.0 for k in keys}

    equity = to_equity(returns)
    total_return = equity[-1] - 1.0
    years = len(returns) / periods_per_year if periods_per_year > 0 else 0.0
    rf_period = (1.0 + rf_annual) ** (1.0 / periods_per_year) - 1.0

    mdd = max_drawdown(equity)
    cagr_value = cagr(equity[-1], years)
    return {
        "cagr": cagr_value,
        "winrate": winrate(returns),
        "sharpe_ratio": sharpe(returns, rf_period, periods_per_year),
        "sortino_ratio": sortino(returns, rf_period, periods_per_year),
        "calmar_ratio": calmar(cagr_value, mdd),
        "max_drawdown": mdd,
        "profit_factor": profit_factor(returns),
        "recovery_factor": recovery_factor(total_return, mdd),
    }


# --------------------------------------------------------------------------- #
# Lapisan DB - bangun seri return kohort dari replay_history.
# --------------------------------------------------------------------------- #
def _trading_calendar(db: Session) -> tuple[list[date], dict[date, int]]:
    """Kalender bursa global (distinct date market_data) + peta date->indeks."""
    dates = list(db.scalars(select(distinct(MarketData.date)).order_by(MarketData.date)))
    return dates, {d: i for i, d in enumerate(dates)}


def cohort_returns(
    db: Session,
    strategy: str,
    *,
    hold: int = DEFAULT_HOLD,
    calendar: tuple[list[date], dict[date, int]] | None = None,
) -> tuple[list[date], list[float]]:
    """Seri (dates, returns) blok non-overlap selebar `hold` hari bursa.

    returns[i] = rata-rata r_hold kandidat yang dientry di blok ke-i (0% bila
    blok tak punya sinyal). dates[i] = tanggal awal blok. Lihat METODOLOGI.
    """
    if hold not in _HORIZON_COLUMN:
        raise ValueError(f"hold={hold} bukan horizon tersedia {tuple(_HORIZON_COLUMN)}.")
    cal_dates, cal_index = calendar if calendar is not None else _trading_calendar(db)
    column = getattr(ReplayHistory, _HORIZON_COLUMN[hold])

    trades = db.execute(
        select(ReplayHistory.date, column)
        .where(ReplayHistory.strategy == strategy)
        .where(column.is_not(None))
        .order_by(ReplayHistory.date)
    ).all()
    if not trades:
        return [], []

    blocks: dict[int, list[float]] = defaultdict(list)
    for entry_date, r_h in trades:
        gi = cal_index.get(entry_date)
        if gi is None:
            continue
        blocks[gi // hold].append(r_h)
    if not blocks:
        return [], []

    b_min, b_max = min(blocks), max(blocks)
    n = len(cal_dates)
    dates: list[date] = []
    returns: list[float] = []
    for b in range(b_min, b_max + 1):
        rs = blocks.get(b)
        returns.append(sum(rs) / len(rs) if rs else 0.0)
        dates.append(cal_dates[min(b * hold, n - 1)])
    return dates, returns


def compute_for_strategy(
    db: Session,
    strategy: str,
    *,
    hold: int = DEFAULT_HOLD,
    rf_annual: float = RISK_FREE_ANNUAL,
    calendar: tuple[list[date], dict[date, int]] | None = None,
) -> dict:
    """Metrik lengkap + metadata (n_periods, active, rentang, hold) per strategi."""
    dates, returns = cohort_returns(db, strategy, hold=hold, calendar=calendar)
    periods_per_year = TRADING_DAYS / hold
    metrics = compute_metrics(returns, periods_per_year, rf_annual=rf_annual)
    return {
        "metrics": metrics,
        "n_periods": len(returns),
        "active_periods": sum(1 for r in returns if r != 0.0),
        "start": dates[0].isoformat() if dates else None,
        "end": dates[-1].isoformat() if dates else None,
        "hold": hold,
        "periods_per_year": round(periods_per_year, 2),
    }


def persist_performance(
    db: Session, strategy: str, metrics: dict, period: str = "ALL"
) -> None:
    """Upsert metrik ke strategy_performance (idempoten per strategy+period)."""
    stmt = pg_insert(StrategyPerformance).values(
        strategy=strategy, period=period, **metrics
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_strategy_performance_strategy_period",
        set_={k: stmt.excluded[k] for k in metrics},
    )
    db.execute(stmt)
    db.commit()


def compute_all(
    db: Session, *, hold: int = DEFAULT_HOLD, persist: bool = True, progress: bool = True
) -> dict[str, dict]:
    """Hitung (dan simpan) metrik seluruh strategi tervalidasi. Dipakai job malam."""
    calendar = _trading_calendar(db)
    out: dict[str, dict] = {}
    for strategy in VALIDATED_STRATEGIES:
        result = compute_for_strategy(db, strategy, hold=hold, calendar=calendar)
        if persist:
            persist_performance(db, strategy, result["metrics"], period="ALL")
        out[strategy] = result
        if progress:
            m = result["metrics"]
            print(
                f"  {strategy:<20} CAGR={m['cagr']*100:6.2f}% "
                f"Sharpe={m['sharpe_ratio']:5.2f} MaxDD={m['max_drawdown']*100:6.2f}% "
                f"PF={m['profit_factor']:.2f} periods={result['n_periods']}"
            )
    return out


def strategy_display_name(strategy: str) -> str | None:
    strat = registry.get(strategy)
    return strat.name if strat else None


def _main() -> None:
    from app.db.session import SessionLocal

    if SessionLocal is None:
        raise SystemExit("DATABASE_URL belum diset di backend/.env")
    db = SessionLocal()
    try:
        print(f"Menghitung performance metrics (hold={DEFAULT_HOLD}, Rf={RISK_FREE_ANNUAL})...")
        compute_all(db, persist=True)
        print("Selesai. Tersimpan ke strategy_performance (period=ALL).")
    finally:
        db.close()


if __name__ == "__main__":
    _main()
