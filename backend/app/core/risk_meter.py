"""Risk Meter - ukur tingkat risiko saham (Low / Medium / High).

Sesuai blueprint Phase 2 (Risk Meter), empat parameter risiko digabung jadi
satu risk score 0-100 (makin tinggi = makin berisiko) lalu diklasifikasi:

  | Parameter              | Bobot | Makna                                       |
  |------------------------|-------|---------------------------------------------|
  | Historical Volatility  | 35%   | stdev return harian (disetahunkan, x√252)   |
  | ATR%                   | 20%   | rentang harian rata-rata / harga (Day 3)    |
  | Max Drawdown           | 30%   | penurunan puncak-ke-lembah terbesar         |
  | Beta                   | 15%   | sensitivitas vs proxy index (universe 80)   |

Klasifikasi: score < 34 -> LOW, < 67 -> MEDIUM, selain itu HIGH.

Beta dihitung terhadap **proxy index equal-weighted** (rata-rata return harian
seluruh saham di market_data) karena IHSG tidak disimpan - universe hanya 80
saham yang di-fetch server-side. Bila proxy tak tersedia, bobot Beta (15%)
diredistribusi ke tiga metrik lain.

Modul ini MURNI (tanpa DB/cache). API (risk.py) yang merakit input dari market_data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

TRADING_DAYS = 252  # hari bursa per tahun (untuk menyetahunkan volatilitas)

# Bobot metrik (jumlah = 1.0).
WEIGHT_HV = 0.35
WEIGHT_ATR = 0.20
WEIGHT_DRAWDOWN = 0.30
WEIGHT_BETA = 0.15

# Ambang sketsa untuk klasifikasi akhir.
THRESHOLD_LOW = 34.0   # < 34 -> LOW
THRESHOLD_HIGH = 67.0  # >= 67 -> HIGH


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class RiskInput:
    closes: list[float]  # seri penutupan kronologis (lama -> baru)
    atr_pct: float | None  # atr / close bar terakhir (pre-computed Day 3)
    market_returns: list[float] | None  # return harian proxy index (untuk Beta)


@dataclass(frozen=True)
class RiskResult:
    risk: str  # "LOW" | "MEDIUM" | "HIGH"
    score: int  # 0-100 (makin tinggi makin berisiko)
    atr_pct: float | None
    historical_volatility: float | None  # disetahunkan (mis. 0.42 = 42%)
    max_drawdown: float | None  # magnitudo 0..1 (mis. 0.25 = -25%)
    beta: float | None


# --------------------------------------------------------------------------- #
# Perhitungan metrik mentah
# --------------------------------------------------------------------------- #
def daily_returns(closes: list[float]) -> list[float]:
    """Return harian sederhana; lewati bar dengan harga sebelumnya 0/None."""
    out: list[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev:
            out.append(closes[i] / prev - 1)
    return out


def _stdev(values: list[float]) -> float | None:
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)  # sampel (N-1)
    return math.sqrt(variance)


def historical_volatility(closes: list[float]) -> float | None:
    """Volatilitas historis disetahunkan = stdev(return harian) * sqrt(252)."""
    sd = _stdev(daily_returns(closes))
    return None if sd is None else sd * math.sqrt(TRADING_DAYS)


def max_drawdown(closes: list[float]) -> float | None:
    """Penurunan puncak-ke-lembah terbesar (magnitudo positif 0..1)."""
    if len(closes) < 2:
        return None
    peak = closes[0]
    worst = 0.0
    for price in closes:
        if price > peak:
            peak = price
        if peak:
            worst = max(worst, (peak - price) / peak)
    return worst


def beta(closes: list[float], market_returns: list[float] | None) -> float | None:
    """Beta = cov(return saham, return pasar) / var(return pasar).

    Saham & pasar diselaraskan dari ekor (panjang terpendek) agar tanggalnya
    bersesuaian. None bila data pasar tak ada / varians pasar nol.
    """
    if not market_returns:
        return None
    stock = daily_returns(closes)
    n = min(len(stock), len(market_returns))
    if n < 2:
        return None
    stock = stock[-n:]
    market = market_returns[-n:]

    mean_s = sum(stock) / n
    mean_m = sum(market) / n
    cov = sum((s - mean_s) * (m - mean_m) for s, m in zip(stock, market)) / (n - 1)
    var_m = sum((m - mean_m) ** 2 for m in market) / (n - 1)
    if var_m == 0:
        return None
    return cov / var_m


# --------------------------------------------------------------------------- #
# Pemetaan metrik -> sub-skor risiko 0-100 (heuristik absolut)
# --------------------------------------------------------------------------- #
def _score_hv(hv: float | None) -> float | None:
    # 15% disetahunkan -> 0 (tenang); 80% -> 100 (sangat bergejolak).
    if hv is None:
        return None
    return _clamp((hv - 0.15) / (0.80 - 0.15) * 100)


def _score_atr(atr_pct: float | None) -> float | None:
    # 1% harian -> 0; 7% -> 100.
    if atr_pct is None:
        return None
    return _clamp((atr_pct - 0.01) / (0.07 - 0.01) * 100)


def _score_drawdown(dd: float | None) -> float | None:
    # 10% -> 0; 50% -> 100.
    if dd is None:
        return None
    return _clamp((dd - 0.10) / (0.50 - 0.10) * 100)


def _score_beta(b: float | None) -> float | None:
    # |beta| 0.5 -> 0 (defensif); 2.0 -> 100 (sangat agresif).
    if b is None:
        return None
    return _clamp((abs(b) - 0.5) / (2.0 - 0.5) * 100)


def _classify(score: float) -> str:
    if score < THRESHOLD_LOW:
        return "LOW"
    if score < THRESHOLD_HIGH:
        return "MEDIUM"
    return "HIGH"


# --------------------------------------------------------------------------- #
# Agregasi
# --------------------------------------------------------------------------- #
def compute_risk(inp: RiskInput) -> RiskResult:
    """Hitung risk score 0-100 + klasifikasi dari empat metrik.

    Tiap sub-skor punya bobot tetap; bobot metrik yang datanya tak tersedia
    diredistribusi proporsional ke metrik lain agar total bobot tetap 1.0.
    """
    hv = historical_volatility(inp.closes)
    dd = max_drawdown(inp.closes)
    b = beta(inp.closes, inp.market_returns)

    parts: list[tuple[float, float]] = []  # (sub_score, weight)
    for sub_score, weight in (
        (_score_hv(hv), WEIGHT_HV),
        (_score_atr(inp.atr_pct), WEIGHT_ATR),
        (_score_drawdown(dd), WEIGHT_DRAWDOWN),
        (_score_beta(b), WEIGHT_BETA),
    ):
        if sub_score is not None:
            parts.append((sub_score, weight))

    if parts:
        total_weight = sum(weight for _, weight in parts)
        raw = sum(sub * weight for sub, weight in parts) / total_weight
    else:
        raw = 50.0  # netral bila benar-benar tak ada data

    score = round(_clamp(raw))
    return RiskResult(
        risk=_classify(score),
        score=score,
        atr_pct=None if inp.atr_pct is None else round(inp.atr_pct, 4),
        historical_volatility=None if hv is None else round(hv, 4),
        max_drawdown=None if dd is None else round(dd, 4),
        beta=None if b is None else round(b, 3),
    )
