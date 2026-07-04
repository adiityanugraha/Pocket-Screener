"""Market Replay API (Phase 4, Day 7).

GET /api/replay/{date}
  Kandidat per strategi teknikal pada tanggal historis (YYYY-MM-DD) + performa
  forward (+1/+3/+7/+30 hari). Membaca tabel replay_history (materialisasi Day 3).

Respons menyertakan data_range (tanggal valid paling awal & akhir) agar pemilih
tanggal di frontend bisa dibatasi.

Query params:
  limit   : maksimum kandidat per strategi (default 10)
  refresh : abaikan cache
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.cache import redis_client
from app.db.session import get_db
from app.quant import market_replay as mr

router = APIRouter(prefix="/api/replay", tags=["replay"])

CACHE_KEY = "replay:{date}:limit={limit}"

DISCLAIMER = (
    "Replay menampilkan kinerja historis kandidat screening (return forward sudah "
    "termasuk biaya 0,3% per trade) sebagai alat bantu analisis/edukasi - BUKAN "
    "rekomendasi maupun jaminan hasil serupa di masa depan."
)


class ReplayResponse(BaseModel):
    date: str
    total_candidates: int
    strategies: dict[str, list[dict]]
    data_range: dict[str, str | None]
    disclaimer: str
    cached: bool
    generated_at: str


@router.get("/{date}", response_model=ReplayResponse)
def get_replay(
    date: str,
    limit: int = Query(10, ge=1, le=50),
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
) -> dict:
    try:
        target = date_cls.fromisoformat(date.strip())
    except ValueError:
        raise HTTPException(status_code=422, detail="Format tanggal harus YYYY-MM-DD.")

    cache_key = CACHE_KEY.format(date=target.isoformat(), limit=limit)
    if not refresh:
        cached = redis_client.cache_get_json(cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

    result = mr.replay_on_date(db, target, limit=limit)
    earliest, latest = mr.replay_date_range(db)

    payload = ReplayResponse(
        date=result["date"],
        total_candidates=result["total_candidates"],
        strategies=result["strategies"],
        data_range={
            "earliest": earliest.isoformat() if earliest else None,
            "latest": latest.isoformat() if latest else None,
        },
        disclaimer=DISCLAIMER,
        cached=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
    ).model_dump()

    redis_client.cache_set_json(cache_key, payload, ttl=redis_client.TTL_QUANT)
    return payload
