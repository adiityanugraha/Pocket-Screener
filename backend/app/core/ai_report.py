"""AI Stock Report - ubah indikator + ML jadi analisis yang mudah dibaca.

Sesuai blueprint Phase 2 (AI Stock Report), output:
  - Bullish / Bearish Summary  (ringkasan + sentimen)
  - Bullish factors            (faktor pendukung kenaikan)
  - Risk factors               (faktor risiko)
  - Confidence Score           (0-100, dipakai sebagai "AI Confidence")

Confidence diambil dari Composite Score Engine (Day 7) agar konsisten dengan
/api/ranking. Faktor-faktor disusun deterministik dari ambang indikator yang
masuk akal (contoh: Volume naik, MACD Golden Cross, RSI sehat, dekat resistance).

Modul ini MURNI (tanpa DB/ML/cache) agar mudah diuji. API (stock_report.py) yang
merakit input dari market_data + prediksi ML.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core import composite_score as cs

# Ambang sentimen dari confidence score (0-100).
SENTIMENT_BULLISH = 60.0
SENTIMENT_BEARISH = 45.0


@dataclass(frozen=True)
class ReportInput:
    """Snapshot satu saham (bar terakhir + konteks) untuk menyusun report.

    Superset dari CompositeInput: menambah field mentah yang dibutuhkan untuk
    menjelaskan alasan secara manusiawi (MACD cross, jarak ke resistance, dll).
    """

    rsi: float | None
    macd_histogram: float | None
    prev_macd_histogram: float | None  # bar sebelumnya - deteksi golden/death cross
    bb_position: float | None  # (close - lower) / (upper - lower), 0..1
    close: float | None
    bb_upper: float | None
    bb_lower: float | None
    return_1d: float | None
    return_5d: float | None
    volume_ratio: float | None
    atr_pct: float | None
    probability_up: float | None  # 0..1 dari model ONNX (None bila ML tak ada)


@dataclass(frozen=True)
class StockReport:
    ticker: str
    score: int  # confidence 0-100 (= Composite Overall, dibulatkan)
    sentiment: str  # "Bullish" | "Bearish" | "Neutral"
    summary: str
    bullish_factors: list[str]
    risk_factors: list[str]


def _to_composite_input(inp: ReportInput) -> cs.CompositeInput:
    """Petakan ReportInput -> CompositeInput agar skor selaras dgn /api/ranking."""
    return cs.CompositeInput(
        rsi=inp.rsi,
        macd_histogram=inp.macd_histogram,
        bb_position=inp.bb_position,
        return_1d=inp.return_1d,
        return_5d=inp.return_5d,
        volume_ratio=inp.volume_ratio,
        atr_pct=inp.atr_pct,
        probability_up=inp.probability_up,
    )


def _pct(value: float) -> str:
    """Format rasio (mis. 0.354) jadi persen ringkas (mis. '35%')."""
    return f"{round(value * 100)}%"


# --------------------------------------------------------------------------- #
# Penyusun faktor
# --------------------------------------------------------------------------- #
def _collect_bullish_factors(inp: ReportInput) -> list[str]:
    factors: list[str] = []

    # Volume di atas rata-rata.
    if inp.volume_ratio is not None and inp.volume_ratio >= 1.2:
        factors.append(f"Volume naik {_pct(inp.volume_ratio - 1)} di atas rata-rata")

    # MACD: golden cross > histogram positif.
    if inp.macd_histogram is not None:
        if inp.macd_histogram > 0:
            if inp.prev_macd_histogram is not None and inp.prev_macd_histogram <= 0:
                factors.append("MACD Golden Cross (momentum berbalik naik)")
            else:
                factors.append("MACD bullish (histogram positif)")

    # RSI sehat (zona bullish, belum overbought).
    if inp.rsi is not None and 50 <= inp.rsi <= 70:
        factors.append(f"RSI {round(inp.rsi)} masih sehat (zona bullish)")

    # Tren naik dalam 5 hari.
    if inp.return_5d is not None and inp.return_5d >= 0.03:
        factors.append(f"Tren naik {_pct(inp.return_5d)} dalam 5 hari")

    # Penguatan harian.
    if inp.return_1d is not None and inp.return_1d >= 0.02:
        factors.append(f"Harga menguat {_pct(inp.return_1d)} hari ini")

    # Model ML memprediksi naik.
    if inp.probability_up is not None and inp.probability_up >= 0.55:
        factors.append(f"Model ML memprediksi naik ({_pct(inp.probability_up)})")

    return factors


def _collect_risk_factors(inp: ReportInput) -> list[str]:
    factors: list[str] = []

    # RSI ekstrem.
    if inp.rsi is not None:
        if inp.rsi > 70:
            factors.append(f"RSI {round(inp.rsi)} overbought (rawan koreksi)")
        elif inp.rsi < 30:
            factors.append(f"RSI {round(inp.rsi)} oversold (tekanan jual kuat)")

    # MACD: death cross > histogram negatif.
    if inp.macd_histogram is not None and inp.macd_histogram < 0:
        if inp.prev_macd_histogram is not None and inp.prev_macd_histogram >= 0:
            factors.append("MACD Death Cross (momentum berbalik turun)")
        else:
            factors.append("MACD bearish (histogram negatif)")

    # Dekat resistance (posisi Bollinger atas).
    if inp.bb_position is not None and inp.bb_position >= 0.85:
        factors.append("Harga dekat resistance (pita Bollinger atas)")

    # Volatilitas tinggi.
    if inp.atr_pct is not None and inp.atr_pct >= 0.05:
        factors.append(f"Volatilitas tinggi (ATR {_pct(inp.atr_pct)})")

    # Tren turun dalam 5 hari.
    if inp.return_5d is not None and inp.return_5d <= -0.03:
        factors.append(f"Tren turun {_pct(abs(inp.return_5d))} dalam 5 hari")

    # Volume sepi.
    if inp.volume_ratio is not None and inp.volume_ratio < 0.6:
        factors.append("Volume sepi (di bawah rata-rata)")

    # Model ML memprediksi turun.
    if inp.probability_up is not None and inp.probability_up <= 0.45:
        factors.append(f"Model ML memprediksi turun ({_pct(1 - inp.probability_up)})")

    return factors


def _sentiment(score: float) -> str:
    if score >= SENTIMENT_BULLISH:
        return "Bullish"
    if score <= SENTIMENT_BEARISH:
        return "Bearish"
    return "Neutral"


def _build_summary(
    ticker: str,
    sentiment: str,
    score: int,
    bullish: list[str],
    risks: list[str],
) -> str:
    """Rangkai kalimat ringkas dari sentimen + faktor dominan."""
    if sentiment == "Bullish":
        opening = f"{ticker} terlihat Bullish dengan AI Confidence {score}%."
    elif sentiment == "Bearish":
        opening = f"{ticker} cenderung Bearish dengan AI Confidence {score}%."
    else:
        opening = f"{ticker} bergerak netral dengan AI Confidence {score}%."

    parts = [opening]
    if bullish:
        lead = "; ".join(bullish[:2])
        parts.append(f"Didukung oleh {lead.lower()}.")
    if risks:
        lead = "; ".join(risks[:2])
        parts.append(f"Perlu diwaspadai: {lead.lower()}.")
    if not bullish and not risks:
        parts.append("Belum ada sinyal teknikal yang menonjol.")
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Generator utama
# --------------------------------------------------------------------------- #
def generate_report(ticker: str, inp: ReportInput) -> StockReport:
    """Hasilkan StockReport: confidence (Composite), sentimen, ringkasan, faktor."""
    composite = cs.compute_composite(_to_composite_input(inp))
    score = round(composite.overall)
    sentiment = _sentiment(composite.overall)

    bullish = _collect_bullish_factors(inp)
    risks = _collect_risk_factors(inp)
    summary = _build_summary(ticker, sentiment, score, bullish, risks)

    return StockReport(
        ticker=ticker,
        score=score,
        sentiment=sentiment,
        summary=summary,
        bullish_factors=bullish,
        risk_factors=risks,
    )
