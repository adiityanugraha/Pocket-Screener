"""Portfolio Builder API (Phase 4, Day 12).

POST /api/portfolio-builder
  Body: { "risk": "MODERATE", "capital": 100000000, "universe": "lq45" }
  Menyusun alokasi portofolio (Composite Score + Risk Meter + Correlation) sesuai
  profil risiko. Opsional menyimpan hasil ke tabel portfolio (save=true).

BUKAN nasihat keuangan - hanya alat bantu analisis/edukasi.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.quant import portfolio_builder as pb

router = APIRouter(prefix="/api/portfolio-builder", tags=["portfolio-builder"])

DISCLAIMER = (
    "Portfolio Builder adalah alat bantu analisis/edukasi berbasis skor & metrik "
    "historis, BUKAN nasihat keuangan atau rekomendasi jual/beli. Keputusan "
    "investasi & risikonya sepenuhnya tanggung jawab Anda."
)


class PortfolioRequest(BaseModel):
    risk: str = Field(..., description="CONSERVATIVE | MODERATE | AGGRESSIVE")
    capital: float = Field(100_000_000, gt=0)
    universe: str = Field("lq45", description="all | lq45 | screened")
    save: bool = Field(False, description="Simpan hasil ke tabel portfolio")
    user_id: str | None = Field(None, description="Pemilik (opsional)")


class PortfolioResponse(BaseModel):
    risk_profile: str
    capital: float
    universe: str
    n_positions: int
    allocations: list[dict]
    summary: dict
    saved_id: int | None = None
    disclaimer: str
    generated_at: str


@router.post("", response_model=PortfolioResponse)
def post_portfolio_builder(
    body: PortfolioRequest,
    db: Session = Depends(get_db),
) -> dict:
    profile = body.risk.strip().upper()
    if profile not in pb.RISK_PROFILES:
        raise HTTPException(
            status_code=422,
            detail=f"risk harus salah satu dari {', '.join(pb.RISK_PROFILES)}.",
        )
    universe = body.universe.strip().lower()
    if universe not in ("all", "lq45", "screened"):
        raise HTTPException(status_code=422, detail="universe harus all|lq45|screened.")

    result = pb.build_portfolio(
        db, risk_profile=profile, capital=body.capital, universe=universe
    )
    if result["n_positions"] == 0:
        raise HTTPException(
            status_code=422,
            detail="Tidak ada kandidat yang lolos filter risiko/korelasi untuk profil ini.",
        )

    saved_id = None
    if body.save:
        saved_id = pb.persist_portfolio(
            db, user_id=body.user_id, risk_profile=profile, allocations=result["allocations"]
        )

    return PortfolioResponse(
        risk_profile=result["risk_profile"],
        capital=result["capital"],
        universe=result["universe"],
        n_positions=result["n_positions"],
        allocations=result["allocations"],
        summary=result["summary"],
        saved_id=saved_id,
        disclaimer=DISCLAIMER,
        generated_at=datetime.now(timezone.utc).isoformat(),
    ).model_dump()
