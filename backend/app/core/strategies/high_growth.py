"""Strategi HIGH GROWTH (Phase 3 Day 6) - perusahaan bertumbuh cepat.

Kriteria (blueprint):
  a. Revenue (Growth: 3 Year)   >= 10   (CAGR 3 tahun, persen)
  b. Revenue (Growth: YTD YoY)  >= 10   (YoY, persen)
  c. Sales Growth Streak        >= 3    (tahun beruntun revenue naik)
  d. Volume MA 20               > 1.000 (likuiditas minimum, lembar)

Semua field tersedia dari data Yahoo (revenue tahunan 4thn + volume) -> strategi
ini bisa dievaluasi penuh. Butuh FundamentalView (data fundamental) + >= 20 bar
(Volume MA20); bila tidak ada -> NOT_EVALUATED.
"""

from __future__ import annotations

from app.core.fundamentals import FundamentalView
from app.core.strategies._common import ge, gt, volume_ma20
from app.core.strategies.base import (
    NOT_EVALUATED,
    StockData,
    Strategy,
    StrategyResult,
    StrategyType,
)
from app.core.strategies.registry import register


def _evaluate(view: FundamentalView, vol_ma20: float) -> tuple[dict[str, bool], dict[str, str]]:
    criteria = {
        "revenue_growth_3yr": ge(view.revenue_growth_3yr, 10),
        "revenue_growth_yoy": ge(view.revenue_growth_yoy, 10),
        "sales_growth_streak": view.sales_growth_streak >= 3,
        "volume_ma20_min": gt(vol_ma20, 1_000),
    }
    descriptions = {
        "revenue_growth_3yr": f"Revenue tumbuh {view.revenue_growth_3yr:.1f}% CAGR 3thn (>= 10%)"
        if view.revenue_growth_3yr is not None else "",
        "revenue_growth_yoy": f"Revenue tumbuh {view.revenue_growth_yoy:.1f}% YoY (>= 10%)"
        if view.revenue_growth_yoy is not None else "",
        "sales_growth_streak": f"Revenue naik {view.sales_growth_streak} tahun beruntun (>= 3)",
        "volume_ma20_min": f"Volume MA20 {vol_ma20:,.0f} > 1.000 (likuid)",
    }
    return criteria, descriptions


class HighGrowthStrategy(Strategy):
    key = "high_growth"
    name = "High Growth"
    type = StrategyType.FUNDAMENTAL
    output_label = "High Growth Companies"

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


register(HighGrowthStrategy())
