"""Meta API - info ringan untuk frontend (tanggal data terbaru, ukuran universe).

GET /api/meta
  Dipakai header/footer agar label "Data per ..." mencerminkan tanggal data
  ASLI di market_data, bukan tanggal hardcoded.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import MarketData, Stock
from app.db.session import get_db

router = APIRouter(prefix="/api/meta", tags=["meta"])


class MetaResponse(BaseModel):
    data_date: str | None = None
    universe: int


@router.get("", response_model=MetaResponse)
def get_meta(db: Session = Depends(get_db)) -> dict:
    latest = db.scalar(select(func.max(MarketData.date)))
    universe = db.scalar(select(func.count()).select_from(Stock)) or 0
    return {
        "data_date": latest.isoformat() if latest else None,
        "universe": int(universe),
    }
