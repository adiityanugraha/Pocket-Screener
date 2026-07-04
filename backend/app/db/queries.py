"""Helper query market_data yang hemat memori.

Banyak endpoint universe (ranking, screener, market breadth) dulu memuat SELURUH
tabel market_data (≈188 ribu baris ORM) ke memori hanya untuk memakai indikator
bar-bar terakhir tiap saham - ini penyebab utama OOM di container kecil.

`load_recent_bars_by_ticker` membatasi muatan ke jendela tanggal terakhir saja,
cukup untuk indikator/momentum yang sudah pre-computed, sehingga memori turun
drastis (mis. 10 tahun -> ~3 bulan).
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import MarketData


def load_recent_bars_by_ticker(
    db: Session,
    *,
    lookback_days: int,
    as_of: date_cls | None = None,
) -> dict[str, list[MarketData]]:
    """Muat bar market_data `lookback_days` hari kalender terakhir, dikelompokkan
    per ticker (urut kronologis).

    Args:
        lookback_days: lebar jendela dalam HARI KALENDER (longgar; ~21 hari kalender
            ≈ 15 hari bursa). Pilih cukup besar untuk indikator terpanjang yang
            dipakai konsumen, tapi jauh lebih kecil dari seluruh histori.
        as_of: batas akhir jendela. Default = tanggal terbaru di market_data.
    """
    if as_of is None:
        as_of = db.scalar(select(func.max(MarketData.date)))
        if as_of is None:
            return {}

    cutoff = as_of - timedelta(days=lookback_days)
    rows = db.scalars(
        select(MarketData)
        .where(MarketData.date >= cutoff, MarketData.date <= as_of)
        .order_by(MarketData.ticker, MarketData.date)
    )
    grouped: dict[str, list[MarketData]] = {}
    for row in rows:
        grouped.setdefault(row.ticker, []).append(row)
    return grouped
