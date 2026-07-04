"""Market Narrator (Phase 5 Day 12).

Merangkai Market Breadth (Phase 2) + Sector Rotation (Day 2) + Strategy Benchmark
(Phase 4) menjadi narasi kondisi pasar berbahasa alami. ANGKA dari sistem; LLM
hanya menarasikan. Di-generate job malam (Day 14) lalu di-cache.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.ai import guardrails, llm_client, prompt_builder, tools
from app.api import benchmark as benchmark_api
from app.quant import performance_metrics as pm


def gather(db: Session) -> dict[str, Any]:
    """Kumpulkan data pasar (angka live dari sistem)."""
    return {
        "market_breadth": tools.run_tool("get_market_breadth"),
        "sector_rotation": tools.run_tool("get_sector_rotation"),
        "benchmark": benchmark_api.get_benchmark(hold=pm.DEFAULT_HOLD, refresh=False, db=db),
    }


def _extract(data: dict[str, Any]) -> dict[str, Any]:
    """Ringkas field kunci dari data mentah (murni - untuk respons & uji)."""
    breadth = data.get("market_breadth") or {}
    sector = data.get("sector_rotation") or {}
    bench = data.get("benchmark") or {}
    strategies = bench.get("strategies", []) if isinstance(bench, dict) else []
    best = strategies[0] if strategies else None
    return {
        "date": breadth.get("date") or sector.get("as_of"),
        "bullish_ratio": breadth.get("bullish_ratio"),
        "advancers": breadth.get("advancers"),
        "decliners": breadth.get("decliners"),
        "leading_sectors": sector.get("leaders", []),
        "lagging_sectors": sector.get("laggards", []),
        "best_strategy": best.get("strategy") if isinstance(best, dict) else None,
    }


def _narrate(data: dict[str, Any]) -> str:
    template = "Ringkasan kondisi pasar berdasarkan data sistem."
    if not llm_client.is_available():
        return guardrails.ensure_disclaimer(template)
    built = prompt_builder.build(
        (
            "Buat ringkasan kondisi pasar saham IDX hari ini dalam 3-4 kalimat: breadth "
            "(bullish ratio, advancers/decliners), sektor yang LEADING & LAGGING, dan "
            "strategi terbaik menurut benchmark. Gunakan HANYA angka dari DATA SISTEM."
        ),
        tool_results=data,
    )
    try:
        text = llm_client.generate(built["prompt"], system=built["system"], max_output_tokens=500)
    except llm_client.LLMError:
        text = template
    return guardrails.ensure_disclaimer(text)


def summarize(db: Session) -> dict[str, Any]:
    """Bangun narasi pasar + field kunci."""
    data = gather(db)
    extracted = _extract(data)
    return {
        **extracted,
        "summary": _narrate(data),
        "disclaimer": guardrails.DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
