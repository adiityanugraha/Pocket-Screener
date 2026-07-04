"""Performance tracking - evaluasi hasil screener setelah N hari + winrate.

Sesuai blueprint Phase 2 (Screener History):
  - Tracking performa setelah screening (mis. "+4.2% setelah 7 hari")
  - Analisis akurasi strategi (winrate per strategi)

Modul ini MURNI (tanpa DB). API (history.py) yang merakit harga forward dari
market_data lalu memanggil fungsi-fungsi di sini.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrackedTrade:
    date: str
    ticker: str
    strategy: str
    score: float | None
    entry_close: float
    forward_close: float | None  # close `horizon` bar setelah tanggal screening
    forward_return: float | None  # None bila bar forward belum tersedia (PENDING)
    outcome: str  # WIN | LOSS | FLAT | PENDING


@dataclass(frozen=True)
class StrategyPerformance:
    strategy: str
    total: int  # seluruh entri riwayat
    evaluated: int  # entri yang sudah punya hasil forward
    wins: int
    losses: int
    flat: int
    winrate: float | None  # wins / evaluated
    avg_return: float | None
    cumulative_return: float | None  # compounding seluruh trade terevaluasi
    max_drawdown: float | None  # dari kurva ekuitas trade berurutan


def classify_outcome(forward_return: float | None) -> str:
    if forward_return is None:
        return "PENDING"
    if forward_return > 0:
        return "WIN"
    if forward_return < 0:
        return "LOSS"
    return "FLAT"


def make_trade(
    date: str,
    ticker: str,
    strategy: str,
    score: float | None,
    entry_close: float,
    forward_close: float | None,
) -> TrackedTrade:
    forward_return = (
        forward_close / entry_close - 1
        if forward_close is not None and entry_close
        else None
    )
    return TrackedTrade(
        date=date,
        ticker=ticker,
        strategy=strategy,
        score=score,
        entry_close=round(entry_close, 2),
        forward_close=None if forward_close is None else round(forward_close, 2),
        forward_return=None if forward_return is None else round(forward_return, 4),
        outcome=classify_outcome(forward_return),
    )


def summarize(trades: list[TrackedTrade], strategy: str) -> StrategyPerformance:
    """Ringkas winrate, rata-rata return, cumulative & max drawdown satu strategi."""
    subset = [t for t in trades if t.strategy == strategy]
    evaluated = [t for t in subset if t.forward_return is not None]

    wins = sum(1 for t in evaluated if t.outcome == "WIN")
    losses = sum(1 for t in evaluated if t.outcome == "LOSS")
    flat = sum(1 for t in evaluated if t.outcome == "FLAT")

    if not evaluated:
        return StrategyPerformance(
            strategy=strategy,
            total=len(subset),
            evaluated=0,
            wins=0,
            losses=0,
            flat=0,
            winrate=None,
            avg_return=None,
            cumulative_return=None,
            max_drawdown=None,
        )

    returns = [t.forward_return for t in evaluated if t.forward_return is not None]
    avg_return = sum(returns) / len(returns)

    # Kurva ekuitas (urut tanggal) untuk cumulative return & max drawdown.
    ordered = sorted(evaluated, key=lambda t: t.date)
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for trade in ordered:
        equity *= 1 + (trade.forward_return or 0.0)
        peak = max(peak, equity)
        if peak:
            max_dd = max(max_dd, (peak - equity) / peak)

    return StrategyPerformance(
        strategy=strategy,
        total=len(subset),
        evaluated=len(evaluated),
        wins=wins,
        losses=losses,
        flat=flat,
        winrate=round(wins / len(evaluated), 4),
        avg_return=round(avg_return, 4),
        cumulative_return=round(equity - 1, 4),
        max_drawdown=round(max_dd, 4),
    )
