"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  BPJS_RESULT_URL,
  BSJP_RESULT_URL,
  buildEquityCurve,
  fetchBacktestResult,
  fetchModelMetrics,
  formatPercent,
  formatSignedPercent,
  type BacktestResult,
  type ModelMetrics,
} from "@/lib/backtest";

type LoadedData = {
  bsjp: BacktestResult;
  bpjs: BacktestResult;
  metrics: ModelMetrics;
};

const STRATEGY_META = {
  bsjp: { label: "BSJP", color: "#34d399", hint: "Beli Sore Jual Pagi" },
  bpjs: { label: "BPJS", color: "#38bdf8", hint: "Beli Pagi Jual Sore" },
} as const;

function StatCard({
  label,
  value,
  tone = "text-white",
  hint,
}: {
  label: string;
  value: string;
  tone?: string;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.04] px-4 py-3 transition-colors hover:border-white/20 hover:bg-white/[0.06]">
      <p className="text-xs text-slate-400">{label}</p>
      <p className={`mt-1 text-xl font-semibold tabular-nums ${tone}`}>
        {value}
      </p>
      {hint ? <p className="mt-1 text-[11px] text-slate-500">{hint}</p> : null}
    </div>
  );
}

function StrategyCard({ result }: { result: BacktestResult }) {
  const meta =
    result.strategy === "BSJP" ? STRATEGY_META.bsjp : STRATEGY_META.bpjs;
  const cumulativeTone =
    result.cumulativeReturn >= 0 ? "text-emerald-300" : "text-rose-300";

  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.03] p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-white">
            {meta.label} Strategy
          </h3>
          <p className="text-xs text-slate-500">{meta.hint}</p>
        </div>
        <span
          className="rounded-full px-3 py-1 text-xs font-semibold"
          style={{ backgroundColor: `${meta.color}22`, color: meta.color }}
        >
          {result.totalTrades} trades
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatCard label="Winrate" value={formatPercent(result.winrate)} />
        <StatCard
          label="Cumulative Return"
          value={formatSignedPercent(result.cumulativeReturn)}
          tone={cumulativeTone}
        />
        <StatCard
          label="Avg Return / Trade"
          value={formatSignedPercent(result.averageReturn, 2)}
          tone={
            result.averageReturn >= 0 ? "text-emerald-300" : "text-rose-300"
          }
        />
        <StatCard
          label="Max Drawdown"
          value={formatPercent(result.maxDrawdown)}
          tone="text-rose-300"
        />
        <StatCard
          label="Periode"
          value={`${result.periodStart.slice(0, 4)}–${result.periodEnd.slice(
            0,
            4,
          )}`}
          hint={`${result.symbols.length} saham`}
        />
        <StatCard label="Total Trades" value={`${result.totalTrades}`} />
      </div>
    </section>
  );
}

