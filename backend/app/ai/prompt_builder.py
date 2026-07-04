"""Penyusun prompt (Phase 5 Day 4).

Merakit prompt LLM dari tiga lapis:
  - instruksi sistem  = persona + SYSTEM_RULES (guardrails: grounding, cakupan,
    anti-injeksi, disclaimer).
  - konteks RAG       = definisi/konsep relevan (dari rag.retriever) - penjelasan,
    BUKAN angka.
  - hasil tool        = ANGKA LIVE dari endpoint Phase 1-4 (dari ai.tools) - sumber
    kebenaran untuk semua angka.

LLM merangkai ketiganya menjadi narasi. Pemisahan ini adalah inti anti-halusinasi:
konsep dari RAG, angka dari tool.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai import guardrails

PERSONA = (
    "Anda adalah AI Financial Analyst untuk Pocket Screener, aplikasi screening & "
    "analisis saham IDX. Tugas Anda menerjemahkan data terstruktur sistem menjadi "
    "penjelasan yang mudah dipahami investor ritel."
)


def system_instruction() -> str:
    """Instruksi sistem lengkap (persona + aturan guardrails)."""
    return f"{PERSONA}\n\n{guardrails.SYSTEM_RULES}"


def _format_tool_results(tool_results: dict[str, Any] | None) -> str:
    if not tool_results:
        return ""
    pretty = json.dumps(tool_results, ensure_ascii=False, indent=2, default=str)
    return (
        "DATA SISTEM (angka resmi - gunakan HANYA angka ini, jangan mengarang):\n"
        f"{pretty}"
    )


def build_prompt(
    user_query: str,
    *,
    rag_context: str = "",
    tool_results: dict[str, Any] | None = None,
) -> str:
    """Susun isi prompt pengguna (di luar system_instruction)."""
    blocks: list[str] = []
    if rag_context:
        blocks.append(rag_context)
    tools_block = _format_tool_results(tool_results)
    if tools_block:
        blocks.append(tools_block)
    blocks.append(f"PERTANYAAN/TUGAS:\n{user_query.strip()}")
    return "\n\n".join(blocks)


def build(
    user_query: str,
    *,
    rag_context: str = "",
    tool_results: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Kembalikan {'system': ..., 'prompt': ...} siap dikirim ke llm_client."""
    return {
        "system": system_instruction(),
        "prompt": build_prompt(user_query, rag_context=rag_context, tool_results=tool_results),
    }
