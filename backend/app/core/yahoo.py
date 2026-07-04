"""Fetch OHLCV harian dari Yahoo Finance - sisi server (bypass CORS).

Menggantikan fetch browser Phase 1 (frontend/src/lib/fetchData.ts). Logika
disamakan:
  - ticker IDX dinormalkan dengan sufiks ".JK" (mis. "BBCA" -> "BBCA.JK")
  - endpoint chart v8, range default "6mo", interval "1d"
  - bar di-skip bila ada open/high/low/close/volume yang null/invalid
    (mirror parseYahooChartResponse)

Catatan: Yahoo menolak request tanpa User-Agent browser, jadi header di-set.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.core.instruments import INDEX_SYMBOLS

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

DEFAULT_RANGE = "6mo"
DEFAULT_INTERVAL = "1d"
DEFAULT_TIMEOUT = 15.0

# Yahoo memblokir client tanpa UA browser (HTTP 401/429).
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


@dataclass(frozen=True)
class Bar:
    """Satu bar OHLCV harian. `date` = string ISO 'YYYY-MM-DD' (sama dgn frontend)."""

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class YahooFetchError(RuntimeError):
    """Gagal mengambil / mem-parse data Yahoo untuk satu simbol."""


def normalize_idx_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    return normalized if normalized.endswith(".JK") else f"{normalized}.JK"


def to_yahoo_symbol(ticker: str) -> str:
    """Petakan ticker internal -> simbol Yahoo.

    Indeks (mis. IHSG) -> simbol khusus (^JKSE); saham biasa -> sufiks .JK.
    """
    normalized = ticker.strip().upper()
    if normalized in INDEX_SYMBOLS:
        return INDEX_SYMBOLS[normalized]
    return normalize_idx_symbol(normalized)


def _is_valid(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def parse_chart_response(payload: dict, symbol: str) -> list[Bar]:
    """Port dari parseYahooChartResponse (frontend)."""
    chart = payload.get("chart") or {}
    error = chart.get("error")
    if error:
        description = error.get("description") or error.get("code") or "unknown error"
        raise YahooFetchError(f"Yahoo Finance error for {symbol}: {description}")

    results = chart.get("result") or []
    if not results:
        return []
    result = results[0]

    timestamps = result.get("timestamp") or []
    quotes = (result.get("indicators") or {}).get("quote") or []
    if not quotes or not timestamps:
        return []
    quote = quotes[0]

    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    bars: list[Bar] = []
    for index, timestamp in enumerate(timestamps):
        open_ = opens[index] if index < len(opens) else None
        high = highs[index] if index < len(highs) else None
        low = lows[index] if index < len(lows) else None
        close = closes[index] if index < len(closes) else None
        volume = volumes[index] if index < len(volumes) else None

        if not (_is_valid(open_) and _is_valid(high) and _is_valid(low)):
            continue
        if not (_is_valid(close) and _is_valid(volume)):
            continue

        bar_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()
        bars.append(
            Bar(
                date=bar_date,
                open=float(open_),
                high=float(high),
                low=float(low),
                close=float(close),
                volume=int(volume),
            )
        )

    return bars


def fetch_daily_ohlcv(
    ticker: str,
    range_: str = DEFAULT_RANGE,
    interval: str = DEFAULT_INTERVAL,
    client: httpx.Client | None = None,
) -> list[Bar]:
    """Ambil OHLCV harian satu ticker IDX. Kembalikan list Bar urut kronologis.

    Jika `client` diberikan, koneksi dipakai ulang (efisien untuk banyak ticker).
    """
    symbol = to_yahoo_symbol(ticker)
    url = YAHOO_CHART_URL.format(symbol=symbol)
    params = {
        "range": range_,
        "interval": interval,
        "includePrePost": "false",
        "events": "history",
    }

    owns_client = client is None
    client = client or httpx.Client(timeout=DEFAULT_TIMEOUT, headers=_HEADERS)
    try:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:  # network / HTTP status
        raise YahooFetchError(f"Request gagal untuk {symbol}: {exc}") from exc
    finally:
        if owns_client:
            client.close()

    return parse_chart_response(payload, symbol)
