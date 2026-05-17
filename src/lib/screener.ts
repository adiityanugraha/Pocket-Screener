import {
  calculateAtr,
  calculateBollingerBands,
  calculateMacd,
  calculateRsi,
  calculateTradeValue,
  calculateVolumeSpike,
  calculateVwap,
  simpleMovingAverage,
  type BollingerBand,
  type OhlcvBar,
  type VolumeSpike,
} from "./indicators.ts";

export type ScreenerStrategy = "BSJP" | "BPJS";

export type ScreenerInput = {
  current: OhlcvBar;
  previous: OhlcvBar;
  priceMa5: number;
  atr: number | null;
  rsi: number | null;
  macd: number | null;
  macdSignal: number | null;
  macdHistogram: number | null;
  bollinger: BollingerBand;
  vwap: number | null;
  volumeSpike: VolumeSpike;
};

export type ScreenerCriteria = {
  priceVsPrevious: boolean;
  priceVsMa5: boolean;
  priceVsOpen?: boolean;
  volumeVsPrevious: boolean;
  valueThreshold: boolean;
};

export type TradeLevels = {
  entry: number;
  stopLoss: number;
  takeProfit: number;
  exit: number;
  riskPerShare: number;
  rewardPerShare: number;
};

export type ScreenerCandidate = ScreenerInput & {
  strategy: ScreenerStrategy;
  criteria: ScreenerCriteria;
  score: number;
  value: number;
  levels: TradeLevels;
};

export type ScreenerResult = {
  bsjp: ScreenerCandidate[];
  bpjs: ScreenerCandidate[];
  all: ScreenerCandidate[];
};

export type ScreenerOptions = {
  limit?: number;
  minDailyValue?: number;
  atrMultiplier?: number;
  riskRewardRatio?: number;
};

const MIN_DAILY_VALUE = 5_000_000_000;
const DEFAULT_ATR_MULTIPLIER = 1;
const DEFAULT_RISK_REWARD_RATIO = 2;

export function buildScreenerInput(bars: OhlcvBar[]): ScreenerInput | null {
  if (bars.length < 6) {
    return null;
  }

  const current = bars.at(-1);
  const previous = bars.at(-2);

  if (!current || !previous) {
    return null;
  }

  const closes = bars.map((bar) => bar.close);
  const volumes = bars.map((bar) => bar.volume);
  const macd = calculateMacd(closes);
  const latestIndex = bars.length - 1;

  return {
    current,
    previous,
    priceMa5: simpleMovingAverage(closes, 5) ?? current.close,
    atr: calculateAtr(bars).at(-1) ?? null,
    rsi: calculateRsi(closes).at(-1) ?? null,
    macd: macd.macd.at(-1) ?? null,
    macdSignal: macd.signal.at(-1) ?? null,
    macdHistogram: macd.histogram.at(-1) ?? null,
    bollinger: calculateBollingerBands(closes).at(-1) ?? {
      middle: null,
      upper: null,
      lower: null,
    },
    vwap: calculateVwap(bars).at(-1) ?? null,
    volumeSpike: calculateVolumeSpike(volumes).at(latestIndex) ?? {
      ratio: null,
      isSpike: false,
    },
  };
}

export function isBsjpCandidate(
  input: ScreenerInput,
  minDailyValue = MIN_DAILY_VALUE,
): boolean {
  return Object.values(getBsjpCriteria(input, minDailyValue)).every(Boolean);
}

export function isBpjsCandidate(
  input: ScreenerInput,
  minDailyValue = MIN_DAILY_VALUE,
): boolean {
  return Object.values(getBpjsCriteria(input, minDailyValue)).every(Boolean);
}

export function screenStock(
  bars: OhlcvBar[],
  options: ScreenerOptions = {},
): ScreenerCandidate[] {
  const input = buildScreenerInput(bars);

  if (!input) {
    return [];
  }

  const minDailyValue = options.minDailyValue ?? MIN_DAILY_VALUE;
  const candidates: ScreenerCandidate[] = [];

  if (isBsjpCandidate(input, minDailyValue)) {
    candidates.push(createCandidate("BSJP", input, options));
  }

  if (isBpjsCandidate(input, minDailyValue)) {
    candidates.push(createCandidate("BPJS", input, options));
  }

  return candidates;
}