function EquityChart({ data }: { data: LoadedData }) {
  const chartData = useMemo(() => {
    const bsjp = buildEquityCurve(data.bsjp.sampleTrades);
    const bpjs = buildEquityCurve(data.bpjs.sampleTrades);
    const length = Math.max(bsjp.length, bpjs.length);

    return Array.from({ length }, (_, index) => ({
      index,
      BSJP: bsjp[index]?.cumulativePct ?? null,
      BPJS: bpjs[index]?.cumulativePct ?? null,
    }));
  }, [data]);

  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.03] p-5">
      <div className="mb-1 flex items-center justify-between">
        <h3 className="text-base font-semibold text-white">
          Cumulative Return
        </h3>
        <span className="text-xs text-slate-400">% equity</span>
      </div>
      <p className="mb-4 text-xs text-slate-500">
        Equity curve dari sample trades terbaru (compounded)
      </p>

      <div className="h-80 w-full">
        <ResponsiveContainer height="100%" width="100%">
          <AreaChart
            data={chartData}
            margin={{ top: 8, right: 12, bottom: 4, left: -8 }}
          >
            <defs>
              <linearGradient id="fillBsjp" x1="0" x2="0" y1="0" y2="1">
                <stop
                  offset="0%"
                  stopColor={STRATEGY_META.bsjp.color}
                  stopOpacity={0.35}
                />
                <stop
                  offset="100%"
                  stopColor={STRATEGY_META.bsjp.color}
                  stopOpacity={0}
                />
              </linearGradient>
              <linearGradient id="fillBpjs" x1="0" x2="0" y1="0" y2="1">
                <stop
                  offset="0%"
                  stopColor={STRATEGY_META.bpjs.color}
                  stopOpacity={0.35}
                />
                <stop
                  offset="100%"
                  stopColor={STRATEGY_META.bpjs.color}
                  stopOpacity={0}
                />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#ffffff14" vertical={false} />
            <XAxis
              dataKey="index"
              stroke="#64748b"
              tick={{ fontSize: 11 }}
              tickLine={false}
            />
            <YAxis
              stroke="#64748b"
              tick={{ fontSize: 11 }}
              tickFormatter={(value: number) => `${value.toFixed(0)}%`}
              tickLine={false}
              width={48}
            />
            <Tooltip
              contentStyle={{
                background: "#0b1120",
                border: "1px solid #ffffff1a",
                borderRadius: 8,
                color: "#e2e8f0",
                fontSize: 12,
              }}
              formatter={(value) => `${Number(value).toFixed(2)}%`}
              labelFormatter={(label) => `Trade #${label}`}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Area
              connectNulls
              dataKey="BSJP"
              fill="url(#fillBsjp)"
              stroke={STRATEGY_META.bsjp.color}
              strokeWidth={2}
              type="monotone"
            />
            <Area
              connectNulls
              dataKey="BPJS"
              fill="url(#fillBpjs)"
              stroke={STRATEGY_META.bpjs.color}
              strokeWidth={2}
              type="monotone"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

function ModelCard({ metrics }: { metrics: ModelMetrics }) {
  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.03] p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-white">
            Model Statistics
          </h3>
          <p className="text-xs text-slate-500">
            {metrics.model} · target: {metrics.target}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <StatCard
          label="Accuracy"
          value={formatPercent(metrics.accuracy)}
          tone="text-sky-300"
        />
        <StatCard
          label="Precision"
          value={formatPercent(metrics.precision)}
          tone="text-amber-300"
        />
        <StatCard
          label="Recall"
          value={formatPercent(metrics.recall)}
          tone="text-violet-300"
        />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 text-xs text-slate-400 sm:grid-cols-4">
        <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2">
          <p className="text-slate-500">Train rows</p>
          <p className="mt-1 font-semibold text-slate-200 tabular-nums">
            {metrics.trainRows.toLocaleString()}
          </p>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2">
          <p className="text-slate-500">Test rows</p>
          <p className="mt-1 font-semibold text-slate-200 tabular-nums">
            {metrics.testRows.toLocaleString()}
          </p>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2">
          <p className="text-slate-500">Features</p>
          <p className="mt-1 font-semibold text-slate-200 tabular-nums">
            {metrics.features.length}
          </p>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2">
          <p className="text-slate-500">Split date</p>
          <p className="mt-1 font-semibold text-slate-200">
            {metrics.splitDate}
          </p>
        </div>
      </div>
    </section>
  );
}

export function BacktestPanel() {
  const [data, setData] = useState<LoadedData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    Promise.all([
      fetchBacktestResult(BSJP_RESULT_URL),
      fetchBacktestResult(BPJS_RESULT_URL),
      fetchModelMetrics(),
    ])
      .then(([bsjp, bpjs, metrics]) => {
        if (active) {
          setData({ bsjp, bpjs, metrics });
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

  if (error) {
    return (
      <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-6 text-sm text-rose-200">
        Gagal memuat hasil backtesting: {error}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-6">
        <div className="h-44 animate-pulse rounded-lg bg-white/[0.04]" />
        <div className="h-80 animate-pulse rounded-lg bg-white/[0.04]" />
        <div className="h-44 animate-pulse rounded-lg bg-white/[0.04]" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-2">
        <StrategyCard result={data.bsjp} />
        <StrategyCard result={data.bpjs} />
      </div>

      <EquityChart data={data} />

      <ModelCard metrics={data.metrics} />

      <p className="text-xs text-slate-500">
        Snapshot pre-computed offline (Jupyter / script). Winrate &amp; return
        tidak dihitung live — sesuai blueprint Phase 1.
      </p>
    </div>
  );
}
