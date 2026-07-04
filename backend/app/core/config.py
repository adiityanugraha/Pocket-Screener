"""Konfigurasi aplikasi.

Semua nilai sensitif (DATABASE_URL, REDIS_URL) dibaca dari environment /
file .env - TIDAK PERNAH di-hardcode di kode, sehingga aman di-commit.
Lihat backend/.env.example untuk template.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Metadata aplikasi
    app_name: str = "Pocket Screener API"
    app_version: str = "0.1.0"
    environment: str = "development"  # development | production

    # Koneksi (diisi mulai Day 2 & Day 4). Optional agar Day 1 tetap jalan
    # tanpa kredensial.
    database_url: str | None = None
    redis_url: str | None = None

    # CORS: origin frontend yang boleh memanggil API.
    # Comma-separated string di .env, mis. "http://localhost:3000,https://app.vercel.app"
    cors_origins: str = "http://localhost:3000"

    # Path file model ONNX. Default (None) -> backend/app/ml/model.onnx
    # (resolve di app.ml.inference). Override lewat env ONNX_MODEL_PATH bila perlu.
    onnx_model_path: str | None = None

    # Scheduler (Day 13). Job harian otomatis dijalankan saat startup FastAPI.
    # Set SCHEDULER_ENABLED=false di .env untuk mematikan (mis. saat testing).
    scheduler_enabled: bool = True

    # --- Phase 5: lapisan AI (LLM + embedding) ---
    # API key Google Gemini (free tier, dari Google AI Studio). Disimpan HANYA di
    # environment server - tidak pernah di kode/klien. Bila kosong, lapisan AI
    # nonaktif (aman-gagal): wrapper LLM jadi tak-tersedia & caller fallback.
    gemini_api_key: str | None = None
    # Nama model dibuat generik agar wrapper provider-agnostic (mudah ganti
    # provider tanpa ubah kode pemanggil).
    # gemini-2.5-flash-lite: kuota harian free tier jauh lebih tinggi daripada
    # gemini-2.5-flash (yang hanya ~20 req/hari) - penting untuk generasi batch
    # (mis. 81 saham di job malam). Kualitas cukup untuk tugas narasi.
    llm_model: str = "gemini-2.5-flash-lite"
    embedding_model: str = "gemini-embedding-001"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Settings di-cache agar .env hanya dibaca sekali."""
    return Settings()
