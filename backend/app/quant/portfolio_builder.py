"""Portfolio Builder (Phase 4, Day 12).

Menyusun portofolio otomatis (alokasi bobot) sesuai profil risiko user dengan
MENGGABUNGKAN komponen yang sudah ada:
  - Composite Score (Phase 2, app.api.ranking) → pilih kandidat berkualitas.
  - Risk Meter (Phase 2, app.core.risk_meter)  → saring sesuai profil risiko.
  - Correlation Matrix (Phase 4, Day 9)        → jaga diversifikasi.

Metode = HEURISTIK (bukan mean-variance/PyPortfolioOpt - dihindari di Windows):
  1. Skor seluruh universe; saring kandidat sesuai level risiko yang diizinkan.
  2. Seleksi greedy menurut skor: lewati kandidat yang korelasinya dengan saham
     terpilih >= ambang (jaga diversifikasi), sampai jumlah posisi maksimum.
  3. Bobot = skor-tertimbang, lalu cap bobot per posisi & redistribusi, sehingga
     total = 100%. Alokasikan ke modal.

Hasil bisa disimpan ke tabel portfolio (opsional). BUKAN nasihat keuangan.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.api.ranking import run_ranking
from app.api.risk import build_risk_input
from app.core import risk_meter
from app.core.instruments import is_index
from app.db.models import MarketData
from app.db.models import Portfolio
from app.quant import correlation_matrix as cm

#: Parameter heuristik per profil risiko.
RISK_PROFILES: dict[str, dict] = {
    "CONSERVATIVE": {
        "max_positions": 8,
        "weight_cap": 0.20,
        "corr_threshold": 0.60,  # paksa diversifikasi ketat
        "allowed_levels": {"LOW", "MEDIUM"},  # hindari saham High Risk
    },
    "MODERATE": {
        "max_positions": 7,
        "weight_cap": 0.25,
        "corr_threshold": 0.70,
        "allowed_levels": {"LOW", "MEDIUM", "HIGH"},
    },
    "AGGRESSIVE": {
        "max_positions": 5,
        "weight_cap": 0.40,  # boleh lebih terkonsentrasi
        "corr_threshold": 0.80,
        "allowed_levels": {"LOW", "MEDIUM", "HIGH"},
    },
}


def apply_weight_cap(weights: dict[str, float], cap: float) -> dict[str, float]:
    """Cap tiap bobot lalu redistribusi kelebihan proporsional. Total tetap ~1.

    Bila cap tak feasible (n * cap < 1), naikkan cap efektif ke 1/n agar total
    bisa mencapai 1 (jatuh ke equal-weight saat ekstrem).
    """
    if not weights:
        return {}
    n = len(weights)
    cap = max(cap, 1.0 / n)  # jamin feasibilitas
    w = dict(weights)
    for _ in range(100):
        over = {k: v for k, v in w.items() if v > cap + 1e-12}
        if not over:
            break
        excess = sum(v - cap for v in over.values())
        for k in over:
            w[k] = cap
        room_keys = [k for k, v in w.items() if v < cap - 1e-12]
        base = sum(w[k] for k in room_keys)
        if not room_keys or base <= 0:
            break
        for k in room_keys:
            w[k] += excess * (w[k] / base)
    total = sum(w.values())
    return {k: v / total for k, v in w.items()} if total > 0 else w


def _candidate_data(db: Session, tickers: set[str]) -> dict[str, dict]:
    """{ticker: {score, name, sector, close}} untuk tiap ticker di universe."""
    ranking = run_ranking(db, limit=10_000, use_ml=False)
    out: dict[str, dict] = {}
    for item in ranking["items"]:
        if item["ticker"] in tickers:
            out[item["ticker"]] = {
                "score": item["overall_score"],
                "name": item["name"],
                "sector": item["sector"],
                "close": item["close"],
            }
    return out


def _load_all_bars(db: Session) -> dict[str, list[MarketData]]:
    """Seluruh bar non-indeks dikelompokkan per ticker, kronologis (sekali muat)."""
    rows = db.scalars(select(MarketData).order_by(MarketData.ticker, MarketData.date))
    grouped: dict[str, list[MarketData]] = {}
    for row in rows:
        if is_index(row.ticker):
            continue
        grouped.setdefault(row.ticker, []).append(row)
    return grouped


def _market_map_from(bars_by_ticker: dict[str, list[MarketData]]) -> dict:
    """Proxy index = rata-rata return harian seluruh saham per tanggal."""
    sums: dict = {}
    counts: dict = {}
    for bars in bars_by_ticker.values():
        for i in range(1, len(bars)):
            prev, cur = bars[i - 1].close, bars[i].close
            if prev and cur:
                day = bars[i].date
                sums[day] = sums.get(day, 0.0) + (cur / prev - 1)
                counts[day] = counts.get(day, 0) + 1
    return {day: sums[day] / counts[day] for day in sums}


def _risk_for(bars: list[MarketData], market_map: dict) -> risk_meter.RiskResult | None:
    if len(bars) < 2:
        return None
    return risk_meter.compute_risk(build_risk_input(bars, market_map))


def _corr_lookup(db: Session, universe: str, window: int = 90) -> dict[frozenset, float]:
    result = cm.compute_correlation(db, universe=universe, window=window, persist=False)
    return {
        frozenset((p["ticker_a"], p["ticker_b"])): p["correlation"]
        for p in result["pairs"]
    }


def build_portfolio(
    db: Session,
    *,
    risk_profile: str,
    capital: float,
    universe: str = "lq45",
    corr_window: int = 90,
) -> dict:
    """Bangun portofolio sesuai profil risiko. Mengembalikan alokasi + ringkasan."""
    profile = risk_profile.strip().upper()
    if profile not in RISK_PROFILES:
        raise ValueError(f"risk_profile '{risk_profile}' tidak dikenal.")
    cfg = RISK_PROFILES[profile]

    tickers = set(cm.resolve_universe(db, universe))
    candidates = _candidate_data(db, tickers)
    bars_by_ticker = _load_all_bars(db)
    market_map = _market_map_from(bars_by_ticker)
    corr = _corr_lookup(db, universe, corr_window)

    # Lampirkan risiko & saring level yang diizinkan.
    enriched: list[dict] = []
    for ticker, info in candidates.items():
        bars = bars_by_ticker.get(ticker, [])
        risk = _risk_for(bars, market_map)
        if risk is None or risk.risk not in cfg["allowed_levels"]:
            continue
        enriched.append({**info, "ticker": ticker, "risk_level": risk.risk, "risk_score": risk.score})

    enriched.sort(key=lambda c: c["score"], reverse=True)

    # Seleksi greedy dengan filter korelasi.
    selected: list[dict] = []
    for cand in enriched:
        too_correlated = any(
            corr.get(frozenset((cand["ticker"], s["ticker"])), 0.0) >= cfg["corr_threshold"]
            for s in selected
        )
        if too_correlated:
            continue
        selected.append(cand)
        if len(selected) >= cfg["max_positions"]:
            break

    if not selected:
        return _empty_result(profile, capital, universe)

    # Bobot skor-tertimbang → cap → alokasi modal.
    total_score = sum(c["score"] for c in selected) or 1.0
    raw_weights = {c["ticker"]: c["score"] / total_score for c in selected}
    weights = apply_weight_cap(raw_weights, cfg["weight_cap"])

    allocations = [
        {
            "ticker": c["ticker"],
            "name": c["name"],
            "sector": c["sector"],
            "weight": round(weights[c["ticker"]], 4),
            "amount": round(weights[c["ticker"]] * capital, 2),
            "score": c["score"],
            "risk_level": c["risk_level"],
            "risk_score": c["risk_score"],
        }
        for c in selected
    ]
    allocations.sort(key=lambda a: a["weight"], reverse=True)

    weighted_risk = sum(a["weight"] * a["risk_score"] for a in allocations)
    return {
        "risk_profile": profile,
        "capital": capital,
        "universe": universe,
        "n_positions": len(allocations),
        "allocations": allocations,
        "summary": {
            "weighted_risk_score": round(weighted_risk, 1),
            "portfolio_risk_level": risk_meter._classify(weighted_risk),
            "avg_correlation": round(_avg_pairwise_corr(selected, corr), 4),
            "config": cfg,
        },
    }


def _avg_pairwise_corr(selected: list[dict], corr: dict[frozenset, float]) -> float:
    pairs = [
        corr.get(frozenset((a["ticker"], b["ticker"])), 0.0)
        for i, a in enumerate(selected)
        for b in selected[i + 1 :]
    ]
    return sum(pairs) / len(pairs) if pairs else 0.0


def _empty_result(profile: str, capital: float, universe: str) -> dict:
    return {
        "risk_profile": profile,
        "capital": capital,
        "universe": universe,
        "n_positions": 0,
        "allocations": [],
        "summary": {"weighted_risk_score": 0.0, "portfolio_risk_level": "LOW",
                    "avg_correlation": 0.0, "config": RISK_PROFILES[profile]},
    }


def persist_portfolio(
    db: Session, *, user_id: str | None, risk_profile: str, allocations: list[dict]
) -> int:
    """Simpan hasil builder ke tabel portfolio (opsional). Mengembalikan id."""
    payload = [{"ticker": a["ticker"], "weight": a["weight"]} for a in allocations]
    stmt = (
        pg_insert(Portfolio)
        .values(user_id=user_id, risk_profile=risk_profile.upper(), allocations=payload)
        .returning(Portfolio.id)
    )
    new_id = db.execute(stmt).scalar_one()
    db.commit()
    return new_id


def _main() -> None:
    import sys

    from app.db.session import SessionLocal

    if SessionLocal is None:
        raise SystemExit("DATABASE_URL belum diset di backend/.env")
    profile = sys.argv[1] if len(sys.argv) > 1 else "MODERATE"
    db = SessionLocal()
    try:
        r = build_portfolio(db, risk_profile=profile, capital=100_000_000, universe="lq45")
        print(f"Portofolio {r['risk_profile']} (modal Rp{r['capital']:,.0f}, {r['n_positions']} posisi):")
        for a in r["allocations"]:
            print(
                f"  {a['ticker']:<6} {a['weight']*100:5.1f}%  Rp{a['amount']:>14,.0f}  "
                f"score={a['score']:.0f} risk={a['risk_level']}"
            )
        s = r["summary"]
        print(
            f"  -> risk portofolio={s['portfolio_risk_level']} "
            f"(skor {s['weighted_risk_score']}), korelasi rata2={s['avg_correlation']}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    _main()
