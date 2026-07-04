"""Advanced Performance Metrics API (Phase 4, Day 4).

GET /api/performance/{strategy}
  Metrik kuantitatif (CAGR, Sharpe, Sortino, Calmar, Profit Factor, Recovery
  Factor, Max Drawdown, Winrate) untuk satu strategi TERVALIDASI (5 teknikal),
  dihitung dari trade log replay_history. Disimpan ke strategy_performance &
  di-cache. SELALU menyertakan metodologi + disclaimer.

Strategi fundamental DIKECUALIKAN dari validasi historis (404) - tidak ada data
fundamental point-in-time (lihat app/quant/__init__.py).

Query params:
  hold    : horizon holding hari bursa (1/3/7/30, default 7)
  refresh : abaikan cache & hitung ulang
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cache import redis_client
from app.db.models import ReplayHistory
from app.db.session import get_db
from app.quant import performance_metrics as pm

router = APIRouter(prefix="/api/performance", tags=["performance"])

CACHE_KEY = "performance:{strategy}:hold={hold}"

DISCLAIMER = (
    "Metrik historis adalah alat bantu analisis/edukasi, BUKAN rekomendasi "
    "jual/beli maupun jaminan kinerja masa depan. Hasil mengandung asumsi biaya "
    "0,3% per trade & keterbatasan survivorship (hanya saham yang masih listing)."
)


class PerformanceResponse(BaseModel):
    strategy: str
    name: str | None = None
    period: str
    metrics: dict[str, float]
    n_trades: int
    n_periods: int
    active_periods: int
    start: str | None
    end: str | None
    hold: int
    methodology: str
    disclaimer: str
    cached: bool
    generated_at: str


@router.get("/{strategy}", response_model=PerformanceResponse)
def get_performance(
    strategy: str,
    hold: int = Query(pm.DEFAULT_HOLD),
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict:
    strategy = strategy.strip().lower()

    if strategy not in pm.VALIDATED_STRATEGIES:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Strategi '{strategy}' tidak divalidasi historis. Hanya strategi "
                f"teknikal yang didukung: {', '.join(pm.VALIDATED_STRATEGIES)}."
            ),
        )
    if hold not in (1, 3, 7, 30):
        raise HTTPException(status_code=422, detail="hold harus salah satu dari 1/3/7/30.")

    cache_key = CACHE_KEY.format(strategy=strategy, hold=hold)
    if not refresh:
        cached = redis_client.cache_get_json(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    result = pm.compute_for_strategy(db, strategy, hold=hold)
    n_trades = db.scalar(
        select(func.count())
        .select_from(ReplayHistory)
        .where(ReplayHistory.strategy == strategy)
        .where(getattr(ReplayHistory, pm._HORIZON_COLUMN[hold]).is_not(None))
    ) or 0

    # Persist hanya untuk hold kanonik (period=ALL) agar tabel konsisten Day 6.
    if hold == pm.DEFAULT_HOLD:
        pm.persist_performance(db, strategy, result["metrics"], period="ALL")

    payload = PerformanceResponse(
        strategy=strategy,
        name=pm.strategy_display_name(strategy),
        period="ALL",
        metrics={k: round(v, 6) for k, v in result["metrics"].items()},
        n_trades=int(n_trades),
        n_periods=result["n_periods"],
        active_periods=result["active_periods"],
        start=result["start"],
        end=result["end"],
        hold=hold,
        methodology=(
            f"Rebalancing kohort non-overlap {hold} hari bursa, basket equal-weight; "
            f"biaya round-trip 0,3% per trade; Rf {pm.RISK_FREE_ANNUAL*100:.0f}%/tahun; "
            f"anualisasi {pm.TRADING_DAYS} hari bursa ({result['periods_per_year']} periode/tahun)."
        ),
        disclaimer=DISCLAIMER,
        cached=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
    ).model_dump()

    redis_client.cache_set_json(cache_key, payload, ttl=redis_client.TTL_QUANT)
    return payload
