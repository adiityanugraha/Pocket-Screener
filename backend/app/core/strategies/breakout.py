"""Strategi BREAKOUT (Phase 3 Day 2) - saham menembus dengan volume kuat.

Kriteria (blueprint):
  a. Price   > Previous Price
  b. Volume  > Volume MA 20
  c. Volume MA 20 > 300.000.000
  d. Price   > 100
  e. Volume  > Previous Volume

Butuh >= 20 bar untuk Volume MA 20; bila kurang -> NOT_EVALUATED.
"""

from __future__ import annotations

from app.core.strategies._common import TechSnapshot, build_tech_snapshot
from app.core.strategies.base import (
    NOT_EVALUATED,
    StockData,
    Strategy,
    StrategyResult,
    StrategyType,
)
from app.core.strategies.registry import register

VOLUME_MA_PERIOD = 20
MIN_VOLUME_MA = 300_000_000  # 300 juta lembar rata-rata 20 hari
MIN_PRICE = 100  # saringan saham gocap


def _evaluate(snap: TechSnapshot, vol_ma20: float) -> tuple[dict[str, bool], dict[str, str]]:
    criteria = {
        "price_vs_previous": snap.close > snap.prev_close,
        "volume_vs_ma20": snap.volume > vol_ma20,
        "volume_ma20_threshold": vol_ma20 > MIN_VOLUME_MA,
        "price_above_100": snap.close > MIN_PRICE,
        "volume_vs_previous": snap.volume > snap.prev_volume,
    }
    descriptions = {
        "price_vs_previous": (
            f"Harga {snap.close:,.0f} > harga kemarin ({snap.prev_close:,.0f})"
        ),
        "volume_vs_ma20": (
            f"Volume {snap.volume:,.0f} > Volume MA20 ({vol_ma20:,.0f})"
        ),
        "volume_ma20_threshold": (
            f"Volume MA20 {vol_ma20:,.0f} > {MIN_VOLUME_MA:,.0f} (likuiditas tinggi)"
        ),
        "price_above_100": f"Harga {snap.close:,.0f} > {MIN_PRICE} (bukan saham gocap)",
        "volume_vs_previous": (
            f"Volume {snap.volume:,.0f} > volume kemarin ({snap.prev_volume:,.0f})"
        ),
    }
    return criteria, descriptions


class BreakoutStrategy(Strategy):
    key = "breakout"
    name = "Breakout"
    type = StrategyType.TECHNICAL
    output_label = "Top Breakout Candidates"

    def run(self, data: StockData) -> StrategyResult:
        snap = build_tech_snapshot(data.bars)
        if snap is None:
            return NOT_EVALUATED
        vol_ma20 = snap.volume_ma(VOLUME_MA_PERIOD)
        if vol_ma20 is None:  # < 20 bar
            return NOT_EVALUATED

        criteria, descriptions = _evaluate(snap, vol_ma20)
        return StrategyResult(
            passed=all(criteria.values()),
            criteria=criteria,
            matched_criteria=[descriptions[k] for k, ok in criteria.items() if ok],
        )


register(BreakoutStrategy())
