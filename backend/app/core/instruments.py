"""Instrumen indeks (mis. IHSG) - pemisahan dari saham biasa.

IHSG = Indeks Harga Saham Gabungan (Jakarta Composite Index). Disimpan dengan
ticker bersih "IHSG" (tanpa "^" agar aman di URL & primary key), dipetakan ke
simbol Yahoo "^JKSE" hanya saat fetch.

Indeks dipakai sebagai KONTEKS pasar (chart/report/risk/S&R) tetapi DIKECUALIKAN
dari screener, ranking, dan market breadth (ia bukan saham tradable BSJP/BPJS).
"""

from __future__ import annotations

# ticker bersih -> simbol Yahoo Finance
INDEX_SYMBOLS: dict[str, str] = {
    "IHSG": "^JKSE",
}

INDEX_TICKERS: frozenset[str] = frozenset(INDEX_SYMBOLS)


def is_index(ticker: str) -> bool:
    """True bila ticker adalah indeks (dikecualikan dari screener/ranking/breadth)."""
    return ticker.strip().upper() in INDEX_TICKERS
