"""Health check endpoint.

Melaporkan status aplikasi + konektivitas dependensi (PostgreSQL & Redis).
Pengecekan dependensi aman-gagal: error koneksi dilaporkan sebagai status
"down"/"error", bukan melempar exception, sehingga endpoint selalu merespons.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from app.cache import redis_client
from app.core.config import get_settings
from app.db.session import SessionLocal

router = APIRouter(tags=["health"])


def _check_database() -> str:
    """'ok' bila SELECT 1 sukses, 'not_configured' bila tak ada URL, 'error' bila gagal."""
    if SessionLocal is None:
        return "not_configured"
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
        return "ok"
    except Exception:  # noqa: BLE001 - health check tidak boleh melempar
        return "error"


def _check_redis() -> str:
    if not get_settings().redis_url:
        return "not_configured"
    return "ok" if redis_client.ping() else "error"


@router.get("/api/health")
async def health_check() -> dict:
    settings = get_settings()
    database = _check_database()
    cache = _check_redis()

    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "dependencies": {
            "database": database,
            "redis": cache,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
