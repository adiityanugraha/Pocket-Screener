"""Strategi CASH RICH (Phase 3 Day 6) - neraca sangat kuat (kas dominan).

Kriteria (blueprint):
  a. Cash and cash equivalents   >= 0.7 x Market Cap
  b. Market Cap                  > 1.000.000.000
  c. Total Debt (Quarter)        < 0.5 x Cash and cash equivalents
  d. Current Price to Book Value > 0
  e. Volume MA 20                > 10.000

Field tersedia dari Yahoo (totalCash, totalDebt andal; marketCap & PBV turunan
harian). Bisa dievaluasi penuh. Butuh FundamentalView + >= 20 bar -> selain itu
NOT_EVALUATED.
"""

from __future__ import annotations

from app.core.fundamentals import FundamentalView
from app.core.strategies._common import gt, lt, volume_ma20
from app.core.strategies.base import (
    NOT_EVALUATED,
    StockData,
    Strategy,
    StrategyResult,
    StrategyType,
)
from app.core.strategies.registry import register


def _evaluate(view: FundamentalView, vol_ma20: float) -> tuple[dict[str, bool], dict[str, str]]:
    cash = view.cash_equivalents
    market_cap = view.market_cap
    total_debt = view.total_debt

    criteria = {
        "cash_vs_market_cap": (
            cash is not None and market_cap is not None and cash >= 0.7 * market_cap
        ),
        "market_cap_min": gt(market_cap, 1_000_000_000),
        "debt_vs_cash": (
            total_debt is not None and cash is not None and total_debt < 0.5 * cash
        ),
        "pbv_positive": gt(view.pbv, 0),
        "volume_ma20_min": gt(vol_ma20, 10_000),
    }
    descriptions = {
        "cash_vs_market_cap": (
            f"Kas Rp {cash:,.0f} >= 70% market cap (Rp {0.7 * market_cap:,.0f})"
            if cash is not None and market_cap is not None else ""
        ),
        "market_cap_min": (
            f"Market cap Rp {market_cap:,.0f} > Rp 1 miliar"
            if market_cap is not None else ""
        ),
        "debt_vs_cash": (
            f"Total utang Rp {total_debt:,.0f} < 50% kas (Rp {0.5 * cash:,.0f})"
            if total_debt is not None and cash is not None else ""
        ),
        "pbv_positive": f"PBV {view.pbv:.2f} > 0" if view.pbv is not None else "",
        "volume_ma20_min": f"Volume MA20 {vol_ma20:,.0f} > 10.000 (likuid)",
    }
    return criteria, descriptions


class CashRichStrategy(Strategy):
    key = "cash_rich"
    name = "Cash Rich"
    type = StrategyType.FUNDAMENTAL
    output_label = "Cash Rich Stocks"

    def run(self, data: StockData) -> StrategyResult:
        view = data.fundamentals
        if view is None:
            return NOT_EVALUATED
        vol_ma20 = volume_ma20(data.bars)
        if vol_ma20 is None:  # < 20 bar
            return NOT_EVALUATED

        criteria, descriptions = _evaluate(view, vol_ma20)
        return StrategyResult(
            passed=all(criteria.values()),
            criteria=criteria,
            matched_criteria=[descriptions[k] for k, ok in criteria.items() if ok],
        )


register(CashRichStrategy())
