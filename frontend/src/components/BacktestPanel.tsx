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
import { VCard } from "./vestigo/Card";

type LoadedData = {
  bsjp: BacktestResult;
  bpjs: BacktestResult;
  metrics: ModelMetrics;
};

const STRATEGY_META = {
  bsjp: { label: "BSJP", color: "#22c55e", hint: "Beli Sore Jual Pagi" },
  bpjs: { label: "BPJS", color: "#c19a6b", hint: "Beli Pagi Jual Sore" },
} as const;

const TOOLTIP_STYLE = {
  background: "var(--s1)",
  border: "1px solid var(--bd2)",
  borderRadius: 8,
  color: "var(--t1)",
  fontSize: 12,
} as const;

function Tile({ label, value, cls = "" }: { label: string; value: string; cls?: string }) {
  return (
    <div className="tile">
      <p className="tile-label">{label}</p>
      <p className={`tile-val mono ${cls}`}>{value}</p>
    </div>
  );
}

function StrategyCard({ result }: { result: BacktestResult }) {
  const meta = result.strategy === "BSJP" ? STRATEGY_META.bsjp : STRATEGY_META.bpjs;
  const cumCls = result.cumulativeReturn >= 0 ? "num-up" : "num-down";

  return (
    <VCard
      title={`Strategi ${meta.label}`}
      sub={meta.hint}
      subMono={false}
      right={
        <span className="badge badge-full" style={{ color: meta.color, borderColor: `${meta.color}55`, background: `${meta.color}1f` }}>
          {result.totalTrades} trades
        </span>
      }
    >
      <div className="tile-grid-3">
        <Tile label="Winrate" value={formatPercent(result.winrate)} />
        <Tile label="Cumulative return" value={formatSignedPercent(result.cumulativeReturn)} cls={cumCls} />
        <Tile
          label="Avg / trade"
          value={formatSignedPercent(result.averageReturn, 2)}
          cls={result.averageReturn >= 0 ? "num-up" : "num-down"}
        />
        <Tile label="Max drawdown" value={formatPercent(result.maxDrawdown)} cls="num-down" />
        <Tile
          label="Periode"
          value={`${result.periodStart.slice(0, 4)}-${result.periodEnd.slice(0, 4)}`}
        />
        <Tile label="Total trades" value={`${result.totalTrades}`} />
      </div>
    </VCard>
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
    <VCard title="Cumulative Return" sub="Equity curve dari sample trades terbaru (compounded)" subMono={false}>
      <div style={{ height: 320, width: "100%" }}>
        <ResponsiveContainer height="100%" width="100%">
          <AreaChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
            <defs>
              <linearGradient id="fillBsjp" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor={STRATEGY_META.bsjp.color} stopOpacity={0.35} />
                <stop offset="100%" stopColor={STRATEGY_META.bsjp.color} stopOpacity={0} />
              </linearGradient>
              <linearGradient id="fillBpjs" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor={STRATEGY_META.bpjs.color} stopOpacity={0.35} />
                <stop offset="100%" stopColor={STRATEGY_META.bpjs.color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#ffffff14" vertical={false} />
            <XAxis dataKey="index" stroke="#6b6157" tick={{ fontSize: 11 }} tickLine={false} />
            <YAxis
              stroke="#6b6157"
              tick={{ fontSize: 11 }}
              tickFormatter={(value: number) => `${value.toFixed(0)}%`}
              tickLine={false}
              width={48}
            />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              formatter={(value) => `${Number(value).toFixed(2)}%`}
              labelFormatter={(label) => `Trade #${label}`}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Area connectNulls dataKey="BSJP" fill="url(#fillBsjp)" stroke={STRATEGY_META.bsjp.color} strokeWidth={2} type="monotone" />
            <Area connectNulls dataKey="BPJS" fill="url(#fillBpjs)" stroke={STRATEGY_META.bpjs.color} strokeWidth={2} type="monotone" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </VCard>
  );
}

function ModelCard({ metrics }: { metrics: ModelMetrics }) {
  return (
    <VCard title="Model Statistics" sub={`${metrics.model} · target: ${metrics.target}`} subMono={false}>
      <div className="tile-grid-3">
        <Tile label="Accuracy" value={formatPercent(metrics.accuracy)} cls="chip-info" />
        <Tile label="Precision" value={formatPercent(metrics.precision)} cls="chip-warn" />
        <Tile label="Recall" value={formatPercent(metrics.recall)} />
        <Tile label="Train rows" value={metrics.trainRows.toLocaleString("id-ID")} />
        <Tile label="Test rows" value={metrics.testRows.toLocaleString("id-ID")} />
        <Tile label="Split date" value={metrics.splitDate} />
      </div>
      <div>
        <p className="section-label">Features ({metrics.features.length})</p>
        <div className="feat-chips">
          {metrics.features.map((f) => (
            <span key={f} className="feat-chip mono">
              {f}
            </span>
          ))}
        </div>
      </div>
      <p className="card-sub">
        Snapshot pre-computed offline. Winrate &amp; return tidak dihitung live.
      </p>
    </VCard>
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
        if (active) setData({ bsjp, bpjs, metrics });
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "Failed to load data");
      });
    return () => {
      active = false;
    };
  }, []);

  if (error) {
    return (
      <div className="empty-state" style={{ textAlign: "left" }}>
        <p style={{ color: "var(--down)", fontWeight: 500 }}>Gagal memuat hasil backtesting.</p>
        <p className="small mt">{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="card">
        <div className="skel">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skel-line" style={{ width: `${60 + (i % 3) * 14}%` }} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="grid-2">
        <StrategyCard result={data.bsjp} />
        <StrategyCard result={data.bpjs} />
      </div>

      <EquityChart data={data} />

      <ModelCard metrics={data.metrics} />
    </>
  );
}
