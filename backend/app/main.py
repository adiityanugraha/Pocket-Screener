"""FastAPI entrypoint - Pocket Screener Phase 2 backend.

Jalankan (dari folder backend/, venv aktif):
    uvicorn app.main:app --reload --port 8000

Health check: http://localhost:8000/api/health
Docs (Swagger): http://localhost:8000/docs
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    ai_analysis,
    benchmark,
    chat,
    compare_strategy,
    correlation,
    daily_report,
    equity_curve,
    explain,
    explain_score,
    forecast,
    fundamentals,
    health,
    history,
    market_breadth,
    market_data,
    market_summary,
    meta,
    monte_carlo,
    natural_query,
    performance,
    portfolio_advisor,
    portfolio_builder,
    ranking,
    replay,
    risk_profile,
    risk,
    screener,
    sector_rotation,
    stock_report,
    strategies,
    strategy_matrix,
    strength,
    support_resistance,
    walkforward,
    why,
)
from app.core.config import get_settings
from app.scheduler import scheduler as scheduler_module

settings = get_settings()
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop scheduler job harian bersama siklus hidup aplikasi (Day 13)."""
    if settings.scheduler_enabled:
        scheduler_module.start()
    else:
        log.info("Scheduler dimatikan (SCHEDULER_ENABLED=false).")
    try:
        yield
    finally:
        scheduler_module.shutdown()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Backend Pocket Screener Phase 2: screener, scoring, analytics & reporting.",
    lifespan=lifespan,
)

# CORS - frontend (Next.js) memanggil API ini dari origin yang berbeda.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------- #
# Rate limiting sederhana (in-memory, per-IP, fixed window) - tanpa dependensi.
# Melindungi API publik dari spam: endpoint LLM (Gemini, berbiaya) dibatasi lebih
# ketat daripada endpoint biasa. Cukup untuk 1 instance Railway; untuk multi-
# instance pakai store bersama (Redis).
# --------------------------------------------------------------------------- #
_RATE_WINDOW_SEC = 60
_RATE_LIMIT_DEFAULT = 200  # request/menit/IP untuk endpoint umum
_RATE_LIMIT_LLM = 20  # lebih ketat untuk endpoint yang memanggil Gemini
_LLM_PATH_PREFIXES = ("/api/chat", "/api/natural-query")
_rate_hits: dict[tuple[str, str], list[float]] = defaultdict(list)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    path = request.url.path
    # Lewati preflight CORS & health check.
    if request.method == "OPTIONS" or path == "/api/health":
        return await call_next(request)

    is_llm = path.startswith(_LLM_PATH_PREFIXES)
    limit = _RATE_LIMIT_LLM if is_llm else _RATE_LIMIT_DEFAULT
    bucket = "llm" if is_llm else "default"
    client_ip = request.client.host if request.client else "unknown"
    key = (client_ip, bucket)

    now = time.monotonic()
    window_start = now - _RATE_WINDOW_SEC
    hits = _rate_hits[key]
    hits[:] = [t for t in hits if t >= window_start]  # buang yang kedaluwarsa

    if len(hits) >= limit:
        return JSONResponse(
            status_code=429,
            content={"detail": "Terlalu banyak permintaan. Coba lagi sebentar."},
        )

    hits.append(now)
    if not hits:
        _rate_hits.pop(key, None)  # jaga dict tetap ramping
    return await call_next(request)


# Routers
app.include_router(health.router)
app.include_router(meta.router)
app.include_router(performance.router)
app.include_router(equity_curve.router)
app.include_router(benchmark.router)
app.include_router(replay.router)
app.include_router(risk_profile.router)
app.include_router(correlation.router)
app.include_router(monte_carlo.router)
app.include_router(walkforward.router)
app.include_router(portfolio_builder.router)
app.include_router(strategies.router)
app.include_router(strategy_matrix.router)
app.include_router(strength.router)
app.include_router(explain.router)
app.include_router(why.router)
app.include_router(forecast.router)
app.include_router(fundamentals.router)
app.include_router(screener.router)
app.include_router(market_data.router)
app.include_router(ranking.router)
app.include_router(stock_report.router)
app.include_router(risk.router)
app.include_router(support_resistance.router)
app.include_router(market_breadth.router)
app.include_router(history.router)
app.include_router(sector_rotation.router)
app.include_router(ai_analysis.router)
app.include_router(explain_score.router)
app.include_router(chat.router)
app.include_router(natural_query.router)
app.include_router(compare_strategy.router)
app.include_router(portfolio_advisor.router)
app.include_router(market_summary.router)
app.include_router(daily_report.router)


@app.get("/")
async def root() -> dict:
    return {
        "message": f"{settings.app_name} is running.",
        "docs": "/docs",
        "health": "/api/health",
    }