export function screenStocks(
  marketData: Record<string, OhlcvBar[]>,
  options: ScreenerOptions = {},
): ScreenerResult {
  const limit = options.limit ?? 5;
  const all = Object.values(marketData)
    .flatMap((bars) => screenStock(bars, options))
    .sort((a, b) => b.score - a.score);
  const bsjp = all
    .filter((candidate) => candidate.strategy === "BSJP")
    .slice(0, limit);
  const bpjs = all
    .filter((candidate) => candidate.strategy === "BPJS")
    .slice(0, limit);

  return {
    bsjp,
    bpjs,
    all: [...bsjp, ...bpjs].sort((a, b) => b.score - a.score),
  };
}

export function rankCandidates(
  inputs: ScreenerInput[],
  limit = 5,
): ScreenerCandidate[] {
  return inputs
    .flatMap((input) => {
      const candidates: ScreenerCandidate[] = [];

      if (isBsjpCandidate(input)) {
        candidates.push(createCandidate("BSJP", input));
      }

      if (isBpjsCandidate(input)) {
        candidates.push(createCandidate("BPJS", input));
      }

      return candidates;
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);
}

export function calculateTradeLevels(
  input: ScreenerInput,
  options: ScreenerOptions = {},
): TradeLevels {
  const entry = input.current.close;
  const atrMultiplier = options.atrMultiplier ?? DEFAULT_ATR_MULTIPLIER;
  const riskRewardRatio = options.riskRewardRatio ?? DEFAULT_RISK_REWARD_RATIO;
  const atrRisk = input.atr === null ? entry * 0.02 : input.atr * atrMultiplier;
  const riskPerShare = Math.max(atrRisk, entry * 0.005);
  const rewardPerShare = riskPerShare * riskRewardRatio;
  const stopLoss = entry - riskPerShare;
  const takeProfit = entry + rewardPerShare;

  return {
    entry,
    stopLoss,
    takeProfit,
    exit: takeProfit,
    riskPerShare,
    rewardPerShare,
  };
}

function createCandidate(
  strategy: ScreenerStrategy,
  input: ScreenerInput,
  options: ScreenerOptions = {},
): ScreenerCandidate {
  const minDailyValue = options.minDailyValue ?? MIN_DAILY_VALUE;
  const criteria =
    strategy === "BSJP"
      ? getBsjpCriteria(input, minDailyValue)
      : getBpjsCriteria(input, minDailyValue);

  return {
    ...input,
    strategy,
    criteria,
    value: calculateTradeValue(input.current.close, input.current.volume),
    score: calculateScore(input, strategy),
    levels: calculateTradeLevels(input, options),
  };
}

function getBsjpCriteria(
  input: ScreenerInput,
  minDailyValue: number,
): ScreenerCriteria {
  const { current, previous, priceMa5 } = input;
  const value = calculateTradeValue(current.close, current.volume);

  return {
    priceVsPrevious: current.close >= 1.05 * previous.close,
    priceVsMa5: current.close >= priceMa5,
    volumeVsPrevious: current.volume >= 1.2 * previous.volume,
    valueThreshold: value > minDailyValue,
  };
}

function getBpjsCriteria(
  input: ScreenerInput,
  minDailyValue: number,
): ScreenerCriteria {
  const { current, previous, priceMa5 } = input;
  const value = calculateTradeValue(current.close, current.volume);

  return {
    priceVsPrevious: current.close >= 1.05 * previous.close,
    priceVsMa5: current.close >= priceMa5,
    priceVsOpen: current.close >= current.open,
    volumeVsPrevious: current.volume >= 0.2 * previous.volume,
    valueThreshold: value > minDailyValue,
  };
}

function calculateScore(input: ScreenerInput, strategy: ScreenerStrategy): number {
  const priceMomentum = input.current.close / input.previous.close;
  const volumeMomentum = input.current.volume / Math.max(input.previous.volume, 1);
  const valueScore =
    calculateTradeValue(input.current.close, input.current.volume) / MIN_DAILY_VALUE;
  const rsiScore = input.rsi === null ? 0 : Math.min(input.rsi / 100, 1);
  const macdScore = input.macdHistogram === null ? 0 : Math.max(input.macdHistogram, 0);
  const vwapScore =
    input.vwap === null ? 0 : input.current.close / Math.max(input.vwap, 1);
  const spikeScore = input.volumeSpike.ratio ?? 0;
  const strategyWeight = strategy === "BSJP" ? 1.05 : 1;

  return (
    (priceMomentum * 2 +
      volumeMomentum +
      Math.min(valueScore, 5) +
      rsiScore +
      macdScore +
      vwapScore +
      spikeScore) *
    strategyWeight
  );
}
