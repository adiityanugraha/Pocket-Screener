"use client";

import type { CSSProperties } from "react";
import { getMarketBreadth, type Mover } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { fmtPctFromFraction, fmtScore } from "@/lib/format";
import { VCard } from "./vestigo/Card";
import { CardError, CardSkeleton } from "./CardStatus";

/** Heat tint from an average sector change (fraction, e.g. 0.012 = +1.2%). */
function heatStyle(fraction: number): CSSProperties {
  const chg = fraction * 100; // percent points
  const a = Math.min(0.32, 0.06 + Math.abs(chg) * 0.05);
  if (chg > 0.05)
    return {
      background: `rgba(34,197,94,${a})`,
      color: "var(--up)",
      borderColor: "rgba(34,197,94,0.25)",
    };
  if (chg < -0.05)
    return {
      background: `rgba(239,68,68,${a})`,
      color: "var(--down)",
      borderColor: "rgba(239,68,68,0.25)",
    };
  return { background: "var(--s2)", color: "var(--t2)" };
}

function MoverList({ title, movers }: { title: string; movers: Mover[] }) {
  return (
    <div>
      <p className="section-label">{title}</p>
      <ul className="report-list">
        {movers.length === 0 && <li className="t3">-</li>}
        {movers.map((m) => {
          const dir = m.change_pct > 0 ? "num-up" : m.change_pct < 0 ? "num-down" : "";
          return (
            <li key={m.ticker} className="between">
              <span className="mini-sym">{m.ticker}</span>
              <span className={`mono ${dir}`}>{fmtPctFromFraction(m.change_pct, 2)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function MarketBreadthCard() {
  const { status, data, error, reload } = useApi(() => getMarketBreadth(), []);

  return (
    <VCard
      title="Market Breadth"
      sub="Kesehatan pasar keseluruhan"
      subMono={false}
      cached={!!data?.cached}
      right={<span className="t3 mono small">{data?.date ?? "IDX"}</span>}
    >
      {status === "loading" && <CardSkeleton lines={6} />}
      {status === "error" && <CardError message={error} onRetry={reload} />}
      {status === "ready" && data && (
        <>
          <div className="tile-grid-3">
            <div className="tile">
              <p className="tile-label">Naik</p>
              <p className="big-num mono num-up">{data.advancers}</p>
            </div>
            <div className="tile">
              <p className="tile-label">Turun</p>
              <p className="big-num mono num-down">{data.decliners}</p>
            </div>
            <div className="tile">
              <p className="tile-label">Bullish ratio</p>
              <p className="big-num mono">
                {data.bullish_ratio === null
                  ? "-"
                  : `${fmtScore(data.bullish_ratio * 100, 0)}%`}
              </p>
            </div>
          </div>

          <div className="grid-2">
            <MoverList title="Top gainers" movers={data.top_gainers} />
            <MoverList title="Top losers" movers={data.top_losers} />
          </div>

          <div>
            <p className="section-label">Performa sektor</p>
            <div className="heatgrid">
              {data.sector_performance.map((s) => (
                <div
                  key={s.sector}
                  className="heatcell"
                  style={heatStyle(s.avg_change_pct)}
                  title={`${s.count} saham`}
                >
                  <span className="heatcell-name">{s.sector}</span>
                  <span className="mono heatcell-pct">
                    {fmtPctFromFraction(s.avg_change_pct, 1)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </VCard>
  );
}
