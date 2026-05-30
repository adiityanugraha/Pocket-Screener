"use client";

import { useEffect, useState } from "react";
import {
  BSJP_RESULT_URL,
  fetchBacktestResult,
  type SampleTrade,
} from "@/lib/backtest";
import { getSector, SECTORS, type Sector } from "@/lib/sectors";

type SectorCell = {
  sector: Sector;
  avgReturn: number; // fraction, e.g. 0.012 = +1.2%
  symbols: number;
  trades: number;
};

function aggregateBySector(trades: SampleTrade[]): SectorCell[] {
  const bySector = new Map<
    Sector,
    { sum: number; trades: number; symbols: Set<string> }
  >();

  for (const trade of trades) {
    const sector = getSector(trade.symbol);
    if (!sector) {
      continue;
    }

    const bucket =
      bySector.get(sector) ?? { sum: 0, trades: 0, symbols: new Set() };
    bucket.sum += trade.returnPct;
    bucket.trades += 1;
    bucket.symbols.add(trade.symbol);
    bySector.set(sector, bucket);
  }

  return SECTORS.map((sector) => {
    const bucket = bySector.get(sector);
    return {
      sector,
      avgReturn: bucket && bucket.trades > 0 ? bucket.sum / bucket.trades : 0,
      symbols: bucket ? bucket.symbols.size : 0,
      trades: bucket ? bucket.trades : 0,
    };
  });
}

// Map an average return to a dark-mode friendly heat tone.
function toneFor(avgReturn: number, hasData: boolean): string {
  if (!hasData) {
    return "bg-white/[0.04] text-slate-500";
  }

  if (avgReturn >= 0.015) return "bg-emerald-500/85 text-slate-950";
  if (avgReturn >= 0.005) return "bg-emerald-500/55 text-slate-950";
  if (avgReturn > 0) return "bg-emerald-500/30 text-emerald-50";
  if (avgReturn === 0) return "bg-slate-500/30 text-slate-100";
  if (avgReturn > -0.005) return "bg-rose-500/30 text-rose-50";
  if (avgReturn > -0.015) return "bg-rose-500/55 text-slate-950";
  return "bg-rose-500/85 text-slate-950";
}

function formatSigned(avgReturn: number): string {
  const pct = (avgReturn * 100).toFixed(2);
  return avgReturn > 0 ? `+${pct}%` : `${pct}%`;
}

export function Heatmap() {
  const [cells, setCells] = useState<SectorCell[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    fetchBacktestResult(BSJP_RESULT_URL)
      .then((result) => {
        if (active) {
          setCells(aggregateBySector(result.sampleTrades));
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load data");
        }
      });

    return () => {
      active = false;
    };
  }, []);

  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.03] p-5">
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-base font-semibold text-white">Sector Heatmap</h2>
        <span className="text-xs font-medium text-slate-400">IDX</span>
      </div>
      <p className="mb-4 text-xs text-slate-500">
        Rata-rata return per sektor (BSJP backtest sample)
      </p>

      {error ? (
        <div className="flex h-72 items-center justify-center rounded-lg border border-rose-500/30 bg-rose-500/10 p-4 text-center text-sm text-rose-200">
          {error}
        </div>
      ) : !cells ? (
        <div className="grid h-72 grid-cols-2 gap-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div
              className="animate-pulse rounded-lg bg-white/[0.05]"
              key={index}
            />
          ))}
        </div>
      ) : (
        <div className="grid h-72 grid-cols-2 gap-3">
          {cells.map((cell) => {
            const hasData = cell.trades > 0;
            return (
              <div
                className={`flex flex-col justify-between rounded-lg p-4 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/30 ${toneFor(
                  cell.avgReturn,
                  hasData,
                )}`}
                key={cell.sector}
              >
                <div className="flex items-start justify-between">
                  <span className="text-sm font-semibold">{cell.sector}</span>
                  <span className="text-[11px] font-medium opacity-80">
                    {cell.symbols} saham
                  </span>
                </div>
                <span className="text-lg font-bold tabular-nums">
                  {hasData ? formatSigned(cell.avgReturn) : "—"}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
