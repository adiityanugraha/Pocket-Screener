"""Retriever RAG (Phase 5 Day 4).

Mengambil konteks KONSEP relevan dari vector store lokal untuk sebuah query, lalu
memformatnya menjadi blok teks siap-sisip ke prompt LLM. Aman-gagal: bila lapisan
AI nonaktif atau knowledge base belum di-seed, kembalikan [] / "" sehingga fitur
LLM tetap jalan (tanpa konteks konsep) - angka tetap dari tool call (grounding).
"""

from __future__ import annotations

from typing import Any

from app.rag import embeddings, vector_store

DEFAULT_TOP_K = 4


def retrieve(query: str, top_k: int = DEFAULT_TOP_K, min_score: float | None = None) -> list[dict[str, Any]]:
    """Konsep paling relevan untuk `query` (cosine di store lokal).

    Mengembalikan [] bila AI nonaktif, store kosong, atau query kosong - caller
    harus tahan terhadap konteks kosong.
    """
    if not query or not query.strip():
        return []
    if not embeddings.is_available():
        return []
    store = vector_store.get_store()
    if len(store) == 0:
        return []
    try:
        query_vector = embeddings.embed_query(query)
    except Exception:  # noqa: BLE001 - RAG opsional; jangan jatuhkan caller
        return []
    hits = store.search(query_vector, top_k=top_k)
    if min_score is not None:
        hits = [h for h in hits if h.get("score", 0.0) >= min_score]
    return hits


def format_context(hits: list[dict[str, Any]]) -> str:
    """Format hasil retrieval jadi blok teks untuk prompt. "" bila kosong."""
    if not hits:
        return ""
    lines = [f"- {h.get('title', h.get('id', '?'))}: {h.get('content', '').strip()}" for h in hits]
    return "Definisi/konsep relevan (referensi penjelasan, BUKAN angka):\n" + "\n".join(lines)


def retrieve_context(query: str, top_k: int = DEFAULT_TOP_K) -> str:
    """Shortcut: retrieve + format_context dalam satu panggilan."""
    return format_context(retrieve(query, top_k=top_k))
