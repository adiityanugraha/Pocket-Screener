// REST client untuk backend Pocket Screener Phase 2 (FastAPI).
//
// Menggantikan komputasi berat client-side (fetch Yahoo + indikator + ONNX) -
// semua kini dihitung server-side. Base URL dari NEXT_PUBLIC_API_BASE_URL
// (default http://localhost:8000). Ticker dikirim TANPA sufiks .JK (backend
// menyimpan ticker dasar IDX).

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

/** Buang sufiks .JK & seragamkan huruf besar (frontend pakai "BBCA.JK"). */
export function bareTicker(symbol: string): string {
  return symbol.trim().toUpperCase().replace(/\.JK$/i, "");
}

async function apiGet<T>(path: string, params?: Record<string, string | number | boolean>): Promise<T> {
  const url = new URL(`${API_BASE_URL}${path}`);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      url.searchParams.set(key, String(value));
    }
  }

  let response: Response;
  try {
    response = await fetch(url.toString(), { headers: { accept: "application/json" } });
  } catch {
    throw new Error(
      `Tidak bisa terhubung ke backend (${API_BASE_URL}). Pastikan server FastAPI berjalan.`,
    );
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* abaikan body non-JSON */
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error(
      `Tidak bisa terhubung ke backend (${API_BASE_URL}). Pastikan server FastAPI berjalan.`,
    );
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const data = (await response.json()) as { detail?: string };
      if (data?.detail) detail = data.detail;
    } catch {
      /* abaikan body non-JSON */
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

// --------------------------------------------------------------------------- //
// Tipe respons (mirror schema Pydantic backend)
// --------------------------------------------------------------------------- //
export type Prediction = {
  label: number;
  probability_up: number;
  probability_down: number;
};

export type ScreenerLevels = {
  entry: number;
  stop_loss: number;
  take_profit: number;
  exit: number;
  risk_per_share: number;
  reward_per_share: number;
};

export type ScreenerCandidate = {
  ticker: string;
  name: string | null;
  sector: string | null;
  date: string;
  open: number;
  close: number;
  volume: number;
  value: number;
  strategy: string;
  score: number;
  prediction_score: number;
  prediction: Prediction | null;
  levels: ScreenerLevels;
};

export type ScreenerResponse = {
  generated_at: string;
  universe: number;
  screened: number;
  persisted: number;
  cached: boolean;
  bsjp: ScreenerCandidate[];
  bpjs: ScreenerCandidate[];
};

export type RankingBreakdown = {
  technical: number;
  momentum: number;
  volume: number;
  volatility: number;
  ml: number | null;
};

export type RankingItem = {
  rank: number;
  ticker: string;
  name: string | null;
  sector: string | null;
  date: string;
  close: number | null;
  overall_score: number;
  breakdown: RankingBreakdown;
};

export type RankingResponse = {
  generated_at: string;
  universe: number;
  ranked: number;
  use_ml: boolean;
  cached: boolean;
  items: RankingItem[];
};

export type StockReport = {
  ticker: string;
  name: string | null;
  sector: string | null;
  date: string;
  close: number | null;
  score: number;
  sentiment: string;
  summary: string;
  bullishFactors: string[];
  riskFactors: string[];
  use_ml: boolean;
  cached: boolean;
  generated_at: string;
};

export type RiskResponse = {
  ticker: string;
  name: string | null;
  sector: string | null;
  date: string;
  close: number | null;
  risk: string; // LOW | MEDIUM | HIGH
  score: number;
  breakdown: {
    atr_pct: number | null;
    historical_volatility: number | null;
    max_drawdown: number | null;
    beta: number | null;
  };
  cached: boolean;
  generated_at: string;
};

export type Zone = { lower: number; upper: number };

export type SupportResistanceResponse = {
  ticker: string;
  name: string | null;
  sector: string | null;
  date: string;
  current: number;
  support: number | null;
  resistance: number | null;
  breakout_zone: Zone | null;
  methods: {
    pivot: { pivot: number; r1: number; r2: number; s1: number; s2: number };
    swing_high: number | null;
    swing_low: number | null;
    atr_band: Zone | null;
  };
  cached: boolean;
  generated_at: string;
};

export type Mover = {
  ticker: string;
  name: string | null;
  close: number;
  change_pct: number;
};

export type SectorPerf = {
  sector: string;
  avg_change_pct: number;
  count: number;
};

export type MarketBreadthResponse = {
  date: string;
  advancers: number;
  decliners: number;
  unchanged: number;
  total: number;
  bullish_ratio: number | null;
  top_gainers: Mover[];
  top_losers: Mover[];
  sector_performance: SectorPerf[];
  persisted: boolean;
  cached: boolean;
  generated_at: string;
};

export type StrategyPerformance = {
  strategy: string;
  total: number;
  evaluated: number;
  wins: number;
  losses: number;
  flat: number;
  winrate: number | null;
  avg_return: number | null;
  cumulative_return: number | null;
  max_drawdown: number | null;
};

export type HistoryEntry = {
  date: string;
  ticker: string;
  name: string | null;
  strategy: string;
  score: number | null;
  entry_close: number;
  forward_close: number | null;
  forward_return: number | null;
  outcome: string; // WIN | LOSS | FLAT | PENDING
};

export type HistoryResponse = {
  horizon: number;
  count: number;
  entries: HistoryEntry[];
  summary: StrategyPerformance[];
  generated_at: string;
};

export type MarketBar = {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  value: number | null;
  rsi: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
  bb_upper: number | null;
  bb_middle: number | null;
  bb_lower: number | null;
  atr: number | null;
  vwap: number | null;
};

export type MarketDataResponse = {
  ticker: string;
  name: string | null;
  sector: string | null;
  count: number;
  cached: boolean;
  bars: MarketBar[];
};

// --------------------------------------------------------------------------- //
// Tipe Phase 3 - Multi-Strategy Engine
// --------------------------------------------------------------------------- //
export type StrategyMeta = {
  key: string;
  name: string;
  type: "technical" | "fundamental";
  output_label: string;
};

export type StrategyCandidate = {
  ticker: string;
  name: string | null;
  sector: string | null;
  date: string;
  open: number | null;
  close: number | null;
  volume: number;
  value: number;
  matched_criteria: string[];
};

export type StrategyScreenerResponse = {
  strategy: string;
  name: string;
  type: string;
  output_label: string;
  generated_at: string;
  universe: number;
  evaluated: number;
  passed: number;
  cached: boolean;
  candidates: StrategyCandidate[];
};

export type StrategyBucket = {
  strategy: string;
  name: string;
  type: string;
  output_label: string;
  evaluated: number;
  passed: number;
  candidates: StrategyCandidate[];
};

export type AllStrategiesResponse = {
  generated_at: string;
  universe: number;
  persisted: number;
  cached: boolean;
  strategies: StrategyBucket[];
};

export type MatrixRow = {
  ticker: string;
  name: string | null;
  sector: string | null;
  results: Record<string, boolean | null>;
  passed_count: number;
  passed_strategies: string[];
};

export type StrategyMatrixResponse = {
  date: string | null;
  generated_at: string;
  cached: boolean;
  universe_evaluated: number;
  strategies: StrategyMeta[];
  matrix: MatrixRow[];
};

// --------------------------------------------------------------------------- //
// Tipe Phase 3 - Forecast, Strength, Explain, Why (Day 15)
// --------------------------------------------------------------------------- //
export type ForecastResponse = {
  ticker: string;
  name: string | null;
  sector: string | null;
  date: string | null;
  prob: { "1d": number; "5d": number; "20d": number };
  confidence: "LOW" | "MEDIUM" | "HIGH";
  disclaimer: string;
  cached: boolean;
  generated_at: string;
};

export type StrengthComponent = {
  strategy: string;
  type: string;
  weight: number;
};

export type StrengthResponse = {
  ticker: string;
  name: string | null;
  sector: string | null;
  date: string | null;
  strength: number;
  points: number;
  max_points: number;
  passed_strategies: string[];
  breakdown: StrengthComponent[];
  cached: boolean;
  generated_at: string;
};

export type ExplainResponse = {
  ticker: string;
  name: string | null;
  sector: string | null;
  date: string | null;
  confidence: number;
  bullish_factors: string[];
  risk_factors: string[];
  passed_strategies: string[];
  cached: boolean;
  generated_at: string;
};

export type MatchedStrategy = {
  key: string;
  name: string;
  type: string;
  reasons: string[];
  skipped: string[];
};

export type WhyResponse = {
  ticker: string;
  name: string | null;
  sector: string | null;
  date: string | null;
  matched: string[];
  matched_strategies: MatchedStrategy[];
  reasons: string[];
  cached: boolean;
  generated_at: string;
};

// --- Phase 4: Quant Analytics & Validation -------------------------------- //
export type QuantMetrics = {
  cagr: number;
  winrate: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  max_drawdown: number;
  profit_factor: number;
  recovery_factor: number;
};

export type PerformanceResponse = {
  strategy: string;
  name: string | null;
  period: string;
  metrics: QuantMetrics;
  n_trades: number;
  n_periods: number;
  active_periods: number;
  start: string | null;
  end: string | null;
  hold: number;
  methodology: string;
  disclaimer: string;
  cached: boolean;
  generated_at: string;
};

export type EquityPoint = {
  date: string;
  value: number;
  peak: number;
  drawdown: number;
};

export type EquityCurveResponse = {
  strategy: string;
  name: string | null;
  hold: number;
  initial_capital: number;
  points: EquityPoint[];
  summary: { final_value: number; total_return: number; max_drawdown: number };
  methodology: string;
  disclaimer: string;
  cached: boolean;
  generated_at: string;
};

export type BenchmarkRow = {
  strategy: string;
  name: string | null;
  is_benchmark: boolean;
  n_periods: number;
  metrics: QuantMetrics;
  beats_market_cagr?: boolean | null;
  beats_market_sharpe?: boolean | null;
};

export type BenchmarkResponse = {
  hold: number;
  market: BenchmarkRow;
  strategies: BenchmarkRow[];
  methodology: string;
  disclaimer: string;
  cached: boolean;
  generated_at: string;
};

export type ReplayCandidate = {
  ticker: string;
  name: string | null;
  sector: string | null;
  price: number | null;
  value: number | null;
  ret: {
    "1d": number | null;
    "3d": number | null;
    "7d": number | null;
    "30d": number | null;
  };
};

export type ReplayResponse = {
  date: string;
  total_candidates: number;
  strategies: Record<string, ReplayCandidate[]>;
  data_range: { earliest: string | null; latest: string | null };
  disclaimer: string;
  cached: boolean;
  generated_at: string;
};

export type HistogramBin = { start: number; end: number; count: number };

export type MonteCarloResponse = {
  strategy: string;
  name: string | null;
  hold: number;
  horizon_years: number;
  n_periods: number;
  simulations: number;
  history_periods: number;
  probability_of_profit: number;
  mean: number;
  percentiles: { p5: number; p25: number; p50: number; p75: number; p95: number };
  histogram: HistogramBin[];
  disclaimer: string;
  cached: boolean;
  generated_at: string;
};

export type RiskProfileResponse = {
  strategy: string;
  name: string | null;
  hold: number;
  volatility: number;
  avg_atr_pct: number | null;
  beta: number;
  max_drawdown: number;
  losing_streak: number;
  risk_level: string;
  n_periods: number;
  thresholds: Record<string, number>;
  disclaimer: string;
  cached: boolean;
  generated_at: string;
};

export type CorrelationPair = {
  ticker_a: string;
  ticker_b: string;
  correlation: number;
};

export type CorrelationResponse = {
  universe: string;
  window: string;
  tickers: string[];
  matrix: number[][];
  top_correlated: CorrelationPair[];
  n: number;
  disclaimer: string;
  computed_at: string;
  cached: boolean;
};

export type PortfolioAllocation = {
  ticker: string;
  name: string | null;
  sector: string | null;
  weight: number;
  amount: number;
  score: number;
  risk_level: string;
  risk_score: number;
};

export type PortfolioResponse = {
  risk_profile: string;
  capital: number;
  universe: string;
  n_positions: number;
  allocations: PortfolioAllocation[];
  summary: {
    weighted_risk_score: number;
    portfolio_risk_level: string;
    avg_correlation: number;
    config: Record<string, unknown>;
  };
  saved_id: number | null;
  disclaimer: string;
  generated_at: string;
};

// --------------------------------------------------------------------------- //
// Endpoint
// --------------------------------------------------------------------------- //
export function getScreener(limit = 5, useMl = true): Promise<ScreenerResponse> {
  return apiGet("/api/screener", { limit, use_ml: useMl });
}

export function getRanking(limit = 20, useMl = true): Promise<RankingResponse> {
  return apiGet("/api/ranking", { limit, use_ml: useMl });
}

export function getStockReport(symbol: string, useMl = true): Promise<StockReport> {
  return apiGet(`/api/stock-report/${bareTicker(symbol)}`, { use_ml: useMl });
}

export function getRisk(symbol: string): Promise<RiskResponse> {
  return apiGet(`/api/risk/${bareTicker(symbol)}`);
}

export function getSupportResistance(symbol: string): Promise<SupportResistanceResponse> {
  return apiGet(`/api/support-resistance/${bareTicker(symbol)}`);
}

export function getMarketBreadth(): Promise<MarketBreadthResponse> {
  return apiGet("/api/market-breadth");
}

export function getHistory(params?: {
  date?: string;
  strategy?: string;
  horizon?: number;
  limit?: number;
}): Promise<HistoryResponse> {
  return apiGet("/api/history", params as Record<string, string | number>);
}

export function getMarketData(symbol: string, limit?: number): Promise<MarketDataResponse> {
  return apiGet(`/api/market-data/${bareTicker(symbol)}`, limit ? { limit } : undefined);
}

// --- Phase 3: Multi-Strategy Engine --------------------------------------- //
export function getStrategies(): Promise<StrategyMeta[]> {
  return apiGet("/api/strategies");
}

export function getStrategyScreener(
  strategy: string,
  limit = 10,
): Promise<StrategyScreenerResponse> {
  return apiGet("/api/screener", { strategy, limit });
}

export function getScreenerAll(limit = 10): Promise<AllStrategiesResponse> {
  return apiGet("/api/screener/all", { limit });
}

export function getStrategyMatrix(minPassed = 1): Promise<StrategyMatrixResponse> {
  return apiGet("/api/strategy-matrix", { min_passed: minPassed });
}

export function getForecast(symbol: string): Promise<ForecastResponse> {
  return apiGet(`/api/forecast/${bareTicker(symbol)}`);
}

export function getStrength(symbol: string): Promise<StrengthResponse> {
  return apiGet(`/api/strength/${bareTicker(symbol)}`);
}

export function getExplain(symbol: string): Promise<ExplainResponse> {
  return apiGet(`/api/explain/${bareTicker(symbol)}`);
}

export function getWhy(symbol: string): Promise<WhyResponse> {
  return apiGet(`/api/why/${bareTicker(symbol)}`);
}

// --- Phase 4: Quant Analytics & Validation -------------------------------- //
export function getPerformance(strategy: string): Promise<PerformanceResponse> {
  return apiGet(`/api/performance/${strategy}`);
}

export function getEquityCurve(
  strategy: string,
  initialCapital = 100_000_000,
): Promise<EquityCurveResponse> {
  return apiGet(`/api/equity-curve/${strategy}`, { initial_capital: initialCapital });
}

export function getBenchmark(): Promise<BenchmarkResponse> {
  return apiGet("/api/benchmark");
}

export function getReplay(date: string, limit = 10): Promise<ReplayResponse> {
  return apiGet(`/api/replay/${date}`, { limit });
}

export function getMonteCarlo(strategy: string): Promise<MonteCarloResponse> {
  return apiGet(`/api/monte-carlo/${strategy}`);
}

export function getRiskProfile(strategy: string): Promise<RiskProfileResponse> {
  return apiGet(`/api/risk-profile/${strategy}`);
}

export function getCorrelation(
  universe = "lq45",
  window = 90,
): Promise<CorrelationResponse> {
  return apiGet("/api/correlation", { universe, window });
}

export function postPortfolioBuilder(body: {
  risk: string;
  capital: number;
  universe: string;
}): Promise<PortfolioResponse> {
  return apiPost("/api/portfolio-builder", body);
}

// --- Phase 5: AI Financial Analyst ---------------------------------------- //
export type AiAnalysisResponse = {
  ticker: string;
  date: string | null;
  confidence: number | null;
  summary: string | null;
  bullish_factors: string[];
  risk_factors: string[];
  ai_generated: boolean;
  note: string | null;
  disclaimer: string;
  cached: boolean;
  generated_at: string | null;
};

export type ExplainComponent = {
  component: string;
  label: string;
  score: number;
  weight: number;
  effective_weight: number;
  contribution: number;
};

export type ExplainScoreResponse = {
  ticker: string;
  date: string | null;
  overall_score: number | null;
  ml_available: boolean;
  breakdown: ExplainComponent[];
  summary: string | null;
  bullish_factors: string[];
  risk_factors: string[];
  ai_generated: boolean;
  note: string | null;
  disclaimer: string;
  cached: boolean;
  generated_at: string | null;
};

export type CompareStrategyResponse = {
  strategy_a: string;
  strategy_b: string;
  name_a: string | null;
  name_b: string | null;
  metrics_a: Record<string, number>;
  metrics_b: Record<string, number>;
  comparison: string | null;
  disclaimer: string;
  cached: boolean;
  generated_at: string | null;
};

export type AdvisorAllocation = {
  ticker: string;
  weight: number;
  amount?: number;
  score?: number;
  risk_level?: string;
  sector?: string;
};

export type PortfolioAdvisorResponse = {
  risk_profile: string;
  capital: number;
  universe: string;
  n_positions: number;
  allocations: AdvisorAllocation[];
  summary: Record<string, unknown>;
  explanation: string | null;
  disclaimer: string;
  cached: boolean;
  generated_at: string | null;
};

export type MarketSummaryResponse = {
  date: string | null;
  summary: string | null;
  bullish_ratio: number | null;
  advancers: number | null;
  decliners: number | null;
  leading_sectors: string[];
  lagging_sectors: string[];
  best_strategy: string | null;
  disclaimer: string;
  cached: boolean;
  generated_at: string | null;
};

export type DailyReportResponse = {
  date: string | null;
  overview: string | null;
  top_opportunities: { ticker: string; name: string | null; overall_score: number }[];
  strongest_sector: string | null;
  weakest_sector: string | null;
  leading_sectors: string[];
  lagging_sectors: string[];
  high_confidence: { ticker: string; prob_5d: number | null; prob_20d: number | null; confidence: string }[];
  risk_warnings: { ticker: string; risk: string; score: number | null }[];
  disclaimer: string;
  cached?: boolean;
  generated_at: string | null;
};

export function getAiAnalysis(symbol: string): Promise<AiAnalysisResponse> {
  return apiGet(`/api/ai-analysis/${bareTicker(symbol)}`);
}

export function getExplainScore(symbol: string): Promise<ExplainScoreResponse> {
  return apiGet(`/api/explain-score/${bareTicker(symbol)}`);
}

export function getCompareStrategy(a: string, b: string): Promise<CompareStrategyResponse> {
  return apiGet("/api/compare-strategy", { a, b });
}

export function postPortfolioAdvisor(body: {
  risk: string;
  capital: number;
  universe: string;
}): Promise<PortfolioAdvisorResponse> {
  return apiPost("/api/portfolio-advisor", body);
}

export function getMarketSummary(): Promise<MarketSummaryResponse> {
  return apiGet("/api/market-summary");
}

export function getDailyReport(): Promise<DailyReportResponse> {
  return apiGet("/api/daily-report");
}

/** URL langsung ke endpoint daily-report (untuk tombol unduh PDF / lihat Markdown). */
export function dailyReportUrl(format: "pdf" | "markdown"): string {
  return `${API_BASE_URL}/api/daily-report?format=${format}`;
}

/**
 * Chat streaming: kirim pesan, panggil onChunk per potongan teks, kembalikan
 * teks penuh. session_id digenerate klien (tak perlu baca header respons).
 */
export async function streamChat(
  message: string,
  sessionId: string,
  onChunk: (chunk: string) => void,
): Promise<string> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId, stream: true }),
    });
  } catch {
    throw new Error(`Tidak bisa terhubung ke backend (${API_BASE_URL}).`);
  }
  if (!response.ok || !response.body) {
    let detail = `HTTP ${response.status}`;
    try {
      const data = (await response.json()) as { detail?: string };
      if (data?.detail) detail = data.detail;
    } catch {
      /* abaikan */
    }
    throw new Error(detail);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let full = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    full += chunk;
    onChunk(chunk);
  }
  return full;
}

// --- Meta (Phase: tanggal data asli untuk header/footer) ---
export type MetaResponse = { data_date: string | null; universe: number };

export function getMeta(): Promise<MetaResponse> {
  return apiGet("/api/meta");
}
