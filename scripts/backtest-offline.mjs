import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  buildScreenerInput,
  isBpjsCandidate,
  isBsjpCandidate,
} from "../src/lib/screener.ts";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DATA_DIR = path.join(ROOT, "data");
const BACKTESTING_DIR = path.join(ROOT, "public", "backtesting");
const CSV_PATH = path.join(DATA_DIR, "historical_daily.csv");
const BSJP_JSON_PATH = path.join(BACKTESTING_DIR, "bsjp_result.json");
const BPJS_JSON_PATH = path.join(BACKTESTING_DIR, "bpjs_result.json");

const SYMBOLS = [
  "BBCA",
  "BBRI",
  "BMRI",
  "TLKM",
  "ASII",
  "UNVR",
  "ICBP",
  "INDF",
  "ANTM",
  "MDKA",
  "ADRO",
  "PGAS",
  "BRIS",
  "CPIN",
  "INCO",
];

const CSV_COLUMNS = ["symbol", "date", "open", "high", "low", "close", "volume"];

await mkdir(DATA_DIR, { recursive: true });
await mkdir(BACKTESTING_DIR, { recursive: true });

const groupedBars = {};

for (const symbol of SYMBOLS) {
  const yahooSymbol = `${symbol}.JK`;
  const bars = await fetchYahooBars(yahooSymbol);

  groupedBars[yahooSymbol] = bars;
  console.log(`${yahooSymbol}: ${bars.length} bars`);
}

const allBars = Object.values(groupedBars)
  .flat()
  .sort((a, b) => a.symbol.localeCompare(b.symbol) || a.date.localeCompare(b.date));

await writeFile(CSV_PATH, toCsv(allBars));

const generatedAt = new Date().toISOString();
const bsjpResult = runBacktest("BSJP", groupedBars, generatedAt);
const bpjsResult = runBacktest("BPJS", groupedBars, generatedAt);

await writeFile(BSJP_JSON_PATH, `${JSON.stringify(bsjpResult, null, 2)}\n`);
await writeFile(BPJS_JSON_PATH, `${JSON.stringify(bpjsResult, null, 2)}\n`);

console.log(`CSV saved: ${path.relative(ROOT, CSV_PATH)} (${allBars.length} rows)`);
console.log(`BSJP trades: ${bsjpResult.totalTrades}`);
console.log(`BPJS trades: ${bpjsResult.totalTrades}`);

async function fetchYahooBars(symbol) {
  const url = new URL(
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}`,
  );
  url.searchParams.set("range", "5y");
  url.searchParams.set("interval", "1d");
  url.searchParams.set("includePrePost", "false");
  url.searchParams.set("events", "history");

  const response = await fetch(url, {
    headers: {
      accept: "application/json",
      "user-agent": "PocketScreener/1.0",
    },
  });

  if (!response.ok) {
    throw new Error(`Yahoo request failed for ${symbol}: HTTP ${response.status}`);
  }

  const payload = await response.json();
  const result = payload.chart?.result?.[0];
  const timestamps = result?.timestamp ?? [];
  const quote = result?.indicators?.quote?.[0];

  if (!quote) {
    return [];
  }

  return timestamps.flatMap((timestamp, index) => {
    const open = quote.open?.[index];
    const high = quote.high?.[index];
    const low = quote.low?.[index];
    const close = quote.close?.[index];
    const volume = quote.volume?.[index];

    if (![open, high, low, close, volume].every(isFiniteNumber)) {
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

function runBacktest(strategy, marketData, generatedAt) {
  const trades = [];

  for (const [symbol, bars] of Object.entries(marketData)) {
    for (let index = 30; index < bars.length; index += 1) {
      const history = bars.slice(0, index + 1);
      const input = buildScreenerInput(history);

      if (!input) {
        continue;
      }

      if (strategy === "BSJP" && !isBsjpCandidate(input)) {
        continue;
      }

      if (strategy === "BPJS" && !isBpjsCandidate(input)) {
        continue;
      }

      const nextBar = bars[index + 1];
      const entry = strategy === "BSJP" ? input.current.close : nextBar?.open;
      const exit = strategy === "BSJP" ? nextBar?.open : nextBar?.close;

      if (!isFiniteNumber(entry) || !isFiniteNumber(exit) || entry <= 0) {
        continue;
      }

      const returnPct = exit / entry - 1;

      trades.push({
        symbol,
        signalDate: input.current.date,
        entry,
        exit,
        returnPct,
        win: returnPct > 0,
      });
    }
  }

  trades.sort((a, b) => a.signalDate.localeCompare(b.signalDate));

  const returns = trades.map((trade) => trade.returnPct);
  const equityCurve = buildEquityCurve(returns);
  const winrate =
    trades.length === 0
      ? null
      : trades.filter((trade) => trade.win).length / trades.length;
  const cumulativeReturn =
    equityCurve.length === 0 ? null : equityCurve[equityCurve.length - 1] - 1;

  return {
    strategy,
    generatedAt,
    source: "Yahoo Finance chart API",
    symbols: Object.keys(marketData),
    periodStart: getPeriodBoundary(marketData, "start"),
    periodEnd: getPeriodBoundary(marketData, "end"),
    totalTrades: trades.length,
    winrate,
    cumulativeReturn,
    averageReturn:
      returns.length === 0
        ? null
        : returns.reduce((sum, value) => sum + value, 0) / returns.length,
    maxDrawdown: calculateMaxDrawdown(equityCurve),
    assumptions:
      strategy === "BSJP"
        ? "Signal uses daily close; return uses next trading day's open divided by signal close."
        : "Signal uses daily close; return uses next trading day's close divided by next trading day's open.",
    sampleTrades: trades.slice(-50),
  };
}

function buildEquityCurve(returns) {
  const equityCurve = [];
  let equity = 1;

  for (const value of returns) {
    equity *= 1 + value;
    equityCurve.push(equity);
  }

  return equityCurve;
}

function calculateMaxDrawdown(equityCurve) {
  if (equityCurve.length === 0) {
    return null;
  }

  let peak = equityCurve[0];
  let maxDrawdown = 0;

  for (const equity of equityCurve) {
    peak = Math.max(peak, equity);
    maxDrawdown = Math.min(maxDrawdown, equity / peak - 1);
  }

  return maxDrawdown;
}

function getPeriodBoundary(marketData, boundary) {
  const dates = Object.values(marketData)
    .flat()
    .map((bar) => bar.date)
    .sort();

  return boundary === "start" ? dates[0] : dates.at(-1);
}

function toCsv(rows) {
  const lines = [
    CSV_COLUMNS.join(","),
    ...rows.map((row) => CSV_COLUMNS.map((column) => row[column]).join(",")),
  ];

  return `${lines.join("\n")}\n`;
}

function isFiniteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}
