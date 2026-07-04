"""Logika screener IDX - port PERSIS dari frontend/src/lib/screener.ts.

Murni (tidak menyentuh DB / ML / cache) sehingga mudah diuji & dipakai ulang.
Dua strategi intraday:
  - BSJP (Beli Sore Jual Pagi)  - butuh lonjakan harga + volume kuat
  - BPJS (Beli Pagi Jual Sore)  - sama, plus close >= open, syarat volume longgar

Ambang & rumus disamakan baris-per-baris dengan TS (lihat komentar per blok).
Indikator dihitung ulang dari bar via app.core.indicators agar identik dengan
perhitungan client-side Phase 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from app.core import indicators

Strategy = Literal["BSJP", "BPJS"]

# Ambang default (mirror screener.ts).
MIN_DAILY_VALUE = 5_000_000_000  # Rp5 miliar turnover harian minimum
DEFAULT_ATR_MULTIPLIER = 1.0
DEFAULT_RISK_REWARD_RATIO = 2.0

# Screener butuh minimal 6 bar (current + previous + MA5 window).
MIN_BARS = 6


class OhlcvBar(Protocol):
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class ScreenerInput:
    current_open: float
    current_close: float
    current_volume: float
    previous_close: float
    previous_volume: float
    price_ma5: float
    atr: float | None
    rsi: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    bb_upper: float | None
    bb_middle: float | None
    bb_lower: float | None
    vwap: float | None
    volume_spike_ratio: float | None


@dataclass(frozen=True)
class TradeLevels:
    entry: float
    stop_loss: float
    take_profit: float
    exit: float
    risk_per_share: float
    reward_per_share: float


@dataclass(frozen=True)
class ScreenerCandidate:
    ticker: str
    strategy: Strategy
    criteria: dict[str, bool]
    score: float
    value: float
    levels: TradeLevels
    inp: ScreenerInput


def _trade_value(price: float, volume: float) -> float:
    return price * volume


def build_screener_input(bars: list[OhlcvBar]) -> ScreenerInput | None:
    """Rakit snapshot indikator bar terakhir. None bila data < MIN_BARS."""
    if len(bars) < MIN_BARS:
        return None

    current = bars[-1]
    previous = bars[-2]

    closes = [bar.close for bar in bars]
    volumes = [float(bar.volume) for bar in bars]
    macd = indicators.calculate_macd(closes)
    band = indicators.calculate_bollinger_bands(closes)[-1]
    spike = indicators.calculate_volume_spike(volumes)[-1]

    return ScreenerInput(
        current_open=current.open,
        current_close=current.close,
        current_volume=float(current.volume),
        previous_close=previous.close,
        previous_volume=float(previous.volume),
        price_ma5=indicators.simple_moving_average(closes, 5) or current.close,
        atr=indicators.calculate_atr(bars)[-1],
        rsi=indicators.calculate_rsi(closes)[-1],
        macd=macd.macd[-1],
        macd_signal=macd.signal[-1],
        macd_histogram=macd.histogram[-1],
        bb_upper=band.upper,
        bb_middle=band.middle,
        bb_lower=band.lower,
        vwap=indicators.calculate_vwap(bars)[-1],
        volume_spike_ratio=spike.ratio,
    )


def get_bsjp_criteria(inp: ScreenerInput, min_daily_value: float) -> dict[str, bool]:
    value = _trade_value(inp.current_close, inp.current_volume)
    return {
        "price_vs_previous": inp.current_close >= 1.05 * inp.previous_close,
        "price_vs_ma5": inp.current_close >= inp.price_ma5,
        "volume_vs_previous": inp.current_volume >= 1.2 * inp.previous_volume,
        "value_threshold": value > min_daily_value,
    }


def get_bpjs_criteria(inp: ScreenerInput, min_daily_value: float) -> dict[str, bool]:
    value = _trade_value(inp.current_close, inp.current_volume)
    return {
        "price_vs_previous": inp.current_close >= 1.05 * inp.previous_close,
        "price_vs_ma5": inp.current_close >= inp.price_ma5,
        "price_vs_open": inp.current_close >= inp.current_open,
        "volume_vs_previous": inp.current_volume >= 0.2 * inp.previous_volume,
        "value_threshold": value > min_daily_value,
    }


def _criteria_for(
    strategy: Strategy, inp: ScreenerInput, min_daily_value: float
) -> dict[str, bool]:
    return (
        get_bsjp_criteria(inp, min_daily_value)
        if strategy == "BSJP"
        else get_bpjs_criteria(inp, min_daily_value)
    )


def calculate_score(inp: ScreenerInput, strategy: Strategy) -> float:
    """Skor komposit - port dari calculateScore (screener.ts)."""
    price_momentum = inp.current_close / inp.previous_close
    volume_momentum = inp.current_volume / max(inp.previous_volume, 1)
    value_score = _trade_value(inp.current_close, inp.current_volume) / MIN_DAILY_VALUE
    rsi_score = 0.0 if inp.rsi is None else min(inp.rsi / 100, 1)
    macd_score = 0.0 if inp.macd_histogram is None else max(inp.macd_histogram, 0)
    vwap_score = 0.0 if inp.vwap is None else inp.current_close / max(inp.vwap, 1)
    spike_score = inp.volume_spike_ratio or 0.0
    strategy_weight = 1.05 if strategy == "BSJP" else 1.0

    return (
        price_momentum * 2
        + volume_momentum
        + min(value_score, 5)
        + rsi_score
        + macd_score
        + vwap_score
        + spike_score
    ) * strategy_weight


def calculate_trade_levels(
    inp: ScreenerInput,
    atr_multiplier: float = DEFAULT_ATR_MULTIPLIER,
    risk_reward_ratio: float = DEFAULT_RISK_REWARD_RATIO,
) -> TradeLevels:
    entry = inp.current_close
    atr_risk = entry * 0.02 if inp.atr is None else inp.atr * atr_multiplier
    risk_per_share = max(atr_risk, entry * 0.005)
    reward_per_share = risk_per_share * risk_reward_ratio
    return TradeLevels(
        entry=entry,
        stop_loss=entry - risk_per_share,
        take_profit=entry + reward_per_share,
        exit=entry + reward_per_share,
        risk_per_share=risk_per_share,
        reward_per_share=reward_per_share,
    )


def _create_candidate(
    ticker: str,
    strategy: Strategy,
    inp: ScreenerInput,
    min_daily_value: float,
    atr_multiplier: float,
    risk_reward_ratio: float,
) -> ScreenerCandidate:
    return ScreenerCandidate(
        ticker=ticker,
        strategy=strategy,
        criteria=_criteria_for(strategy, inp, min_daily_value),
        value=_trade_value(inp.current_close, inp.current_volume),
        score=calculate_score(inp, strategy),
        levels=calculate_trade_levels(inp, atr_multiplier, risk_reward_ratio),
        inp=inp,
    )


def screen_bars(
    ticker: str,
    bars: list[OhlcvBar],
    min_daily_value: float = MIN_DAILY_VALUE,
    atr_multiplier: float = DEFAULT_ATR_MULTIPLIER,
    risk_reward_ratio: float = DEFAULT_RISK_REWARD_RATIO,
) -> list[ScreenerCandidate]:
    """Kembalikan kandidat (0..2) untuk satu ticker, satu per strategi yang lolos."""
    inp = build_screener_input(bars)
    if inp is None:
        return []

    candidates: list[ScreenerCandidate] = []
    for strategy in ("BSJP", "BPJS"):
        criteria = _criteria_for(strategy, inp, min_daily_value)  # type: ignore[arg-type]
        if all(criteria.values()):
            candidates.append(
                _create_candidate(
                    ticker,
                    strategy,  # type: ignore[arg-type]
                    inp,
                    min_daily_value,
                    atr_multiplier,
                    risk_reward_ratio,
                )
            )
    return candidates
