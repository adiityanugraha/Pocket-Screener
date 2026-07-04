"""Risk Exposure Dashboard per STRATEGI (Phase 4, Day 8).

Berbeda dari Risk Meter Phase 2 (per-SAHAM), ini mengukur profil risiko sebuah
STRATEGI dari seri return historisnya (kohort 30 hari, sama dgn Day 4-6):

  - volatility   : volatilitas TER-ANUALISASI dari seri return strategi.
  - avg_atr_pct  : rata-rata ATR% (ATR/price) saham yang DIPILIH strategi -
                   seberapa bergejolak kandidatnya (dari market_data).
  - beta         : kepekaan return strategi terhadap IHSG (cov/var pasar),
                   atas blok yang sama-sama aktif.
  - max_drawdown : penurunan terdalam equity curve.
  - losing_streak: deret periode rugi beruntun terpanjang.

Lalu diklasifikasikan Low / Medium / High berdasarkan volatilitas & drawdown.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db.models import MarketData, ReplayHistory
from app.quant import benchmark as bench
from app.quant import performance_metrics as pm

# Ambang klasifikasi (volatilitas tahunan & |max drawdown|). Didokumentasikan
# agar transparan; disetel untuk strategi ekuitas IDX.
VOL_HIGH = 0.40
VOL_LOW = 0.25
DD_HIGH = 0.60
DD_LOW = 0.35


def longest_losing_streak(returns: list[float]) -> int:
    """Deret terpanjang periode AKTIF dengan return < 0 (kas/0 memutus deret)."""
    best = current = 0
    for r in returns:
        if r < 0:
            current += 1
            best = max(best, current)
        elif r > 0:
            current = 0
        # r == 0 (kas) tidak menambah, tetapi juga tidak mereset - abaikan
    return best


def beta(strategy_returns: list[float], market_returns: list[float]) -> float:
    """Beta = cov(strategi, pasar) / var(pasar). 0 bila data kurang / var nol."""
    n = len(strategy_returns)
    if n < 2 or n != len(market_returns):
        return 0.0
    ms = sum(strategy_returns) / n
    mm = sum(market_returns) / n
    cov = sum((s - ms) * (m - mm) for s, m in zip(strategy_returns, market_returns)) / n
    var = sum((m - mm) ** 2 for m in market_returns) / n
    return cov / var if var else 0.0


def classify(volatility: float, max_drawdown: float) -> str:
    """LOW / MEDIUM / HIGH dari volatilitas tahunan & |max drawdown|."""
    dd = abs(max_drawdown)
    if volatility >= VOL_HIGH or dd >= DD_HIGH:
        return "HIGH"
    if volatility <= VOL_LOW and dd <= DD_LOW:
        return "LOW"
    return "MEDIUM"


def _market_block_returns(
    db: Session, hold: int, cal_dates: list[date], close_by_date: dict[date, float]
) -> dict[int, float]:
    """Return IHSG per blok b = close[(b+1)*hold] / close[b*hold] - 1."""
    out: dict[int, float] = {}
    n = len(cal_dates)
    b = 0
    while (b + 1) * hold < n:
        c0 = close_by_date.get(cal_dates[b * hold])
        c1 = close_by_date.get(cal_dates[(b + 1) * hold])
        if c0 and c1 and c0 > 0:
            out[b] = c1 / c0 - 1.0
        b += 1
    return out


def aligned_returns(
    db: Session,
    strategy: str,
    *,
    hold: int = pm.DEFAULT_HOLD,
    calendar: tuple[list[date], dict[date, int]] | None = None,
) -> tuple[list[float], list[float]]:
    """(return strategi, return pasar) selaras pada blok yang sama-sama tersedia."""
    cal_dates, cal_index = calendar if calendar is not None else pm._trading_calendar(db)
    column = getattr(ReplayHistory, pm._HORIZON_COLUMN[hold])

    trades = db.execute(
        select(ReplayHistory.date, column)
        .where(ReplayHistory.strategy == strategy)
        .where(column.is_not(None))
    ).all()
    s_blocks: dict[int, list[float]] = defaultdict(list)
    for d, r in trades:
        gi = cal_index.get(d)
        if gi is not None:
            s_blocks[gi // hold].append(r)

    rows = db.execute(
        select(MarketData.date, MarketData.close).where(MarketData.ticker == bench.MARKET_TICKER)
    ).all()
    close_by_date = {d: c for d, c in rows if c is not None}
    m_blocks = _market_block_returns(db, hold, cal_dates, close_by_date)

    common = sorted(set(s_blocks) & set(m_blocks))
    s = [sum(s_blocks[b]) / len(s_blocks[b]) for b in common]
    m = [m_blocks[b] for b in common]
    return s, m


def avg_atr_pct(db: Session, strategy: str) -> float | None:
    """Rata-rata ATR% (ATR/price) saham yang dipilih strategi (dari market_data)."""
    value = db.scalar(
        select(func.avg(MarketData.atr / func.nullif(ReplayHistory.price, 0.0)))
        .select_from(ReplayHistory)
        .join(
            MarketData,
            and_(
                MarketData.ticker == ReplayHistory.ticker,
                MarketData.date == ReplayHistory.date,
            ),
        )
        .where(ReplayHistory.strategy == strategy)
        .where(MarketData.atr.is_not(None))
    )
    return float(value) if value is not None else None


def compute_risk_profile(
    db: Session,
    strategy: str,
    *,
    hold: int = pm.DEFAULT_HOLD,
    calendar: tuple[list[date], dict[date, int]] | None = None,
) -> dict:
    """Profil risiko lengkap + klasifikasi untuk satu strategi."""
    calendar = calendar or pm._trading_calendar(db)
    dates, returns = pm.cohort_returns(db, strategy, hold=hold, calendar=calendar)
    periods_per_year = pm.TRADING_DAYS / hold

    volatility = pm._std(returns) * (periods_per_year ** 0.5)
    equity = pm.to_equity(returns)
    mdd = pm.max_drawdown(equity)
    streak = longest_losing_streak(returns)

    s_ret, m_ret = aligned_returns(db, strategy, hold=hold, calendar=calendar)
    b = beta(s_ret, m_ret)
    atr_pct = avg_atr_pct(db, strategy)

    return {
        "strategy": strategy,
        "name": pm.strategy_display_name(strategy),
        "volatility": volatility,
        "avg_atr_pct": atr_pct,
        "beta": b,
        "max_drawdown": mdd,
        "losing_streak": streak,
        "risk_level": classify(volatility, mdd),
        "n_periods": len(returns),
    }


def compute_all(db: Session, *, hold: int = pm.DEFAULT_HOLD, progress: bool = True) -> dict[str, dict]:
    calendar = pm._trading_calendar(db)
    out: dict[str, dict] = {}
    for strategy in pm.VALIDATED_STRATEGIES:
        p = compute_risk_profile(db, strategy, hold=hold, calendar=calendar)
        out[strategy] = p
        if progress:
            print(
                f"  {strategy:<20} vol={p['volatility']*100:5.1f}% beta={p['beta']:+.2f} "
                f"maxDD={p['max_drawdown']*100:+6.1f}% streak={p['losing_streak']} "
                f"[{p['risk_level']}]"
            )
    return out


def _main() -> None:
    from app.db.session import SessionLocal

    if SessionLocal is None:
        raise SystemExit("DATABASE_URL belum diset di backend/.env")
    db = SessionLocal()
    try:
        print(f"Menghitung risk profile per strategi (hold={pm.DEFAULT_HOLD})...")
        compute_all(db)
    finally:
        db.close()


if __name__ == "__main__":
    _main()
