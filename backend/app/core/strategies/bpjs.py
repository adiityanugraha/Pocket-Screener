"""Strategi BPJS (Beli Pagi Jual Sore) - dipindah ke pola registry (Day 1).

Logika TIDAK ditulis ulang: kriteria tetap dihitung oleh fungsi murni Phase 2
(app.core.screener.get_bpjs_criteria) sehingga hasil dijamin identik. File ini
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
        "price_vs_open": (
            f"Close {inp.current_close:,.0f} >= open hari ini "
            f"({inp.current_open:,.0f})"
        ),
        "volume_vs_previous": (
            f"Volume {inp.current_volume:,.0f} >= 0.2x volume kemarin "
            f"({0.2 * inp.previous_volume:,.0f})"
        ),
        "value_threshold": (
            f"Nilai transaksi Rp {value:,.0f} > Rp "
            f"{screener_core.MIN_DAILY_VALUE:,.0f}"
        ),
    }


class BpjsStrategy(Strategy):
    key = "bpjs"
    name = "BPJS (Beli Pagi Jual Sore)"
    type = StrategyType.TECHNICAL
    output_label = "Top BPJS Candidates"

    def run(self, data: StockData) -> StrategyResult:
        inp = screener_core.build_screener_input(data.bars)
        if inp is None:
            return NOT_EVALUATED

        criteria = screener_core.get_bpjs_criteria(inp, screener_core.MIN_DAILY_VALUE)
        descriptions = _descriptions(inp)
        return StrategyResult(
            passed=all(criteria.values()),
            criteria=criteria,
            matched_criteria=[descriptions[key] for key, ok in criteria.items() if ok],
        )


register(BpjsStrategy())
