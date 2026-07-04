"""Correlation Matrix (Phase 4, Day 9).

Korelasi Pearson antar return HARIAN saham untuk membantu diversifikasi
portofolio (hindari menumpuk saham yang bergerak seragam). Matriks penuh
seluruh IDX = O(n^2) → universe DIBATASI (LQ45 / ter-screen / semua large-cap
yang dimiliki). Hanya pasangan unik (ticker_a < ticker_b) disimpan ke tabel
correlation_matrix; respons penuh di-cache di Redis.

Window default 90 hari bursa (korelasi terkini). Saham dengan data tidak lengkap
pada window itu atau varians nol di-skip.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import distinct, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.instruments import is_index
from app.db.models import CorrelationMatrix, MarketData, ReplayHistory, Stock

DEFAULT_WINDOW = 90

#: Subset LQ45 (large-cap likuid) yang ada di universe - pembatas O(n^2) baku.
#: Di-intersect dengan ticker yang tersedia, jadi aman bila komposisi berubah.
LQ45 = frozenset({
    "ACES", "ADRO", "AKRA", "AMRT", "ANTM", "ARTO", "ASII", "BBCA", "BBNI",
    "BBRI", "BBTN", "BMRI", "BRIS", "BRPT", "BUKA", "CPIN", "CTRA", "ESSA",
    "GGRM", "GOTO", "HRUM", "ICBP", "INCO", "INDF", "INKP", "INTP", "ISAT",
    "ITMG", "JPFA", "JSMR", "KLBF", "MAPA", "MAPI", "MBMA", "MDKA", "MEDC",
    "MTEL", "PGAS", "PTBA", "SIDO", "SMGR", "TLKM", "TOWR", "TPIA", "UNTR",
    "UNVR",
})


def resolve_universe(db: Session, universe: str) -> list[str]:
    """Daftar ticker untuk universe yang diminta (selalu di-intersect ketersediaan)."""
    available = [t for t in db.scalars(select(Stock.ticker).order_by(Stock.ticker)) if not is_index(t)]
    key = universe.strip().lower()
    if key == "all":
        return available
    if key == "lq45":
        avail = set(available)
        return [t for t in sorted(LQ45) if t in avail]
    if key == "screened":
        screened = set(db.scalars(select(distinct(ReplayHistory.ticker))))
        return [t for t in available if t in screened]
    raise ValueError(f"universe '{universe}' tidak dikenal (all|lq45|screened).")


def _correlation_frame(db: Session, tickers: list[str], window: int) -> pd.DataFrame:
    """Matriks korelasi Pearson (DataFrame) return harian atas window terakhir.

    Memakai UNION tanggal terbaru sebagai kalender lalu forward/back-fill celah
    suspensi per saham (alih-alih membuang saham yang absen 1-2 hari). Ticker
    dengan varians nol (tak bergerak) di-buang. DataFrame kosong bila < 2 ticker.
    """
    cal_dates = list(
        db.scalars(
            select(distinct(MarketData.date)).order_by(MarketData.date.desc()).limit(window + 1)
        )
    )
    if len(cal_dates) < window + 1:
        return pd.DataFrame()
    cal_dates.sort()

    rows = db.execute(
        select(MarketData.ticker, MarketData.date, MarketData.close)
        .where(MarketData.ticker.in_(tickers))
        .where(MarketData.date.in_(cal_dates))
    ).all()
    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows, columns=["ticker", "date", "close"])
    wide = (
        frame.pivot(index="date", columns="ticker", values="close")
        .reindex(cal_dates)
        .ffill()
        .bfill()
    )
    returns = wide.pct_change().iloc[1:]
    returns = returns.loc[:, returns.std() > 0]  # buang yang tak bergerak / NaN
    returns = returns.dropna(axis=1, how="any")
    if returns.shape[1] < 2:
        return pd.DataFrame()
    return returns.corr()


def _persist_pairs(db: Session, pairs: list[dict]) -> int:
    if not pairs:
        return 0
    stmt = pg_insert(CorrelationMatrix).values(pairs)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker_a", "ticker_b", "window"],
        set_={"correlation": stmt.excluded.correlation, "computed_at": datetime.now(timezone.utc)},
    )
    db.execute(stmt)
    db.commit()
    return len(pairs)


def compute_correlation(
    db: Session,
    *,
    universe: str = "lq45",
    window: int = DEFAULT_WINDOW,
    persist: bool = True,
) -> dict:
    """Hitung matriks korelasi Pearson untuk universe. Persist pasangan unik."""
    tickers = resolve_universe(db, universe)
    corr_df = _correlation_frame(db, tickers, window)
    window_label = f"{window}d"

    if corr_df.empty:
        return {
            "universe": universe,
            "window": window_label,
            "tickers": [],
            "matrix": [],
            "pairs": [],
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    valid = list(corr_df.columns)
    corr = corr_df.to_numpy()
    n = len(valid)

    pairs: list[dict] = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = valid[i], valid[j]
            if a > b:
                a, b = b, a
            pairs.append(
                {"ticker_a": a, "ticker_b": b, "window": window_label,
                 "correlation": float(corr[i][j])}
            )

    if persist:
        _persist_pairs(db, pairs)

    return {
        "universe": universe,
        "window": window_label,
        "tickers": valid,
        "matrix": [[round(float(corr[i][j]), 4) for j in range(n)] for i in range(n)],
        "pairs": pairs,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def top_correlated(pairs: list[dict], limit: int = 10) -> list[dict]:
    """Pasangan paling berkorelasi (untuk peringatan konsentrasi)."""
    return sorted(pairs, key=lambda p: p["correlation"], reverse=True)[:limit]


def _main() -> None:
    import sys

    from app.db.session import SessionLocal

    if SessionLocal is None:
        raise SystemExit("DATABASE_URL belum diset di backend/.env")
    universe = sys.argv[1] if len(sys.argv) > 1 else "lq45"
    db = SessionLocal()
    try:
        result = compute_correlation(db, universe=universe)
        print(
            f"Korelasi universe={universe} window={result['window']}: "
            f"{len(result['tickers'])} ticker, {len(result['pairs'])} pasangan."
        )
        for p in top_correlated(result["pairs"], 8):
            print(f"  {p['ticker_a']}-{p['ticker_b']}: {p['correlation']:+.2f}")
    finally:
        db.close()


if __name__ == "__main__":
    _main()
