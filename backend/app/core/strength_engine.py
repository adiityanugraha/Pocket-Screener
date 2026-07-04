"""Screener Strength Score lintas-strategi (Phase 3 Day 9).

Menggabungkan SEMUA strategi yang lolos untuk satu saham menjadi satu skor
0-100. Berbeda dari Composite Score Phase 2 (fokus 1 strategi/indikator),
Strength Score melihat LINTAS strategi: makin banyak strategi (terutama yang
berbobot tinggi) yang lolos, makin kuat.

Formula (transparan & configurable):
    points   = Σ bobot(strategi) untuk strategi yang lolos
    strength = round(100 * min(points, full_points) / full_points)

Bobot default per TIPE strategi (configurable per request):
    technical   = 1.0
    fundamental = 1.5   (lebih berat - sinyal kualitas jangka panjang)
full_points default 6.0 (≈ lolos seluruh 4 strategi fundamental -> 100).

Logika murni (compute_strength) tak menyentuh DB - pemanggil menyuplai daftar
strategi yang lolos beserta tipenya.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_TYPE_WEIGHTS: dict[str, float] = {"technical": 1.0, "fundamental": 1.5}
DEFAULT_FULL_POINTS = 6.0


@dataclass(frozen=True)
class StrengthComponent:
    strategy: str
    type: str
    weight: float


@dataclass(frozen=True)
class StrengthResult:
    ticker: str
    strength: int  # 0-100
    points: float
    max_points: float
    passed_strategies: list[str] = field(default_factory=list)
    breakdown: list[StrengthComponent] = field(default_factory=list)


def type_weight(strategy_type: str, weights: dict[str, float] | None = None) -> float:
    weights = weights or DEFAULT_TYPE_WEIGHTS
    return weights.get(strategy_type, 1.0)


def compute_strength(
    ticker: str,
    passed: list[tuple[str, str]],
    weights: dict[str, float] | None = None,
    full_points: float = DEFAULT_FULL_POINTS,
) -> StrengthResult:
    """Hitung Strength Score dari daftar strategi lolos.

    passed      : list (strategy_key, strategy_type) untuk strategi yang LOLOS.
    weights     : bobot per tipe (default technical 1.0, fundamental 1.5).
    full_points : poin untuk mencapai 100 (configurable).
    """
    if full_points <= 0:
        raise ValueError("full_points harus > 0")

    breakdown = [
        StrengthComponent(strategy=key, type=stype, weight=type_weight(stype, weights))
        for key, stype in passed
    ]
    points = sum(component.weight for component in breakdown)
    strength = round(100 * min(points, full_points) / full_points)

    return StrengthResult(
        ticker=ticker,
        strength=strength,
        points=points,
        max_points=full_points,
        passed_strategies=[component.strategy for component in breakdown],
        breakdown=breakdown,
    )
