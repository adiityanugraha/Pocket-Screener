"""Cache layer - wrapper Redis (Upstash, serverless).

Dipakai untuk mempercepat data yang sering diakses (harga, indikator, ranking,
support/resistance). Prinsip desain:

  - **Opsional & aman gagal**: jika REDIS_URL kosong atau Redis tak terjangkau,
    semua helper jadi no-op (get -> None, set -> diabaikan). Aplikasi tetap jalan
    dengan fallback ke PostgreSQL / komputasi langsung. Cache TIDAK boleh membuat
    request gagal.
  - **Namespacing**: semua key diberi prefix `pocket-screener:` agar tidak bentrok.
  - **Serialisasi JSON**: nilai disimpan sebagai string JSON (decode_responses=True).

Koneksi Upstash memakai skema `rediss://` (TLS) - didukung langsung redis-py.
"""

from __future__ import annotations

import json
from typing import Any

import redis

from app.core.config import get_settings

KEY_PREFIX = "pocket-screener:"

# Strategi TTL (detik). Data market dianggap "segar" selama jam bursa berjalan;
# ranking/laporan lebih jarang berubah sehingga TTL lebih panjang.
TTL_PRICE = 15 * 60        # harga / OHLCV terbaru - selaras cache frontend (15 menit)
TTL_INDICATORS = 15 * 60   # indikator teknikal
TTL_RANKING = 60 * 60      # composite score / ranking (Day 7)
TTL_REPORT = 60 * 60       # AI stock report (Day 8)
TTL_SUPPORT_RESISTANCE = 30 * 60  # S/R levels (Day 10)
TTL_QUANT = 12 * 60 * 60   # metrik kuantitatif Phase 4 (dihitung job malam, stabil seharian)

_client: redis.Redis | None = None
_initialized = False


def get_redis() -> redis.Redis | None:
    """Kembalikan singleton Redis client, atau None bila tidak dikonfigurasi.

    Koneksi dibuat lazy & dicache. Bila REDIS_URL kosong atau ping awal gagal,
    fungsi mengembalikan None dan caller harus fallback ke sumber data asli.
    """
    global _client, _initialized
    if _initialized:
        return _client

    _initialized = True
    redis_url = get_settings().redis_url
    if not redis_url:
        _client = None
        return None

    try:
        client = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            health_check_interval=30,
        )
        client.ping()  # verifikasi koneksi sekali di awal
        _client = client
    except redis.RedisError:
        _client = None

    return _client


def _namespaced(key: str) -> str:
    return key if key.startswith(KEY_PREFIX) else f"{KEY_PREFIX}{key}"


def cache_get_json(key: str) -> Any | None:
    """Ambil & deserialisasi nilai JSON. None bila miss / cache mati / korup."""
    client = get_redis()
    if client is None:
        return None
    try:
        raw = client.get(_namespaced(key))
    except redis.RedisError:
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def cache_set_json(key: str, value: Any, ttl: int | None = None) -> bool:
    """Serialisasi & simpan nilai sebagai JSON dengan TTL opsional (detik).

    Mengembalikan True bila tersimpan, False bila cache tak aktif / gagal.
    """
    client = get_redis()
    if client is None:
        return False
    try:
        payload = json.dumps(value, default=str)
        client.set(_namespaced(key), payload, ex=ttl)
        return True
    except (redis.RedisError, TypeError, ValueError):
        return False


def cache_delete(*keys: str) -> int:
    """Hapus satu/lebih key (invalidasi). Mengembalikan jumlah key terhapus."""
    client = get_redis()
    if client is None or not keys:
        return 0
    try:
        return client.delete(*(_namespaced(key) for key in keys))
    except redis.RedisError:
        return 0


def ping() -> bool:
    """True bila Redis aktif & merespons (untuk health check)."""
    client = get_redis()
    if client is None:
        return False
    try:
        return bool(client.ping())
    except redis.RedisError:
        return False
