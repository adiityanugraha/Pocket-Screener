"""Strategi TURNAROUND (Phase 3 Day 7) - perusahaan mulai pulih.

Kriteria blueprint (8) dan status datanya di sumber Yahoo gratis:
  a. Net Income (Growth: YTD YoY)        >= 5    EVALUASI (YoY tahunan)
  b. Net Income (YTD) <= 1 x Income From Operations
                                                  SKIP* (IFO tak tersedia)
  c. Current Price to Book Value         > 0     EVALUASI
  d. PE Annualised <= 0.7 x Current PE            SKIP (butuh PE annualised
                                                  dari laporan kuartalan -
                                                  hanya ada 1 PE trailing)
  e. Current PE Ratio (Annualised)       > 1     EVALUASI (proxy: PE trailing)
  f. Current PE Ratio (Annualised)       <= 12   EVALUASI (proxy: PE trailing)
  g. Income From Operations <= 1 x Gross Profit   SKIP* (IFO tak tersedia)
  h. Revenue (Growth: YTD YoY)           >= 5    EVALUASI (YoY tahunan)

  *) b & g dievaluasi otomatis bila income_from_operations terisi (mis. saat
     sumber data di-upgrade) - skip-nya dinamis, bukan hardcode.

Kebijakan "proxy + lewati, ditandai": strategi dinilai atas subset terhitung;
kriteria yang dilewati dicatat di skipped_criteria.
"""

from __future__ import annotations

from app.core.fundamentals import FundamentalView
from app.core.strategies.base import (
    NOT_EVALUATED,
    StockData,
    Strategy,
    StrategyResult,
    StrategyType,
)
from app.core.strategies.registry import register

SKIP_PE_ANNUALISED = (
    "pe_annualised_vs_current: butuh PE annualised dari laporan kuartalan "
    "(tak tersedia di sumber data gratis)"
)
SKIP_NI_VS_IFO = (
    "net_income_vs_income_from_operations: Income From Operations tak tersedia"
)
SKIP_IFO_VS_GROSS = (
    "income_from_operations_vs_gross_profit: Income From Operations tak tersedia"
)


def _evaluate(view: FundamentalView) -> tuple[dict[str, bool], dict[str, str], list[str]]:
    pe = view.pe_annualised  # proxy: PE trailing dihitung harian (close/EPS ttm)
    ni_yoy = view.net_income_growth_yoy
    rev_yoy = view.revenue_growth_yoy

    criteria = {
        "net_income_growth_yoy": ni_yoy is not None and ni_yoy >= 5,
        "pbv_positive": view.pbv is not None and view.pbv > 0,
        "pe_above_1": pe is not None and pe > 1,
        "pe_max_12": pe is not None and pe <= 12,
        "revenue_growth_yoy": rev_yoy is not None and rev_yoy >= 5,
    }
    descriptions = {
        "net_income_growth_yoy": (
            f"Net income tumbuh {ni_yoy:.1f}% YoY (>= 5%)" if ni_yoy is not None else ""
        ),
        "pbv_positive": f"PBV {view.pbv:.2f} > 0" if view.pbv is not None else "",
        "pe_above_1": f"PE {pe:.2f} > 1 (proxy PE trailing)" if pe is not None else "",
        "pe_max_12": f"PE {pe:.2f} <= 12 - masih murah (proxy PE trailing)"
        if pe is not None else "",
        "revenue_growth_yoy": (
            f"Revenue tumbuh {rev_yoy:.1f}% YoY (>= 5%)" if rev_yoy is not None else ""
        ),
    }

    skipped = [SKIP_PE_ANNUALISED]
    ifo = view.income_from_operations
    if ifo is not None and view.net_income_ttm is not None:
        criteria["net_income_vs_ifo"] = view.net_income_ttm <= ifo
        descriptions["net_income_vs_ifo"] = (
            f"Net income Rp {view.net_income_ttm:,.0f} <= laba operasi Rp {ifo:,.0f}"
        )
    else:
        skipped.append(SKIP_NI_VS_IFO)
    if ifo is not None and view.gross_profit is not None:
        criteria["ifo_vs_gross_profit"] = ifo <= view.gross_profit
        descriptions["ifo_vs_gross_profit"] = (
            f"Laba operasi Rp {ifo:,.0f} <= laba kotor Rp {view.gross_profit:,.0f}"
        )
    else:
        skipped.append(SKIP_IFO_VS_GROSS)

    return criteria, descriptions, skipped


class TurnaroundStrategy(Strategy):
    key = "turnaround"
    name = "Turnaround"
    type = StrategyType.FUNDAMENTAL
    output_label = "Turnaround Candidates"

    def run(self, data: StockData) -> StrategyResult:
        view = data.fundamentals
        if view is None:
            return NOT_EVALUATED

        criteria, descriptions, skipped = _evaluate(view)
        return StrategyResult(
            passed=all(criteria.values()),
            criteria=criteria,
            matched_criteria=[descriptions[k] for k, ok in criteria.items() if ok],
            skipped_criteria=skipped,
        )


register(TurnaroundStrategy())
