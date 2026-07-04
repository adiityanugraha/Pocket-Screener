"""Explainable AI 2.0 - pembentukan Composite Score (Phase 5 Day 6).

Menjelaskan BAGAIMANA Composite Score (Phase 2) terbentuk: breakdown per komponen
(Technical 30%, Momentum 25%, Volume 20%, Volatility 10%, ML 15%) beserta
KONTRIBUSI tiap komponen ke skor akhir, lalu dinarasikan LLM.

Konsistensi dengan engine Phase 2 (app.core.composite_score):
  - Bila ML tersedia  : overall = Σ skor_i × bobot_i (bobot jumlah 1.0).
  - Bila ML tak ada   : bobot ML (15%) didistribusi ulang - 4 bobot lain
    direnormalisasi atas 0.85 (effective_weight). contribution = skor ×
    effective_weight; Σ contribution == overall pada KEDUA cabang.

ANGKA (skor & kontribusi) dari sistem; LLM hanya menarasikan (grounding).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.ai import guardrails, llm_client, prompt_builder, tools

# Bobot nominal Composite Score (selaras core.composite_score).
WEIGHTS: dict[str, float] = {
    "technical": 0.30,
    "momentum": 0.25,
    "volume": 0.20,
    "volatility": 0.10,
    "ml": 0.15,
}
LABELS: dict[str, str] = {
    "technical": "Technical Strength",
    "momentum": "Momentum",
    "volume": "Volume Activity",
    "volatility": "Volatility",
    "ml": "ML Prediction",
}
_NON_ML = ("technical", "momentum", "volume", "volatility")

ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "2-3 kalimat: komponen apa yang paling mendorong skor."},
        "bullish_factors": {"type": "array", "items": {"type": "string"}},
        "risk_factors": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "bullish_factors", "risk_factors"],
}


def build_breakdown(scores: dict[str, Any]) -> dict[str, Any]:
    """Breakdown kontribusi per komponen, konsisten dengan formula Phase 2.

    `scores` = {technical, momentum, volume, volatility, ml(None|num)}.
    """
    ml_available = scores.get("ml") is not None
    if ml_available:
        effective = dict(WEIGHTS)
        components = ("technical", "momentum", "volume", "volatility", "ml")
    else:
        base = sum(WEIGHTS[k] for k in _NON_ML)  # 0.85
        effective = {k: WEIGHTS[k] / base for k in _NON_ML}
        components = _NON_ML

    rows: list[dict[str, Any]] = []
    overall = 0.0
    for key in components:
        score = float(scores[key])
        weight = effective[key]
        contribution = score * weight
        overall += contribution
        rows.append(
            {
                "component": key,
                "label": LABELS[key],
                "score": round(score, 2),
                "weight": round(WEIGHTS[key], 4),
                "effective_weight": round(weight, 4),
                "contribution": round(contribution, 2),
            }
        )
    return {"components": rows, "ml_available": ml_available, "recomputed_overall": round(overall, 2)}


def explain(ticker: str) -> dict[str, Any]:
    """Penjelasan pembentukan Composite Score untuk `ticker` (breakdown + narasi)."""
    ticker = ticker.strip().upper()
    comp = tools.run_tool("get_composite_score", {"ticker": ticker})
    if "error" in comp:
        return {"ticker": ticker, "error": comp["error"]}

    breakdown = build_breakdown(comp["breakdown"])
    base: dict[str, Any] = {
        "ticker": ticker,
        "date": comp.get("date"),
        "overall_score": comp.get("overall_score"),
        "ml_available": breakdown["ml_available"],
        "breakdown": breakdown["components"],
        "disclaimer": guardrails.DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if not llm_client.is_available():
        return {
            **base,
            "summary": None,
            "bullish_factors": [],
            "risk_factors": [],
            "ai_generated": False,
            "note": "Narasi AI nonaktif; breakdown tetap dari sistem.",
        }

    from app.rag import retriever

    rag_context = retriever.retrieve_context(
        "composite score: technical strength, momentum, volume activity, volatility, ml prediction", top_k=3
    )
    built = prompt_builder.build(
        (
            f"Jelaskan BAGAIMANA Composite Score {comp.get('overall_score')} saham {ticker} terbentuk. "
            "Soroti komponen dengan KONTRIBUSI terbesar & terkecil (lihat 'contribution'). "
            "Hasilkan: summary 2-3 kalimat; bullish_factors (komponen kuat); risk_factors (komponen lemah). "
            "Rujuk ANGKA dari DATA SISTEM, jangan mengarang."
        ),
        rag_context=rag_context,
        tool_results={"composite_score": comp, "breakdown_kontribusi": breakdown},
    )
    try:
        parsed = llm_client.generate_json(
            built["prompt"], schema=ANALYSIS_SCHEMA, system=built["system"], max_output_tokens=900
        )
    except llm_client.LLMError as exc:
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
