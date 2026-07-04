"use client";

// AI Strategy Comparator (Phase 5) - bandingkan 2 strategi teknikal.
// GET /api/compare-strategy?a=&b=. Hanya 5 strategi teknikal tervalidasi.

import { useState } from "react";
import { getCompareStrategy, type CompareStrategyResponse } from "@/lib/api";
import { TECHNICAL_STRATEGIES } from "@/lib/strategies";
import { useAsyncAction } from "@/lib/useAsyncAction";
import { VCard } from "../vestigo/Card";
import { CardError } from "../CardStatus";

const METRIC_LABELS: Record<string, string> = {
  cagr: "CAGR",
  sharpe_ratio: "Sharpe",
  sortino_ratio: "Sortino",
  calmar_ratio: "Calmar",
  max_drawdown: "Max Drawdown",
  winrate: "Winrate",
  profit_factor: "Profit Factor",
  recovery_factor: "Recovery Factor",
};

function metricKeys(d: CompareStrategyResponse): string[] {
  return Array.from(new Set([...Object.keys(d.metrics_a), ...Object.keys(d.metrics_b)]));
}

export function StrategyComparator() {
  const [a, setA] = useState("breakout");
  const [b, setB] = useState("trend_following");
  const { status, data, error, run } = useAsyncAction<CompareStrategyResponse>();
  const compare = () => run(() => getCompareStrategy(a, b));

  return (
    <VCard
      title="AI Strategy Comparator"
      sub="Bandingkan dua strategi teknikal (metrik historis) + narasi tradeoff"
      subMono={false}
    >
      <form
        className="cmp-row"
        onSubmit={(e) => {
          e.preventDefault();
          compare();
        }}
      >
        <select value={a} onChange={(e) => setA(e.target.value)} className="select">
          {TECHNICAL_STRATEGIES.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </select>
        <span className="t3">vs</span>
        <select value={b} onChange={(e) => setB(e.target.value)} className="select">
          {TECHNICAL_STRATEGIES.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </select>
        <button type="submit" disabled={status === "loading"} className="primary-btn">
          {status === "loading" ? "Membandingkan…" : "Bandingkan"}
        </button>
      </form>

      {status === "error" && <CardError message={error} onRetry={compare} />}
      {status === "ready" && (
        <>
          <div className="table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Metrik</th>
                  <th className="ta-r">{data.strategy_a}</th>
                  <th className="ta-r">{data.strategy_b}</th>
                </tr>
              </thead>
              <tbody>
                {metricKeys(data).map((k) => (
                  <tr key={k}>
                    <td className="t2">{METRIC_LABELS[k] ?? k}</td>
                    <td className="ta-r mono">{data.metrics_a[k] ?? "-"}</td>
                    <td className="ta-r mono">{data.metrics_b[k] ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.comparison && <p className="narrator narrator-sm">{data.comparison}</p>}
          <p className="feature-note">
            Membandingkan metrik historis dua strategi teknikal untuk melihat tradeoff
            imbal hasil & risiko.
          </p>
          <p className="disclaimer">{data.disclaimer}</p>
        </>
      )}
    </VCard>
  );
}
