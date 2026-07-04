"""Wrapper pemanggilan LLM - provider-agnostic (Phase 5 Day 1).

Membungkus provider LLM (saat ini Google Gemini, free tier) di balik antarmuka
NETRAL: caller hanya bekerja dengan `str`, `dict`, dan iterator teks biasa -
tidak ada tipe khusus Gemini yang bocor keluar. Mengganti provider nanti cukup
mengubah file INI saja.

Prinsip desain (selaras cache/redis_client Phase 2):
  - **Opsional & aman-gagal**: bila GEMINI_API_KEY kosong, `is_available()`
    mengembalikan False dan caller harus fallback (mis. tampilkan data mentah
    tanpa narasi). Pembuatan client bersifat lazy & dicache.
  - **Error provider dibungkus** jadi `LLMError` agar caller tak bergantung pada
    detail SDK provider.

Tiga mode yang didukung (sesuai Step_by_Step_Phase5 Day 1):
  - generate()      : prompt -> teks (chat biasa)
  - generate_json() : structured output (JSON) - fondasi NL Screener Day 9
  - stream()        : streaming teks token-demi-token - untuk Chat Day 7-8

Catatan biaya/kuota: free tier punya batas RPM/RPD. Generasi batch (job malam)
WAJIB di-cache; throttle antar-pemanggilan dilakukan di pemanggil, bukan di sini.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from typing import Any

from app.core.config import get_settings

log = logging.getLogger("app.ai")

# Retry untuk error TRANSIEN (rate limit / overload) - krusial di free tier saat
# generasi batch (mis. 81 saham di job malam). Backoff: 2s, 4s.
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0
_RETRYABLE_MARKERS = ("429", "resource_exhausted", "rate", "503", "unavailable", "overload", "500")


class LLMError(RuntimeError):
    """Kegagalan pemanggilan LLM (tak tersedia, error provider, atau parsing)."""


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in _RETRYABLE_MARKERS)


def _generate_content(client: Any, *, model: str, contents: str, config: Any) -> Any:
    """Panggil generate_content dengan retry+backoff pada error transien."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < _MAX_RETRIES - 1 and _is_retryable(exc):
                time.sleep(_BACKOFF_BASE * (2 ** attempt))
                continue
            raise
    raise last_exc  # pragma: no cover


# Singleton client + flag inisialisasi (pola sama dengan cache/redis_client).
_client: Any | None = None
_initialized = False


def _build_client() -> Any | None:
    """Buat client Gemini bila API key ada. None bila tidak dikonfigurasi/gagal."""
    api_key = get_settings().gemini_api_key
    if not api_key:
        return None
    try:
        # Import lokal: SDK provider hanya dibutuhkan bila lapisan AI aktif.
        from google import genai

        return genai.Client(api_key=api_key)
    except Exception as exc:  # noqa: BLE001 - jangan jatuhkan app karena AI mati
        log.warning("Gagal inisialisasi client LLM: %s", exc)
        return None


def get_client() -> Any | None:
    """Kembalikan singleton client LLM, atau None bila lapisan AI nonaktif."""
    global _client, _initialized
    if _initialized:
        return _client
    _initialized = True
    _client = _build_client()
    return _client


def reset_client() -> None:
    """Reset singleton (untuk testing / setelah konfigurasi berubah)."""
    global _client, _initialized
    _client = None
    _initialized = False


def is_available() -> bool:
    """True bila LLM siap dipakai (API key terkonfigurasi & client terbentuk)."""
    return get_client() is not None


def _model_name(override: str | None) -> str:
    return override or get_settings().llm_model


def _config(system: str | None, temperature: float | None, max_output_tokens: int | None, **extra: Any):
    """Rakit GenerateContentConfig Gemini; hanya field non-None yang diisi.

    Thinking DINONAKTIFKAN (thinking_budget=0) secara default: tugas Phase 5
    sekadar menarasikan angka dari sistem (bukan reasoning kompleks), sehingga
    thinking hanya menambah latensi & boros kuota free tier - dan dengan
    max_output_tokens kecil, anggaran bisa habis untuk thinking sampai teks
    jawaban kosong. Caller bisa override via extra["thinking_config"].
    """
    from google.genai import types

    params: dict[str, Any] = {"thinking_config": types.ThinkingConfig(thinking_budget=0)}
    if system is not None:
        params["system_instruction"] = system
    if temperature is not None:
        params["temperature"] = temperature
    if max_output_tokens is not None:
        params["max_output_tokens"] = max_output_tokens
    params.update(extra)  # extra menang (mis. response_mime_type, atau override thinking)
    return types.GenerateContentConfig(**params)


def generate(
    prompt: str,
    *,
    system: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    model: str | None = None,
) -> str:
    """Panggil LLM sekali dan kembalikan teks jawaban.

    Melempar LLMError bila lapisan AI nonaktif atau provider gagal.
    """
    client = get_client()
    if client is None:
        raise LLMError("Lapisan AI nonaktif (GEMINI_API_KEY belum diisi).")
    try:
        resp = _generate_content(
            client,
            model=_model_name(model),
            contents=prompt,
            config=_config(system, temperature, max_output_tokens),
        )
        return resp.text or ""
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"Pemanggilan LLM gagal: {exc}") from exc


def generate_json(
    prompt: str,
    *,
    schema: Any | None = None,
    system: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    model: str | None = None,
) -> Any:
    """Panggil LLM dengan output terstruktur (JSON) dan kembalikan objek hasil parse.

    `schema` opsional: JSON Schema (dict) atau tipe/Pydantic yang didukung provider
    untuk membatasi bentuk output. Fondasi NL Screener (Day 9) & grounding.
    Melempar LLMError bila nonaktif, provider gagal, atau JSON tidak valid.
    """
    client = get_client()
    if client is None:
        raise LLMError("Lapisan AI nonaktif (GEMINI_API_KEY belum diisi).")
    extra: dict[str, Any] = {"response_mime_type": "application/json"}
    if schema is not None:
        extra["response_schema"] = schema
    try:
        resp = _generate_content(
            client,
            model=_model_name(model),
            contents=prompt,
            config=_config(system, temperature, max_output_tokens, **extra),
        )
        raw = resp.text or ""
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"Pemanggilan LLM (JSON) gagal: {exc}") from exc
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise LLMError(f"Output LLM bukan JSON valid: {exc}") from exc


def stream(
    prompt: str,
    *,
    system: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    model: str | None = None,
) -> Iterator[str]:
    """Streaming jawaban LLM sebagai potongan teks (untuk Chat Day 7-8).

    Yield hanya potongan teks non-kosong. Melempar LLMError bila nonaktif/gagal.
    """
    client = get_client()
    if client is None:
        raise LLMError("Lapisan AI nonaktif (GEMINI_API_KEY belum diisi).")
    model_name = _model_name(model)
    config = _config(system, temperature, max_output_tokens)
    for attempt in range(_MAX_RETRIES):
        produced_any = False
        try:
            stream_iter = client.models.generate_content_stream(
                model=model_name, contents=prompt, config=config
            )
            for chunk in stream_iter:
                text = getattr(chunk, "text", None)
                if text:
                    produced_any = True
                    yield text
            return
        except Exception as exc:  # noqa: BLE001
            # Retry HANYA bila belum ada teks ter-yield (hindari duplikasi).
            if not produced_any and attempt < _MAX_RETRIES - 1 and _is_retryable(exc):
                time.sleep(_BACKOFF_BASE * (2 ** attempt))
                continue
            raise LLMError(f"Streaming LLM gagal: {exc}") from exc
