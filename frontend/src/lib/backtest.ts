export type SampleTrade = {
  symbol: string;
  signalDate: string;
  entry: number;
  exit: number;
  returnPct: number;
  win: boolean;
};

export type BacktestResult = {
  strategy: string;
  generatedAt: string;
  source: string;
  symbols: string[];
  periodStart: string;
  periodEnd: string;
  totalTrades: number;
  winrate: number;
  cumulativeReturn: number;
  averageReturn: number;
  maxDrawdown: number;
  assumptions: string;
  sampleTrades: SampleTrade[];
};

export type ModelMetrics = {
  model: string;
  target: string;
  features: string[];
  trainRows: number;
  testRows: number;
  splitDate: string;
  accuracy: number;
  precision: number;
  recall: number;
};

export const BSJP_RESULT_URL = "/backtesting/bsjp_result.json";
export const BPJS_RESULT_URL = "/backtesting/bpjs_result.json";
export const MODEL_METRICS_URL = "/model_metrics.json";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    headers: { accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error(`Failed to load ${url} (HTTP ${response.status})`);
  }

  return (await response.json()) as T;
}

// Sample trade mentah dari JSON. File hasil notebook (offline) memakai
// snake_case (date, return_pct, tanpa win); script .mjs memakai camelCase
// (signalDate, returnPct, win). Reader menerima keduanya agar tahan format.
type RawSampleTrade = {
  symbol: string;
  signalDate?: string;
  date?: string;
  entry: number;
  exit: number;
  returnPct?: number;
  return_pct?: number;
  win?: boolean;
};

type RawBacktestResult = Omit<BacktestResult, "sampleTrades"> & {
  sampleTrades?: RawSampleTrade[];
};

function normalizeTrade(raw: RawSampleTrade): SampleTrade {
  const returnPct = raw.returnPct ?? raw.return_pct ?? 0;
  // "2024-04-30 00:00:00" -> "2024-04-30"
  const signalDate = (raw.signalDate ?? raw.date ?? "").slice(0, 10);

  return {
    symbol: raw.symbol,
    signalDate,
    entry: raw.entry,
    exit: raw.exit,
    returnPct,
    win: raw.win ?? returnPct > 0,
  };
}

export async function fetchBacktestResult(url: string): Promise<BacktestResult> {
  const raw = await fetchJson<RawBacktestResult>(url);

  return {
    ...raw,
    sampleTrades: (raw.sampleTrades ?? []).map(normalizeTrade),
  };
}

export function fetchModelMetrics(): Promise<ModelMetrics> {
  return fetchJson<ModelMetrics>(MODEL_METRICS_URL);
}

export type EquityPoint = {
  index: number;
  date: string;
  // Cumulative return in percent, compounded across sample trades.
  cumulativePct: number;
};

// Build a compounded equity curve from a strategy's sample trades. The sample
// is a recent subset (not the full period), so this is a shape/illustration
// of the strategy - headline stats use the precomputed full-period numbers.
export function buildEquityCurve(trades: SampleTrade[]): EquityPoint[] {
  const ordered = [...trades].sort((a, b) =>
    a.signalDate.localeCompare(b.signalDate),
  );

  let equity = 1;
  const points: EquityPoint[] = [
    { index: 0, date: ordered[0]?.signalDate ?? "", cumulativePct: 0 },
  ];

  ordered.forEach((trade, position) => {
    equity *= 1 + trade.returnPct;
    points.push({
      index: position + 1,
      date: trade.signalDate,
      cumulativePct: (equity - 1) * 100,
    });
  });

  return points;
}

export function formatPercent(value: number, fractionDigits = 1): string {
  return `${(value * 100).toFixed(fractionDigits)}%`;
}

export function formatSignedPercent(value: number, fractionDigits = 1): string {
  const formatted = `${(value * 100).toFixed(fractionDigits)}%`;
  return value > 0 ? `+${formatted}` : formatted;
}
