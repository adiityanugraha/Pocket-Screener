"""Strategi TIMELESS (Phase 3 Day 7) - compounder jangka panjang.

Kriteria blueprint (10) dan status datanya di sumber Yahoo gratis:
  a. Average RoE 5yr            >= 10    PROXY (RoE saat ini - histori 5thn
                                          tak tersedia)
  b. Net Income (Growth: 3yr)   >= -5    EVALUASI (CAGR 3thn)
  c. Net Income (Annual)        >= 1T    EVALUASI (tahun fiskal terakhir)
  d. 10 Year Price Returns      > 0      PROXY (return atas histori harga yang
                                          tersedia, span ditandai)
  e. PE                         > 0      EVALUASI
  f. PE                         <= 25    EVALUASI
  g. Common Equity              >= 10T   EVALUASI (derived: marketCap/PBV)
  h. Dividend Payment Streak    >= 5     SKIP (histori dividen tak tersedia)
  i. Dividend Yield             >= 2%    EVALUASI (dps/close)
  j. Value MA 20                >= 5M    EVALUASI (dari bar harga)

Kebijakan "proxy + lewati, ditandai": kriteria proxy diberi label proxy di
deskripsinya; yang dilewati dicatat di skipped_criteria.
"""

from __future__ import annotations

from app.core.fundamentals import FundamentalView
from app.core.strategies._common import value_ma20
from app.core.strategies.base import (
    NOT_EVALUATED,
    StockData,
    Strategy,
    StrategyResult,
    StrategyType,
)
from app.core.strategies.registry import register

MIN_NET_INCOME_ANNUAL = 1_000_000_000_000   # Rp1 triliun
MIN_COMMON_EQUITY = 10_000_000_000_000      # Rp10 triliun
MIN_VALUE_MA20 = 5_000_000_000              # Rp5 miliar

SKIP_DIVIDEND_STREAK = (
    "dividend_streak: histori pembayaran dividen 5 tahun tak tersedia "
    "di sumber data gratis"
)


def _evaluate(
    view: FundamentalView, val_ma20: float
) -> tuple[dict[str, bool], dict[str, str]]:
    # a. RoE - proxy: RoE saat ini (fraksi -> persen) bila rata-rata 5thn kosong.
    roe_pct = (
        view.roe_5yr_avg
        if view.roe_5yr_avg is not None
        else (view.roe * 100 if view.roe is not None else None)
    )
    roe_is_proxy = view.roe_5yr_avg is None

    # c. Net income tahun fiskal terakhir.
    ni_annual = view.annual[0].net_income if view.annual else None

    # d. Price return - proxy atas histori yang tersedia.
    span_years = (
        view.price_return_span_days / 365 if view.price_return_span_days else None
    )

    # i. Dividend yield: fraksi -> persen.
    div_yield_pct = view.dividend_yield * 100 if view.dividend_yield is not None else None

    pe = view.pe_annualised
    ni_3yr = view.net_income_growth_3yr

    criteria = {
        "roe_min_10": roe_pct is not None and roe_pct >= 10,
        "net_income_growth_3yr": ni_3yr is not None and ni_3yr >= -5,
        "net_income_annual_min": ni_annual is not None and ni_annual >= MIN_NET_INCOME_ANNUAL,
        "price_return_positive": view.price_return is not None and view.price_return > 0,
        "pe_positive": pe is not None and pe > 0,
        "pe_max_25": pe is not None and pe <= 25,
        "common_equity_min": (
            view.common_equity is not None and view.common_equity >= MIN_COMMON_EQUITY
        ),
        "dividend_yield_min": div_yield_pct is not None and div_yield_pct >= 2,
        "value_ma20_min": val_ma20 >= MIN_VALUE_MA20,
    }
    descriptions = {
        "roe_min_10": (
            f"RoE {roe_pct:.1f}% >= 10%"
            + (" (proxy RoE saat ini - rata-rata 5thn tak tersedia)" if roe_is_proxy else "")
            if roe_pct is not None else ""
        ),
        "net_income_growth_3yr": (
            f"Net income {ni_3yr:+.1f}% CAGR 3thn (>= -5%)" if ni_3yr is not None else ""
        ),
        "net_income_annual_min": (
            f"Net income tahunan Rp {ni_annual:,.0f} >= Rp 1 triliun"
            if ni_annual is not None else ""
        ),
        "price_return_positive": (
            f"Return harga {view.price_return:+.1f}% selama ~{span_years:.1f} tahun > 0 "
            f"(proxy 10-Year Price Returns)"
            if view.price_return is not None and span_years is not None else ""
        ),
        "pe_positive": f"PE {pe:.2f} > 0" if pe is not None else "",
        "pe_max_25": f"PE {pe:.2f} <= 25" if pe is not None else "",
        "common_equity_min": (
            f"Ekuitas Rp {view.common_equity:,.0f} >= Rp 10 triliun"
            if view.common_equity is not None else ""
        ),
        "dividend_yield_min": (
            f"Dividend yield {div_yield_pct:.2f}% >= 2%" if div_yield_pct is not None else ""
        ),
        "value_ma20_min": f"Nilai transaksi MA20 Rp {val_ma20:,.0f} >= Rp 5 miliar",
    }
    return criteria, descriptions


class TimelessStrategy(Strategy):
    key = "timeless"
    name = "Timeless"
    type = StrategyType.FUNDAMENTAL
    output_label = "Timeless Compounders"

    def run(self, data: StockData) -> StrategyResult:
        view = data.fundamentals
        if view is None:
            return NOT_EVALUATED
        val_ma20 = value_ma20(data.bars)
        if val_ma20 is None:  # < 20 bar
            return NOT_EVALUATED

        criteria, descriptions = _evaluate(view, val_ma20)
        return StrategyResult(
            passed=all(criteria.values()),
            criteria=criteria,
            matched_criteria=[descriptions[k] for k, ok in criteria.items() if ok],
            skipped_criteria=[SKIP_DIVIDEND_STREAK],
        )


register(TimelessStrategy())
