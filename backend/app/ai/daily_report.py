"""AI Daily Report (Phase 5 Day 13).

Laporan harian otomatis yang mengagregasi insight sistem:
  - Top Opportunities  : ranking Composite Score (Phase 2)
  - Strongest/Weakest Sector : Sector Rotation (Day 2)
  - High Confidence Stocks   : Probability Forecast (Phase 3, confidence HIGH)
  - Risk Warning       : saham HIGH risk di antara Top Opportunities (Risk Meter)

LLM menarasikan overview; ANGKA dari sistem. Tersedia 3 format: dict (dashboard),
Markdown, dan PDF (fpdf2). Di-generate job malam (Day 14) lalu di-cache.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import guardrails, llm_client, prompt_builder, tools
from app.api import ranking as ranking_api
from app.db.models import Forecast

_TOP_N = 5


def build_report(db: Session) -> dict[str, Any]:
    """Rakit laporan harian (angka dari sistem + overview LLM)."""
    ranking = ranking_api.run_ranking(db, limit=_TOP_N, use_ml=True)
    top_opportunities = [
        {"ticker": it["ticker"], "name": it.get("name"), "overall_score": it["overall_score"]}
        for it in ranking.get("items", [])
    ]
    report_date = (top_opportunities and ranking["items"][0].get("date")) or None

    sector = tools.run_tool("get_sector_rotation")
    leaders = sector.get("leaders", []) if isinstance(sector, dict) else []
    laggards = sector.get("laggards", []) if isinstance(sector, dict) else []

    # High Confidence Stocks dari tabel forecast (tanggal terbaru, confidence HIGH).
    high_confidence: list[dict] = []
    fdate = db.scalar(select(func.max(Forecast.date)))
    if fdate is not None:
        rows = db.scalars(
            select(Forecast)
            .where(Forecast.date == fdate, Forecast.confidence == "HIGH")
            .order_by(Forecast.prob_5d.desc())
            .limit(_TOP_N)
        ).all()
        high_confidence = [
            {"ticker": r.ticker, "prob_5d": r.prob_5d, "prob_20d": r.prob_20d, "confidence": r.confidence}
            for r in rows
        ]

    # Risk warning: saham HIGH risk di antara Top Opportunities.
    risk_warnings: list[dict] = []
    for opp in top_opportunities:
        risk = tools.run_tool("get_risk", {"ticker": opp["ticker"]})
        if isinstance(risk, dict) and risk.get("risk") == "HIGH":
            risk_warnings.append({"ticker": opp["ticker"], "risk": "HIGH", "score": risk.get("score")})

    report = {
        "date": report_date,
        "top_opportunities": top_opportunities,
        "strongest_sector": leaders[0] if leaders else None,
        "weakest_sector": laggards[0] if laggards else None,
        "leading_sectors": leaders,
        "lagging_sectors": laggards,
        "high_confidence": high_confidence,
        "risk_warnings": risk_warnings,
        "disclaimer": guardrails.DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    report["overview"] = _overview(report)
    return report


def _overview(report: dict[str, Any]) -> str:
    template = "Ringkasan laporan harian berdasarkan data sistem."
    if not llm_client.is_available():
        return guardrails.ensure_disclaimer(template)
    built = prompt_builder.build(
        (
            "Tulis overview laporan harian pasar saham (3-4 kalimat): sebut beberapa Top "
            "Opportunities, sektor terkuat & terlemah, dan peringatan risiko bila ada. "
            "Gunakan HANYA angka dari DATA SISTEM."
        ),
        tool_results={
            "top_opportunities": report["top_opportunities"],
            "strongest_sector": report["strongest_sector"],
            "weakest_sector": report["weakest_sector"],
            "high_confidence": report["high_confidence"],
            "risk_warnings": report["risk_warnings"],
        },
    )
    try:
        text = llm_client.generate(built["prompt"], system=built["system"], max_output_tokens=600)
    except llm_client.LLMError:
        text = template
    return guardrails.ensure_disclaimer(text)


# --------------------------------------------------------------------------- #
# Format Markdown & PDF
# --------------------------------------------------------------------------- #
def to_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Laporan Harian Pocket Screener - {report.get('date') or '-'}", ""]
    lines += ["## Ringkasan", report.get("overview") or "-", ""]

    lines.append("## Top Opportunities")
    if report["top_opportunities"]:
        for o in report["top_opportunities"]:
            lines.append(f"- {o['ticker']} ({o.get('name') or '-'}): skor {o['overall_score']}")
    else:
        lines.append("- (tidak ada)")
    lines.append("")

    lines += [
        "## Sektor",
        f"- Terkuat: {report.get('strongest_sector') or '-'}",
        f"- Terlemah: {report.get('weakest_sector') or '-'}",
        "",
        "## High Confidence Stocks",
    ]
    if report["high_confidence"]:
        for h in report["high_confidence"]:
            lines.append(f"- {h['ticker']}: P(5h)={h.get('prob_5d')}, keyakinan {h['confidence']}")
    else:
        lines.append("- (tidak ada)")
    lines.append("")

    lines.append("## Risk Warning")
    if report["risk_warnings"]:
        for w in report["risk_warnings"]:
            lines.append(f"- {w['ticker']}: risiko {w['risk']} (skor {w.get('score')})")
    else:
        lines.append("- Tidak ada peringatan risiko tinggi pada Top Opportunities.")
    lines += ["", "---", report.get("disclaimer", "")]
    return "\n".join(lines)


def _latin1(text: str) -> str:
    """Sanitasi ke latin-1 (font inti fpdf2 tak dukung Unicode penuh)."""
    return text.encode("latin-1", "replace").decode("latin-1")


def to_pdf(report: dict[str, Any]) -> bytes:
    """Render laporan ke PDF (fpdf2, font inti)."""
    from fpdf import FPDF, XPos, YPos

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    def write(text: str, size: int, bold: bool = False) -> None:
        pdf.set_font("Helvetica", "B" if bold else "", size)
        pdf.multi_cell(0, size * 0.6 + 2, text or " ", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    for raw in to_markdown(report).split("\n"):
        line = _latin1(raw)
        if line.startswith("# "):
            write(line[2:], 15, bold=True)
        elif line.startswith("## "):
            write(line[3:], 12, bold=True)
        elif line.strip() == "---":
            pdf.ln(2)
        else:
            write(line, 10)
    return bytes(pdf.output())
