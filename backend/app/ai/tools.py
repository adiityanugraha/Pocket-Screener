"""Tools layer - jembatan GROUNDING (Phase 5 Day 4).

Membungkus logika/endpoint Phase 1-4 sebagai "tool" yang dipanggil IN-PROCESS
(bukan HTTP) dan mengembalikan dict berisi ANGKA LIVE dari sistem. Inilah sumber
kebenaran angka untuk seluruh fitur LLM: LLM memanggil tool ini lalu MENARASIKAN
hasilnya - tidak pernah mengarang angka.

Registry bersifat pluggable: tambah tool baru = tambah satu entri TOOLS. Fitur
hari berikutnya (Day 5 AI Analyst, Day 7 Chat) memakai run_tool()/tool_specs().

Catatan data: beberapa tool butuh data yang mungkin belum direkonstruksi di DB
lokal (mis. strategy_results/forecast kosong sampai reconstruct dijalankan).
Tool yang gagal/empty mengembalikan {"error": ...}, tidak melempar - caller aman.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api import forecast as forecast_api
from app.api import market_breadth as breadth_api
from app.api import ranking as ranking_api
from app.api import risk as risk_api
from app.api import sector_rotation as sector_api
from app.api import support_resistance as sr_api
from app.db.models import MarketData
from app.db.session import SessionLocal

_TICKER_PARAM = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string", "description": "Kode saham IDX tanpa .JK, mis. BBCA"}
    },
    "required": ["ticker"],
}
_NO_PARAM = {"type": "object", "properties": {}}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    run: Callable[[dict[str, Any], Session], dict[str, Any]]


def _ticker(args: dict[str, Any]) -> str:
    ticker = (args or {}).get("ticker", "")
    if not ticker or not str(ticker).strip():
        raise ValueError("Parameter 'ticker' wajib diisi.")
    return str(ticker).strip().upper()


# --------------------------------------------------------------------------- #
# Implementasi tiap tool (dipanggil dengan session aktif)
# --------------------------------------------------------------------------- #
def _market_data(args: dict[str, Any], db: Session) -> dict[str, Any]:
    ticker = _ticker(args)
    row = db.scalars(
        select(MarketData).where(MarketData.ticker == ticker).order_by(desc(MarketData.date)).limit(1)
    ).first()
    if row is None:
        return {"error": f"Tidak ada market_data untuk {ticker}."}
    return {
        "ticker": ticker,
        "date": row.date.isoformat(),
        "open": row.open, "high": row.high, "low": row.low, "close": row.close,
        "volume": row.volume, "value": row.value,
        "rsi": row.rsi, "macd": row.macd, "macd_signal": row.macd_signal,
        "macd_histogram": row.macd_histogram,
        "bb_upper": row.bb_upper, "bb_middle": row.bb_middle, "bb_lower": row.bb_lower,
        "atr": row.atr, "vwap": row.vwap,
    }


def _risk(args: dict[str, Any], db: Session) -> dict[str, Any]:
    return risk_api.get_risk(ticker=_ticker(args), refresh=False, db=db)


def _support_resistance(args: dict[str, Any], db: Session) -> dict[str, Any]:
    return sr_api.get_support_resistance(ticker=_ticker(args), refresh=False, db=db)


def _composite_score(args: dict[str, Any], db: Session) -> dict[str, Any]:
    ticker = _ticker(args)
    result = ranking_api.run_ranking(db, limit=80, use_ml=True)
    item = next((it for it in result.get("items", []) if it["ticker"] == ticker), None)
    if item is None:
        return {"error": f"{ticker} tidak ter-ranking (data kurang / tidak memenuhi MIN_BARS)."}
    return item


def _forecast(args: dict[str, Any], db: Session) -> dict[str, Any]:
    return forecast_api.get_forecast(ticker=_ticker(args), refresh=False, db=db)


def _sector_rotation(args: dict[str, Any], db: Session) -> dict[str, Any]:
    return sector_api.get_sector_rotation(as_of=None, top=3, refresh=False, db=db)


def _market_breadth(args: dict[str, Any], db: Session) -> dict[str, Any]:
    return breadth_api.get_market_breadth(date=None, top=5, persist=False, refresh=False, db=db)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
TOOLS: dict[str, Tool] = {
    "get_market_data": Tool(
        "get_market_data",
        "OHLCV terbaru + indikator teknikal (RSI, MACD, Bollinger, ATR, VWAP) sebuah saham.",
        _TICKER_PARAM, _market_data,
    ),
    "get_risk": Tool(
        "get_risk",
        "Profil risiko sebuah saham (Low/Medium/High) dari ATR, volatilitas, drawdown, beta.",
        _TICKER_PARAM, _risk,
    ),
    "get_support_resistance": Tool(
        "get_support_resistance",
        "Level support, resistance, dan zona breakout sebuah saham.",
        _TICKER_PARAM, _support_resistance,
    ),
    "get_composite_score": Tool(
        "get_composite_score",
        "Composite Score 0-100 sebuah saham + breakdown (technical/momentum/volume/volatility/ml).",
        _TICKER_PARAM, _composite_score,
    ),
    "get_forecast": Tool(
        "get_forecast",
        "Probabilitas return positif 1D/5D/20D sebuah saham + tingkat keyakinan (LOW/MEDIUM/HIGH).",
        _TICKER_PARAM, _forecast,
    ),
    "get_sector_rotation": Tool(
        "get_sector_rotation",
        "Kekuatan relatif & rotasi sektor (1M/3M/6M vs IHSG) + leaders/laggards.",
        _NO_PARAM, _sector_rotation,
    ),
    "get_market_breadth": Tool(
        "get_market_breadth",
        "Konteks pasar: advancers/decliners, Bullish Ratio, top gainers/losers, performa sektor.",
        _NO_PARAM, _market_breadth,
    ),
}


def tool_specs() -> list[dict[str, Any]]:
    """Spesifikasi tool (provider-netral) untuk function-calling LLM."""
    return [
        {"name": t.name, "description": t.description, "parameters": t.parameters}
        for t in TOOLS.values()
    ]


def run_tool(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Jalankan tool by name dengan session DB baru. Selalu kembalikan dict (aman-gagal)."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": f"Tool tidak dikenal: {name}"}
    if SessionLocal is None:
        return {"error": "DATABASE_URL belum dikonfigurasi."}
    db = SessionLocal()
    try:
        return tool.run(args or {}, db)
    except HTTPException as exc:
        return {"error": str(exc.detail), "status": exc.status_code}
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - tool tak boleh menjatuhkan caller
        return {"error": f"Tool '{name}' gagal: {exc}"}
    finally:
        db.close()
