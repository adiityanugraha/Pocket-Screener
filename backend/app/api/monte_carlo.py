"""Monte Carlo Simulation API (Phase 4, Day 10).

GET /api/monte-carlo/{strategy}
  Sebaran hasil masa depan (1 tahun default) via bootstrap return historis:
  Probability of Profit, Worst Case (P5), Expected (median), Best Case (P95)
  + histogram. Hanya strategi TERVALIDASI (5 teknikal).

Query params:
  hold          : horizon holding seri sumber (1/3/7/30, default 30)
  horizon_years : panjang horizon simulasi (0.25..5, default 1)
  simulations   : jumlah lintasan (1000..50000, default 5000)
  refresh       : abaikan cache
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.cache import redis_client
from app.db.session import get_db
from app.quant import monte_carlo as mc
from app.quant import performance_metrics as pm

router = APIRouter(prefix="/api/monte-carlo", tags=["monte-carlo"])

CACHE_KEY = "monte-carlo:{strategy}:hold={hold}:y={years}:sims={sims}"

DISCLAIMER = (
    "Simulasi Monte Carlo BUKAN ramalan atau jaminan. Hasil mengasumsikan pola "
    "return historis berulang & independen - kondisi pasar nyata bisa berbeda "
    "jauh. Gunakan hanya sebagai gambaran sebaran risiko, bukan prediksi."
)


class MonteCarloResponse(BaseModel):
    strategy: str
    name: str | None = None
    hold: int
    horizon_years: float
    n_periods: int
    simulations: int
    history_periods: int
    probability_of_profit: float
    mean: float
    percentiles: dict[str, float]
    histogram: list[dict]
    disclaimer: str
    cached: bool
    generated_at: str


@router.get("/{strategy}", response_model=MonteCarloResponse)
def get_monte_carlo(
    strategy: str,
    hold: int = Query(pm.DEFAULT_HOLD),
    horizon_years: float = Query(mc.DEFAULT_HORIZON_YEARS, ge=0.25, le=5.0),
    simulations: int = Query(mc.DEFAULT_SIMULATIONS, ge=1000, le=50000),
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict:
    strategy = strategy.strip().lower()
    if strategy not in pm.VALIDATED_STRATEGIES:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Strategi '{strategy}' tidak divalidasi historis. Hanya strategi "
                f"teknikal: {', '.join(pm.VALIDATED_STRATEGIES)}."
            ),
        )
    if hold not in (1, 3, 7, 30):
        raise HTTPException(status_code=422, detail="hold harus salah satu dari 1/3/7/30.")

    cache_key = CACHE_KEY.format(
        strategy=strategy, hold=hold, years=horizon_years, sims=simulations
    )
    if not refresh:
        cached = redis_client.cache_get_json(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    result = mc.monte_carlo_strategy(
        db, strategy, hold=hold, horizon_years=horizon_years, n_sims=simulations
    )
    if result["simulations"] == 0:
        raise HTTPException(
            status_code=422, detail=f"Data historis '{strategy}' belum cukup untuk simulasi."
        )

    payload = MonteCarloResponse(
        strategy=result["strategy"],
        name=result["name"],
        hold=result["hold"],
        horizon_years=result["horizon_years"],
        n_periods=result["n_periods"],
        simulations=result["simulations"],
        history_periods=result["history_periods"],
        probability_of_profit=round(result["probability_of_profit"], 4),
        mean=round(result["mean"], 6),
        percentiles={k: round(v, 6) for k, v in result["percentiles"].items()},
        histogram=result["histogram"],
        disclaimer=DISCLAIMER,
        cached=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
    ).model_dump()

    redis_client.cache_set_json(cache_key, payload, ttl=redis_client.TTL_QUANT)
    return payload
