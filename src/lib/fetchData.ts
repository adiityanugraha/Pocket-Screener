import type { OhlcvBar } from "./indicators";

export type YahooRange = "5d" | "1mo" | "3mo" | "6mo" | "1y" | "5y";
export type YahooInterval = "1d" | "1wk" | "1mo";

export type FetchMarketDataOptions = {
  range?: YahooRange;
  interval?: YahooInterval;
  cacheTtlMs?: number;
  forceRefresh?: boolean;
  proxyUrl?: string;
  concurrency?: number;
};

type YahooFinanceBar = {
  timestamp?: number[];
  indicators?: {
    quote?: Array<{
      open?: Array<number | null>;
      high?: Array<number | null>;
      low?: Array<number | null>;
      close?: Array<number | null>;
      volume?: Array<number | null>;
    }>;
  };
};

type YahooFinanceResponse = {
  chart?: {
    result?: YahooFinanceBar[] | null;
    error?: {
      code?: string;
      description?: string;
    } | null;
  };
};

type CachedMarketData = {
  savedAt: number;
  bars: OhlcvBar[];
};

const DEFAULT_RANGE: YahooRange = "6mo";
const DEFAULT_INTERVAL: YahooInterval = "1d";
const DEFAULT_CACHE_TTL_MS = 15 * 60 * 1000;
const DEFAULT_FETCH_CONCURRENCY = 8;
const CACHE_PREFIX = "pocket-screener:ohlcv";
const SAME_ORIGIN_YAHOO_PROXY = "/api/yahoo?url=";

export function normalizeIdxSymbol(symbol: string): string {
  const normalized = symbol.trim().toUpperCase();

  return normalized.endsWith(".JK") ? normalized : `${normalized}.JK`;
}

export function buildYahooChartUrl(
  symbol: string,
  range: YahooRange = DEFAULT_RANGE,
  interval: YahooInterval = DEFAULT_INTERVAL,
): string {
  const yahooSymbol = encodeURIComponent(normalizeIdxSymbol(symbol));
  const params = new URLSearchParams({
    range,
    interval,
    includePrePost: "false",
    events: "history",
  });

  return `https://query1.finance.yahoo.com/v8/finance/chart/${yahooSymbol}?${params.toString()}`;
}

export async function fetchDailyOhlcv(
  symbol: string,
  options: FetchMarketDataOptions = {},
): Promise<OhlcvBar[]> {
  return fetchOhlcv(symbol, { ...options, interval: "1d" });
}

export async function fetchOhlcv(
  symbol: string,
  options: FetchMarketDataOptions = {},
): Promise<OhlcvBar[]> {
  const range = options.range ?? DEFAULT_RANGE;
  const interval = options.interval ?? DEFAULT_INTERVAL;
  const cacheTtlMs = options.cacheTtlMs ?? DEFAULT_CACHE_TTL_MS;
  const yahooSymbol = normalizeIdxSymbol(symbol);
  const cacheKey = getCacheKey(yahooSymbol, range, interval);

  if (!options.forceRefresh) {
    const cached = readMarketDataCache(cacheKey, cacheTtlMs);

    if (cached) {
      return cached;
    }
  }

  const yahooUrl = buildYahooChartUrl(yahooSymbol, range, interval);
  const response = await fetchWithCorsFallback(yahooUrl, options.proxyUrl);
  const payload = (await response.json()) as YahooFinanceResponse;
  const bars = parseYahooChartResponse(payload, yahooSymbol);

  writeMarketDataCache(cacheKey, bars);

  return bars;
}

// Fetch many symbols resiliently: limited concurrency to avoid Yahoo
// rate-limits, and individual failures are skipped so a single bad symbol
// never breaks the whole screener run.
export async function fetchManyDailyOhlcv(
  symbols: string[],
  options: FetchMarketDataOptions = {},
): Promise<Record<string, OhlcvBar[]>> {
  const batchSize = options.concurrency ?? DEFAULT_FETCH_CONCURRENCY;
  const result: Record<string, OhlcvBar[]> = {};

  for (let start = 0; start < symbols.length; start += batchSize) {
    const batch = symbols.slice(start, start + batchSize);
    const settled = await Promise.allSettled(
      batch.map(async (symbol) => {
        const yahooSymbol = normalizeIdxSymbol(symbol);
        const bars = await fetchDailyOhlcv(yahooSymbol, options);

        return [yahooSymbol, bars] as const;
      }),
    );

    for (const outcome of settled) {
      if (outcome.status === "fulfilled") {
        const [yahooSymbol, bars] = outcome.value;
        result[yahooSymbol] = bars;
      }
    }
  }

  return result;
}

