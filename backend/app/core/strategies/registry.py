"""Strategy Registry - daftar semua strategi screening (Phase 3 Day 1).

Pola pluggable sesuai blueprint: menambah strategi baru = buat 1 file di
folder ini yang memanggil `register(...)` saat import, lalu tambahkan nama
modulnya ke _DEFAULT_MODULES. Engine (run_all) TIDAK perlu diubah.

Pemakaian:
    from app.core.strategies import registry

    registry.load_defaults()                  # idempoten, aman dipanggil ulang
    result = registry.get("bsjp").run(data)   # satu strategi
    results = registry.run_all(data)          # semua strategi -> {key: result}
"""

from __future__ import annotations

from importlib import import_module

from app.core.strategies.base import StockData, Strategy, StrategyResult, StrategyType

# Modul strategi yang dimuat load_defaults(). Urutan = urutan tampil di API.
# LENGKAP: 9 strategi (5 teknikal + 4 fundamental) sesuai blueprint Phase 3.
_DEFAULT_MODULES = [
    "app.core.strategies.bsjp",
    "app.core.strategies.bpjs",
    "app.core.strategies.breakout",
    "app.core.strategies.trend_following",
    "app.core.strategies.potential_reversal",
    "app.core.strategies.high_growth",
    "app.core.strategies.cash_rich",
    "app.core.strategies.turnaround",
    "app.core.strategies.timeless",
]

_strategies: dict[str, Strategy] = {}


def register(strategy: Strategy) -> Strategy:
    """Daftarkan satu instance strategi. Dipanggil modul strategi saat import."""
    existing = _strategies.get(strategy.key)
    if existing is not None:
        if type(existing) is type(strategy):  # re-import modul yang sama -> no-op
            return existing
        raise ValueError(f"Strategy key duplikat: {strategy.key!r}")
    _strategies[strategy.key] = strategy
    return strategy


def load_defaults() -> None:
    """Import semua modul strategi default (idempoten - import di-cache Python)."""
    for module_name in _DEFAULT_MODULES:
        import_module(module_name)


def get(key: str) -> Strategy | None:
    load_defaults()
    return _strategies.get(key)


def all_strategies() -> list[Strategy]:
    load_defaults()
    return list(_strategies.values())


def by_type(strategy_type: StrategyType) -> list[Strategy]:
    return [s for s in all_strategies() if s.type is strategy_type]


def run_all(data: StockData) -> dict[str, StrategyResult]:
    """Engine inti: jalankan SEMUA strategi terdaftar untuk satu saham."""
    return {strategy.key: strategy.run(data) for strategy in all_strategies()}
