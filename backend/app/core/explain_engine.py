"""Explainable AI engine (Phase 3 Day 10).

Mengubah angka mentah menjadi penjelasan manusiawi (bullish factors + risk
factors + confidence). Dua lapis, sesuai blueprint:

  1. RULE-BASED  : matched_criteria dari strategi yang LOLOS - sudah per-saham &
                   akurat (mis. "MA20 > MA50 > MA100 > MA200", "Revenue +18% YoY").
                   Disuplai pemanggil dari hasil Strategy Registry.
  2. ML-LAYER    : interpretasi per-saham atas 13 fitur yang DILIHAT model
                   (RSI, MACD, Bollinger, ATR, volume, VWAP) menjadi kalimat.
                   Confidence = probabilitas model ONNX (P(up)) - bukan SHAP
                   (keputusan: lapisan ringan, model lemah 0.54 acc).

Modul MURNI (tanpa DB/ONNX) - pemanggil menyuplai snapshot indikator +
probabilitas + matched_criteria. Ambang interpretasi dikumpulkan sebagai
konstanta agar mudah disetel.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Ambang interpretasi sinyal teknikal (terdokumentasi & mudah disetel).
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0
RSI_HEALTHY_LOW = 50.0
RSI_HEALTHY_HIGH = 70.0
VOLUME_SPIKE_MIN = 1.2          # >= 1.2x rata-rata 20 hari -> bullish
BB_NEAR_UPPER = 0.9            # posisi dalam band >= 0.9 -> dekat resistance
BB_NEAR_LOWER = 0.1            # <= 0.1 -> dekat support
ATR_HIGH_PCT = 0.04           # ATR >= 4% harga -> volatilitas tinggi


@dataclass(frozen=True)
class ExplainSnapshot:
    """Snapshot indikator bar terakhir untuk interpretasi ML-layer."""

    close: float
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    bb_position: float | None = None      # (close - lower) / (upper - lower)
    atr_pct: float | None = None          # atr / close
    vwap_ratio: float | None = None       # close / vwap - 1
    volume_spike_ratio: float | None = None  # volume / rata-rata 20 hari


@dataclass(frozen=True)
class Explanation:
    confidence: int
    bullish_factors: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)


def technical_bullish(s: ExplainSnapshot) -> list[str]:
    """Sinyal teknikal positif dari snapshot (per-saham, dengan angka aktual)."""
    factors: list[str] = []

    if (
        s.macd is not None
        and s.macd_signal is not None
        and s.macd > s.macd_signal
        and (s.macd_histogram is None or s.macd_histogram > 0)
    ):
        factors.append("MACD di atas garis sinyal (momentum naik)")

    if s.volume_spike_ratio is not None and s.volume_spike_ratio >= VOLUME_SPIKE_MIN:
        pct = (s.volume_spike_ratio - 1) * 100
        factors.append(f"Volume {pct:.0f}% di atas rata-rata 20 hari")

    if s.rsi is not None and RSI_HEALTHY_LOW <= s.rsi <= RSI_HEALTHY_HIGH:
        factors.append(f"RSI sehat ({s.rsi:.0f}) - momentum kuat tanpa overbought")

    if s.vwap_ratio is not None and s.vwap_ratio > 0:
        factors.append(f"Harga {s.vwap_ratio * 100:.1f}% di atas VWAP (akumulasi)")

    if s.bb_position is not None and BB_NEAR_LOWER < s.bb_position < BB_NEAR_UPPER and s.bb_position >= 0.5:
        factors.append("Harga di paruh atas Bollinger Band (kekuatan)")

    return factors


def technical_risk(s: ExplainSnapshot) -> list[str]:
    """Sinyal risiko teknikal dari snapshot."""
    factors: list[str] = []

    if s.bb_position is not None and s.bb_position >= BB_NEAR_UPPER:
        factors.append("Dekat resistance (upper Bollinger Band)")

    if s.rsi is not None and s.rsi >= RSI_OVERBOUGHT:
        factors.append(f"Overbought (RSI {s.rsi:.0f})")
    elif s.rsi is not None and s.rsi <= RSI_OVERSOLD:
        factors.append(f"Oversold (RSI {s.rsi:.0f}) - tekanan jual masih ada")

    if s.atr_pct is not None and s.atr_pct >= ATR_HIGH_PCT:
        factors.append(f"Volatilitas tinggi (ATR {s.atr_pct * 100:.1f}% dari harga)")

    if (
        s.macd is not None
        and s.macd_signal is not None
        and s.macd < s.macd_signal
    ):
        factors.append("Momentum MACD melemah (di bawah garis sinyal)")

    if s.vwap_ratio is not None and s.vwap_ratio < 0:
        factors.append(f"Harga {abs(s.vwap_ratio) * 100:.1f}% di bawah VWAP (distribusi)")

    if s.bb_position is not None and s.bb_position <= BB_NEAR_LOWER:
        factors.append("Dekat support (lower Bollinger Band) - risiko breakdown")

    return factors


def confidence_from_probability(probability_up: float | None) -> int:
    """Confidence (0-100) dari probabilitas model. None -> 50 (netral)."""
    if probability_up is None:
        return 50
    return round(max(0.0, min(1.0, probability_up)) * 100)


def build_explanation(
    snapshot: ExplainSnapshot | None,
    probability_up: float | None,
    matched_factors: list[str],
) -> Explanation:
    """Gabungkan rule-based (matched_factors) + ML-layer (interpretasi teknikal).

    matched_factors didahulukan (paling akurat); duplikat dibuang sambil menjaga
    urutan.
    """
    bullish: list[str] = list(matched_factors)
    if snapshot is not None:
        for factor in technical_bullish(snapshot):
            if factor not in bullish:
                bullish.append(factor)

    risk = technical_risk(snapshot) if snapshot is not None else []

    return Explanation(
        confidence=confidence_from_probability(probability_up),
        bullish_factors=bullish,
        risk_factors=risk,
    )
