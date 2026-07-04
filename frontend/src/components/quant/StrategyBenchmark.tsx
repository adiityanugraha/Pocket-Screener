"use client";

// Strategy Benchmark (Phase 4) - metrik seluruh strategi tervalidasi + IHSG.
// GET /api/benchmark. Menandai strategi yang mengalahkan pasar.

import { getBenchmark, type BenchmarkRow } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { fmtPctFromFraction, fmtScore } from "@/lib/format";
import { VCard } from "../vestigo/Card";
import { CardError, CardSkeleton } from "../CardStatus";

function pctClass(value: number): string {
  if (value > 0) return "num-up";
  if (value < 0) return "num-down";
  return "";
}

function Row({ row, market }: { row: BenchmarkRow; market: boolean }) {
  const m = row.metrics;
  return (
    <tr style={market ? { background: "var(--s2)", fontWeight: 500 } : undefined}>
      <td>
        <span>{row.name ?? row.strategy}</span>
        {!market && row.beats_market_cagr === true && <span className="beat-badge">&gt; pasar</span>}
      </td>
      <td className={`ta-r mono ${pctClass(m.cagr)}`}>{fmtPctFromFraction(m.cagr, 1)}</td>
      <td className="ta-r mono">{fmtScore(m.winrate * 100, 0)}%</td>
      <td className="ta-r mono">{fmtScore(m.sharpe_ratio, 2)}</td>
      <td className="ta-r mono num-down">{fmtPctFromFraction(m.max_drawdown, 1)}</td>
      <td className="ta-r mono">{fmtScore(m.profit_factor, 2)}</td>
    </tr>
  );
}

export function StrategyBenchmark() {
  const { status, data, error, reload } = useApi(() => getBenchmark(), []);

  return (
    <VCard
      title="Strategy Benchmark"
      sub="5 strategi teknikal vs IHSG (buy & hold) - apakah mengalahkan pasar?"
      subMono={false}
      cached={!!data?.cached}
    >
      {status === "loading" && <CardSkeleton lines={6} />}
      {status === "error" && <CardError message={error} onRetry={reload} />}
      {status === "ready" && data && (
        <>
          <div className="table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Strategi</th>
                  <th className="ta-r">CAGR</th>
                  <th className="ta-r">Winrate</th>
                  <th className="ta-r">Sharpe</th>
                  <th className="ta-r">Max DD</th>
                  <th className="ta-r">PF</th>
                </tr>
              </thead>
              <tbody>
                {data.strategies.map((row) => (
                  <Row key={row.strategy} row={row} market={false} />
                ))}
                <Row row={data.market} market />
              </tbody>
            </table>
          </div>
          <p className="feature-note">
            Membandingkan performa 5 strategi teknikal terhadap IHSG selama ~5 tahun.
          </p>
          <p className="disclaimer">{data.disclaimer}</p>
        </>
      )}
    </VCard>
  );
}
