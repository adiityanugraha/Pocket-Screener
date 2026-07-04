"""Embedding teks -> vektor via Gemini (Phase 5 Day 3).

Memakai client Gemini yang sama dengan llm_client (model embedding default
gemini-embedding-001). Output di-set 768 dimensi (lebih ringkas & cepat untuk
KB kecil). Aman-gagal: bila lapisan AI nonaktif (GEMINI_API_KEY kosong),
melempar LLMError - caller harus menanganinya.

Task type Gemini meningkatkan kualitas retrieval: dokumen di-embed sebagai
RETRIEVAL_DOCUMENT, query sebagai RETRIEVAL_QUERY. Catatan: untuk dimensi < 3072,
embedding tidak ternormalisasi otomatis - vector_store menormalkan saat cosine.
"""

from __future__ import annotations

from app.ai import llm_client
from app.core.config import get_settings

# Dimensi output yang diminta dari gemini-embedding-001 (128..3072; 768 ringkas).
EMBED_DIM = 768

# Batas aman jumlah teks per panggilan batch (KB kita jauh di bawah ini).
_BATCH = 100


def is_available() -> bool:
    """True bila embedding siap (sama dengan ketersediaan LLM)."""
    return llm_client.is_available()


def _embed(texts: list[str], task_type: str) -> list[list[float]]:
    client = llm_client.get_client()
    if client is None:
        raise llm_client.LLMError("Lapisan AI nonaktif (GEMINI_API_KEY belum diisi).")

    from google.genai import types

    model = get_settings().embedding_model
    config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBED_DIM)
    out: list[list[float]] = []
    try:
        for start in range(0, len(texts), _BATCH):
            chunk = texts[start : start + _BATCH]
            result = client.models.embed_content(model=model, contents=chunk, config=config)
            out.extend(list(e.values) for e in result.embeddings)
    except Exception as exc:  # noqa: BLE001
        raise llm_client.LLMError(f"Embedding gagal: {exc}") from exc
    return out


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed daftar dokumen (task_type RETRIEVAL_DOCUMENT)."""
    if not texts:
        return []
    return _embed(texts, "RETRIEVAL_DOCUMENT")


def embed_query(text: str) -> list[float]:
    """Embed satu query (task_type RETRIEVAL_QUERY)."""
    return _embed([text], "RETRIEVAL_QUERY")[0]
