"""Strategi TREND FOLLOWING (Phase 3 Day 2) - uptrend MA tersusun rapi.

Kriteria (blueprint):
  a. Price       > Price MA 20
  b. Price MA 20 > Price MA 50
  c. Price MA 50 > Price MA 100
  d. Price MA 100> Price MA 200
  e. Value       > 1.000.000.000   (minimum likuiditas)

Butuh >= 200 bar untuk MA200; bila kurang -> NOT_EVALUATED. (Re-ingest 2 tahun
sudah dijalankan sebelum Day 2 agar MA200 tersedia.)
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

MIN_VALUE = 1_000_000_000  # Rp1 miliar turnover harian minimum


def _evaluate(
    snap: TechSnapshot, ma20: float, ma50: float, ma100: float, ma200: float
) -> tuple[dict[str, bool], dict[str, str]]:
    criteria = {
        "price_above_ma20": snap.close > ma20,
        "ma20_above_ma50": ma20 > ma50,
        "ma50_above_ma100": ma50 > ma100,
        "ma100_above_ma200": ma100 > ma200,
        "value_threshold": snap.value > MIN_VALUE,
    }
    descriptions = {
        "price_above_ma20": f"Harga {snap.close:,.0f} > MA20 ({ma20:,.0f})",
        "ma20_above_ma50": f"MA20 ({ma20:,.0f}) > MA50 ({ma50:,.0f})",
        "ma50_above_ma100": f"MA50 ({ma50:,.0f}) > MA100 ({ma100:,.0f})",
        "ma100_above_ma200": f"MA100 ({ma100:,.0f}) > MA200 ({ma200:,.0f})",
        "value_threshold": f"Nilai transaksi Rp {snap.value:,.0f} > Rp {MIN_VALUE:,.0f}",
    }
    return criteria, descriptions


class TrendFollowingStrategy(Strategy):
    key = "trend_following"
    name = "Trend Following"
    type = StrategyType.TECHNICAL
    output_label = "Top Trend Stocks"

    def run(self, data: StockData) -> StrategyResult:
        snap = build_tech_snapshot(data.bars)
        if snap is None:
            return NOT_EVALUATED
        ma20 = snap.price_ma(20)
        ma50 = snap.price_ma(50)
        ma100 = snap.price_ma(100)
        ma200 = snap.price_ma(200)
        if None in (ma20, ma50, ma100, ma200):  # < 200 bar
            return NOT_EVALUATED

        criteria, descriptions = _evaluate(snap, ma20, ma50, ma100, ma200)
        return StrategyResult(
            passed=all(criteria.values()),
            criteria=criteria,
            matched_criteria=[descriptions[k] for k, ok in criteria.items() if ok],
        )


register(TrendFollowingStrategy())
