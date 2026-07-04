"""Natural Language Screener (Phase 5 Day 9).

Mengubah prompt bahasa alami -> PARAMETER FILTER terstruktur (via LLM structured
output), lalu EKSEKUSI memakai engine screener Phase 3 yang SUDAH ADA
(strategy_screener). LLM HANYA membuat filter; pemilihan saham tetap
deterministik oleh engine (anti-halusinasi: bukan LLM yang "memilih" saham).

Pipeline:
  query -> parse_query() [LLM JSON: {strategy, max_risk, limit}]
        -> screen_one_strategy() [engine deterministik]
        -> filter Risk Meter (opsional, ambang max_risk)
        -> ringkasan AI (opsional, degradasi anggun)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.ai import guardrails, llm_client, prompt_builder, tools
from app.core import strategy_screener
from app.core.strategies import registry

_RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
DEFAULT_LIMIT = 5
MAX_LIMIT = 20


def strategy_catalog() -> list[dict[str, str]]:
    """Daftar strategi dari registry (untuk memandu LLM memetakan query)."""
    return [
        {"key": s.key, "name": s.name, "label": s.output_label}
        for s in registry.all_strategies()
    ]


def _filter_schema(keys: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "strategy": {"type": "string", "enum": keys},
            "max_risk": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "NONE"]},
            "limit": {"type": "integer"},
        },
        "required": ["strategy", "max_risk", "limit"],
    }


def _clamp_limit(value: Any) -> int:
    try:
        return max(1, min(int(value), MAX_LIMIT))
    except (TypeError, ValueError):
        return DEFAULT_LIMIT


def parse_query(query: str) -> dict[str, Any]:
    """Terjemahkan query NL -> {strategy, max_risk(None|LOW/MED/HIGH), limit}.

    Melempar LLMError bila AI nonaktif/gagal; melempar ValueError bila strategi
    hasil LLM tidak dikenal (caller -> 422).
    """
    catalog = strategy_catalog()
    keys = [s["key"] for s in catalog]
    catalog_text = "\n".join(f"- {s['key']}: {s['name']} ({s['label']})" for s in catalog)
    system = (
        "Anda penerjemah query screener saham. Petakan permintaan pengguna ke SATU "
        "strategi paling cocok dari daftar (gunakan KEY-nya). Tetapkan max_risk bila "
        "pengguna menyebut preferensi risiko (rendah=LOW, sedang=MEDIUM, tinggi=HIGH), "
        "jika tidak gunakan NONE. limit default 5. JANGAN memilih saham - hanya filter."
    )
    prompt = f"Strategi tersedia:\n{catalog_text}\n\nQuery pengguna: {query}"
    parsed = llm_client.generate_json(
        prompt, schema=_filter_schema(keys), system=system, max_output_tokens=200
    )
    strategy = (parsed.get("strategy") or "").strip().lower()
    if strategy not in keys:
        raise ValueError(f"Strategi hasil interpretasi tidak dikenal: {strategy!r}")
    max_risk = parsed.get("max_risk", "NONE")
    return {
        "strategy": strategy,
        "max_risk": max_risk if max_risk in _RISK_ORDER else None,
        "limit": _clamp_limit(parsed.get("limit", DEFAULT_LIMIT)),
    }


def _risk_allowed(level: str | None, max_risk: str) -> bool:
    if level not in _RISK_ORDER:
        return False
    return _RISK_ORDER[level] <= _RISK_ORDER[max_risk]


def _summarize(query: str, filt: dict, result: dict, candidates: list[dict]) -> str:
    """Ringkasan AI atas hasil (degradasi anggun -> template bila LLM gagal)."""
    tickers = [c["ticker"] for c in candidates]
    template = (
        f"Strategi '{result['name']}' menghasilkan {len(candidates)} kandidat"
        + (f" dengan risiko maksimal {filt['max_risk']}" if filt["max_risk"] else "")
        + (f": {', '.join(tickers)}." if tickers else " (tidak ada yang memenuhi).")
    )
    if not llm_client.is_available():
        return guardrails.ensure_disclaimer(template)
    built = prompt_builder.build(
        f"Ringkas hasil screening (2-3 kalimat) untuk permintaan: '{query}'. "
        "Sebut strategi & jumlah kandidat. Jangan mengarang angka.",
        tool_results={"filter": filt, "strategy": result["name"], "candidates": candidates},
    )
    try:
        text = llm_client.generate(built["prompt"], system=built["system"], max_output_tokens=400)
    except llm_client.LLMError:
        text = template
    return guardrails.ensure_disclaimer(text)


def run(query: str, db: Session) -> dict[str, Any]:
    """Jalankan NL screener: parse -> engine -> filter risiko -> ringkasan."""
    filt = parse_query(query)  # dapat melempar LLMError/ValueError -> caller tangani
    result = strategy_screener.screen_one_strategy(db, filt["strategy"], limit=filt["limit"])
    candidates = result["candidates"]

    if filt["max_risk"]:
        filtered: list[dict] = []
        for cand in candidates:
            risk = tools.run_tool("get_risk", {"ticker": cand["ticker"]})
            level = risk.get("risk") if isinstance(risk, dict) else None
            if _risk_allowed(level, filt["max_risk"]):
                filtered.append({**cand, "risk": level, "risk_score": risk.get("score")})
        candidates = filtered

    return {
        "query": query,
        "filter": filt,
        "strategy": result["strategy"],
        "strategy_name": result["name"],
        "passed_total": result["passed"],
        "returned": len(candidates),
        "candidates": candidates,
        "summary": _summarize(query, filt, result, candidates),
        "disclaimer": guardrails.DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
