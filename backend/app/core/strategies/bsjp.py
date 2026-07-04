"""Strategi BSJP (Beli Sore Jual Pagi) - dipindah ke pola registry (Day 1).

Logika TIDAK ditulis ulang: kriteria tetap dihitung oleh fungsi murni Phase 2
(app.core.screener.get_bsjp_criteria) sehingga hasil dijamin identik. File ini
hanya membungkusnya dalam interface Strategy + deskripsi human-readable per
kriteria untuk Explainable AI (Day 10).
"""

from __future__ import annotations

from app.core import screener as screener_core
from app.core.strategies.base import (
    NOT_EVALUATED,
    StockData,
    Strategy,
    StrategyResult,
    StrategyType,
)
from app.core.strategies.registry import register


def _descriptions(inp: screener_core.ScreenerInput) -> dict[str, str]:
    value = inp.current_close * inp.current_volume
    return {
        "price_vs_previous": (
            f"Harga {inp.current_close:,.0f} >= 105% harga kemarin "
            f"({1.05 * inp.previous_close:,.0f})"
        ),
        "price_vs_ma5": f"Harga {inp.current_close:,.0f} >= MA5 ({inp.price_ma5:,.0f})",
        "volume_vs_previous": (
            f"Volume {inp.current_volume:,.0f} >= 1.2x volume kemarin "
            f"({1.2 * inp.previous_volume:,.0f})"
        ),
        "value_threshold": (
            f"Nilai transaksi Rp {value:,.0f} > Rp "
            f"{screener_core.MIN_DAILY_VALUE:,.0f}"
        ),
    }


class BsjpStrategy(Strategy):
    key = "bsjp"
    name = "BSJP (Beli Sore Jual Pagi)"
    type = StrategyType.TECHNICAL
    output_label = "Top BSJP Candidates"

    def run(self, data: StockData) -> StrategyResult:
        inp = screener_core.build_screener_input(data.bars)
        if inp is None:
            return NOT_EVALUATED

        criteria = screener_core.get_bsjp_criteria(inp, screener_core.MIN_DAILY_VALUE)
        descriptions = _descriptions(inp)
        return StrategyResult(
            passed=all(criteria.values()),
            criteria=criteria,
            matched_criteria=[descriptions[key] for key, ok in criteria.items() if ok],
        )


register(BsjpStrategy())