export function parseYahooChartResponse(
  payload: YahooFinanceResponse,
  symbol: string,
): OhlcvBar[] {
  const error = payload.chart?.error;

  if (error) {
    throw new Error(
      `Yahoo Finance error for ${symbol}: ${error.description ?? error.code ?? "unknown error"}`,
    );
  }

  const result = payload.chart?.result?.[0];
  const timestamps = result?.timestamp ?? [];
  const quote = result?.indicators?.quote?.[0];

  if (!quote || timestamps.length === 0) {
    return [];
  }

  return timestamps.flatMap((timestamp, index) => {
    const open = quote.open?.[index];
    const high = quote.high?.[index];
    const low = quote.low?.[index];
    const close = quote.close?.[index];
    const volume = quote.volume?.[index];

    if (!isValidBarValue(open) || !isValidBarValue(high) || !isValidBarValue(low)) {
      return [];
    }

    if (!isValidBarValue(close) || !isValidBarValue(volume)) {
      return [];
    }

    return {
      symbol,
      date: new Date(timestamp * 1000).toISOString().slice(0, 10),
      open,
      high,
      low,
      close,
      volume,
    };
  });
}

async function fetchWithCorsFallback(
  yahooUrl: string,
  explicitProxyUrl?: string,
): Promise<Response> {
  const proxyUrl =
    explicitProxyUrl ??
    process.env.NEXT_PUBLIC_MARKET_DATA_PROXY_URL ??
    getSameOriginProxyUrl();

  if (proxyUrl && typeof window !== "undefined") {
    return fetchJson(buildProxyUrl(proxyUrl, yahooUrl));
  }

  try {
    return await fetchJson(yahooUrl);
  } catch (directError) {
    if (!proxyUrl) {
      throw directError;
    }

    return fetchJson(buildProxyUrl(proxyUrl, yahooUrl));
  }
}

async function fetchJson(url: string): Promise<Response> {
  const response = await fetch(url, {
    headers: {
      accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`Market data request failed with HTTP ${response.status}`);
  }

  return response;
}

function buildProxyUrl(proxyUrl: string, targetUrl: string): string {
  if (proxyUrl.includes("{url}")) {
    return proxyUrl.replace("{url}", encodeURIComponent(targetUrl));
  }

  return `${proxyUrl}${encodeURIComponent(targetUrl)}`;
}

function readMarketDataCache(
  cacheKey: string,
  cacheTtlMs: number,
): OhlcvBar[] | null {
  if (!canUseLocalStorage()) {
    return null;
  }

  const raw = window.localStorage.getItem(cacheKey);

  if (!raw) {
    return null;
  }

  try {
    const cached = JSON.parse(raw) as CachedMarketData;
    const isFresh = Date.now() - cached.savedAt <= cacheTtlMs;

    return isFresh ? cached.bars : null;
  } catch {
    window.localStorage.removeItem(cacheKey);

    return null;
  }
}

function writeMarketDataCache(cacheKey: string, bars: OhlcvBar[]) {
  if (!canUseLocalStorage()) {
    return;
  }

  const payload: CachedMarketData = {
    savedAt: Date.now(),
    bars,
  };

  window.localStorage.setItem(cacheKey, JSON.stringify(payload));
}

function getCacheKey(
  symbol: string,
  range: YahooRange,
  interval: YahooInterval,
): string {
  return `${CACHE_PREFIX}:${symbol}:${range}:${interval}`;
}

function canUseLocalStorage(): boolean {
  return typeof window !== "undefined" && "localStorage" in window;
}

function getSameOriginProxyUrl(): string | undefined {
  return typeof window === "undefined" ? undefined : SAME_ORIGIN_YAHOO_PROXY;
}

function isValidBarValue(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}
