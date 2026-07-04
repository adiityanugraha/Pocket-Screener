"""Strategi POTENTIAL REVERSAL (Phase 3 Day 3) - keluar dari fase koreksi.

Kriteria (blueprint):
  a. Price        > Price MA 10
  b. Price MA 20  > Price
  c. Price MA 20  > Price MA 10
  d. Previous Price < Price MA 10
  e. Previous Price < Price
  f. Volume       > Volume MA 20

Intuisi: harga baru saja menembus MA10 dari bawah (kemarin di bawah MA10, hari ini
di atas) tetapi masih di bawah MA20 - awal pemulihan dari koreksi, dikonfirmasi
volume di atas rata-rata. Butuh >= 20 bar (MA20 & Volume MA20) -> NOT_EVALUATED.
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


def _evaluate(
    snap: TechSnapshot, ma10: float, ma20: float, vol_ma20: float
) -> tuple[dict[str, bool], dict[str, str]]:
    criteria = {
        "price_above_ma10": snap.close > ma10,
        "ma20_above_price": ma20 > snap.close,
        "ma20_above_ma10": ma20 > ma10,
        "prev_below_ma10": snap.prev_close < ma10,
        "prev_below_price": snap.prev_close < snap.close,
        "volume_above_ma20": snap.volume > vol_ma20,
    }
    descriptions = {
        "price_above_ma10": f"Harga {snap.close:,.0f} > MA10 ({ma10:,.0f})",
        "ma20_above_price": f"MA20 ({ma20:,.0f}) > harga {snap.close:,.0f}",
        "ma20_above_ma10": f"MA20 ({ma20:,.0f}) > MA10 ({ma10:,.0f})",
        "prev_below_ma10": (
            f"Harga kemarin {snap.prev_close:,.0f} < MA10 ({ma10:,.0f}) "
            f"-> baru menembus naik"
        ),
        "prev_below_price": (
            f"Harga kemarin {snap.prev_close:,.0f} < harga hari ini {snap.close:,.0f}"
        ),
        "volume_above_ma20": (
            f"Volume {snap.volume:,.0f} > Volume MA20 ({vol_ma20:,.0f})"
        ),
    }
    return criteria, descriptions


class PotentialReversalStrategy(Strategy):
    key = "potential_reversal"
    name = "Potential Reversal"
    type = StrategyType.TECHNICAL
    output_label = "Potential Reversal Stocks"

    def run(self, data: StockData) -> StrategyResult:
        snap = build_tech_snapshot(data.bars)
        if snap is None:
            return NOT_EVALUATED
        ma10 = snap.price_ma(10)
        ma20 = snap.price_ma(20)
        vol_ma20 = snap.volume_ma(20)
        if None in (ma10, ma20, vol_ma20):  # < 20 bar
            return NOT_EVALUATED

        criteria, descriptions = _evaluate(snap, ma10, ma20, vol_ma20)
        return StrategyResult(
            passed=all(criteria.values()),
            criteria=criteria,
            matched_criteria=[descriptions[k] for k, ok in criteria.items() if ok],
        )


register(PotentialReversalStrategy())
