"""Fondasi Strategy Registry (Phase 3 Day 1).

Interface seragam untuk SEMUA strategi screening (teknikal & fundamental):

    strategy.run(StockData) -> StrategyResult(passed, criteria, matched_criteria)

Kontrak penting:
  - `criteria`         : dict key -> bool, SEMUA kriteria strategi (lolos/tidak).
                         Key BSJP/BPJS dipertahankan sama persis dengan Phase 2
                         (price_vs_previous, dst.) agar hasil regression-identik.
  - `matched_criteria` : deskripsi human-readable HANYA untuk kriteria yang lolos,
                         berisi angka aktual - dipakai Explainable AI / "Why
                         Selected" (Day 10) sehingga penjelasan otomatis akurat.
  - `evaluated=False`  : data tidak cukup untuk menilai (mis. bar < minimum);
                         beda makna dengan "dinilai lalu gagal".

Strategi fundamental (Day 6-7) memakai field `fundamentals` di StockData;
untuk strategi teknikal field itu None dan diabaikan.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar

from app.core.fundamentals import FundamentalView
from app.core.screener import OhlcvBar


class StrategyType(str, Enum):
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"


@dataclass(frozen=True)
class StockData:
    """Snapshot satu saham yang dinilai strategi.

    bars         : OHLCV harian urut kronologis (terakhir = hari berjalan).
    fundamentals : FundamentalView (raw + derived + growth) bila tersedia; None
                   untuk saham tanpa data fundamental. Strategi teknikal
                   mengabaikannya; strategi fundamental mengembalikan
                   NOT_EVALUATED bila None.
    """

    ticker: str
    bars: list[OhlcvBar]
    fundamentals: FundamentalView | None = None


@dataclass(frozen=True)
class StrategyResult:
    passed: bool
    criteria: dict[str, bool] = field(default_factory=dict)
    matched_criteria: list[str] = field(default_factory=list)
    evaluated: bool = True
    # Kriteria yang DILEWATI karena datanya secara struktural tak tersedia dari
    # sumber gratis (mis. Income From Operations, dividend streak). Strategi
    # dinilai atas subset yang terhitung; field ini membuat keterbatasan itu
    # transparan ke API/explain (kebijakan "proxy + lewati, ditandai", Day 7).
    skipped_criteria: list[str] = field(default_factory=list)


#: Hasil baku saat data tidak cukup - semua strategi memakai ini agar seragam.
NOT_EVALUATED = StrategyResult(passed=False, evaluated=False)


class Strategy(ABC):
    """Satu strategi screening. Subclass wajib mengisi metadata kelas + run()."""

    key: ClassVar[str]  # identifier API/DB, mis. "bsjp", "breakout"
    name: ClassVar[str]  # nama tampilan, mis. "BSJP (Beli Sore Jual Pagi)"
    type: ClassVar[StrategyType]
    output_label: ClassVar[str]  # judul daftar hasil, mis. "Top Breakout Candidates"

    @abstractmethod
    def run(self, data: StockData) -> StrategyResult: ...

    def describe(self) -> dict[str, str]:
        """Metadata untuk GET /api/strategies (Day 3)."""
        return {
            "key": self.key,
            "name": self.name,
            "type": self.type.value,
            "output_label": self.output_label,
        }
