"""AI Analyst Engine (Phase 5 Day 5).

Mengubah angka & indikator sistem menjadi analisis berbahasa manusia: ringkasan,
faktor bullish, faktor risiko, dan confidence. UPGRADE dari AI Stock Report
(Phase 2) & Explainable AI (Phase 3) - kini dinarasikan LLM, tetapi:

  - ANGKA selalu dari tool (Composite Score, Forecast, Risk, S/R, Market Data,
    Sector Rotation) - LLM dilarang mengarang (grounding).
  - `confidence` = Composite Score (0-100) DARI SISTEM, bukan dari LLM.
  - Output terstruktur (JSON) agar konsisten & mudah disimpan/ditampilkan.

Aman-gagal: bila market_data tak ada -> {"error"}. Bila LLM nonaktif -> tetap
kembalikan angka + confidence (tanpa narasi), ditandai ai_generated=False.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.ai import guardrails, llm_client, prompt_builder, tools

# Tool yang dirangkai sebagai input analisis (per-saham + konteks sektor).
_TOOLS = (
    "get_market_data",
    "get_composite_score",
    "get_forecast",
    "get_risk",
    "get_support_resistance",
    "get_sector_rotation",
)

# Skema output terstruktur LLM (tanpa disclaimer - disclaimer di field terpisah).
ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "Ringkasan 2-3 kalimat kondisi saham."},
        "bullish_factors": {"type": "array", "items": {"type": "string"}},
        "risk_factors": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "bullish_factors", "risk_factors"],
}


def gather(ticker: str) -> dict[str, Any]:
    """Kumpulkan seluruh data sistem untuk satu saham via tool (angka live)."""
    return {name: tools.run_tool(name, {"ticker": ticker}) for name in _TOOLS}


def _confidence(data: dict[str, Any]) -> float | None:
    comp = data.get("get_composite_score", {})
    return comp.get("overall_score") if isinstance(comp, dict) and "error" not in comp else None


def analyze(ticker: str) -> dict[str, Any]:
    """Hasilkan analisis AI ter-grounding untuk `ticker`."""
    ticker = ticker.strip().upper()
    data = gather(ticker)

    market = data.get("get_market_data", {})
    if "error" in market:
        return {"ticker": ticker, "error": market["error"]}

    as_of = market.get("date")
    confidence = _confidence(data)
    base: dict[str, Any] = {
        "ticker": ticker,
        "date": as_of,
        "confidence": confidence,
        "disclaimer": guardrails.DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # LLM nonaktif: tetap kembalikan angka + confidence tanpa narasi.
    if not llm_client.is_available():
        return {
            **base,
            "summary": None,
            "bullish_factors": [],
            "risk_factors": [],
            "ai_generated": False,
            "note": "Narasi AI nonaktif (GEMINI_API_KEY belum diisi); angka tetap dari sistem.",
        }

    from app.rag import retriever

    rag_context = retriever.retrieve_context(
        f"analisis saham {ticker}: composite score, forecast, risiko, support resistance, rotasi sektor",
        top_k=4,
    )
    built = prompt_builder.build(
        (
            f"Buat analisis ringkas saham {ticker} untuk investor ritel berbahasa Indonesia. "
            "Hasilkan: (1) summary 2-3 kalimat; (2) bullish_factors: 2-4 poin faktor pendukung; "
            "(3) risk_factors: 1-3 poin risiko. Setiap poin singkat & merujuk ANGKA dari DATA "
            "SISTEM (mis. 'Composite Score 75', 'RSI 60', 'risiko MEDIUM'). JANGAN mengarang angka."
        ),
        rag_context=rag_context,
        tool_results=data,
    )

    try:
        parsed = llm_client.generate_json(
            built["prompt"], schema=ANALYSIS_SCHEMA, system=built["system"], max_output_tokens=900
        )
    except llm_client.LLMError as exc:
        # Branch error mengembalikan key konsisten (tak ada KeyError di caller).
        return {
            **base,
            "summary": None,
            "bullish_factors": [],
            "risk_factors": [],
            "ai_generated": False,
            "error": f"Narasi AI gagal: {exc}",
            "note": f"Narasi AI gagal: {exc}",
        }

    return {
        **base,
        "summary": (parsed.get("summary") or "").strip() or None,
        "bullish_factors": parsed.get("bullish_factors") or [],
        "risk_factors": parsed.get("risk_factors") or [],
        "ai_generated": True,
    }
