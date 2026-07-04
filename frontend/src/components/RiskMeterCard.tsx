"use client";

import { getRisk } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { fmtScore } from "@/lib/format";
import { useMode } from "./ModeProvider";
import { VCard } from "./vestigo/Card";
import { CardError, CardSkeleton } from "./CardStatus";

function riskTone(risk: string): "up" | "down" | "warn" {
  if (risk === "LOW") return "up";
  if (risk === "HIGH") return "down";
  return "warn";
}

function riskFill(risk: string): string {
  if (risk === "LOW") return "var(--up)";
  if (risk === "HIGH") return "var(--down)";
  return "var(--warn)";
}

/** Fractions from the API (0.221) → "22,1%". */
function pct(value: number | null): string {
  return value === null ? "-" : `${fmtScore(value * 100, 1)}%`;
}

export function RiskMeterCard({ symbol }: { symbol: string }) {
  const { pro } = useMode();
  const { status, data, error, reload } = useApi(() => getRisk(symbol), [symbol]);

  return (
    <VCard title="Risk Meter" sub={symbol} cached={!!data?.cached}>
      {status === "loading" && <CardSkeleton lines={4} />}
      {status === "error" && <CardError message={error} onRetry={reload} />}
      {status === "ready" && data && (
        <>
          <div className="verdict-top">
            <span className={`badge badge-${riskTone(data.risk)} badge-full`}>
              {data.risk} RISK
            </span>
            <div className="ta-r">
              <p className="tile-label">Risk Score</p>
              <p className="big-num mono">{data.score}</p>
            </div>
          </div>

          <div className="riskbar">
            <div
              className="riskbar-fill"
              style={{ width: `${data.score}%`, background: riskFill(data.risk) }}
            />
          </div>

          {pro && (
            <div className="tile-grid-4">
              <div className="tile">
                <p className="tile-label">Volatilitas (th)</p>
                <p className="tile-val mono">{pct(data.breakdown.historical_volatility)}</p>
              </div>
              <div className="tile">
                <p className="tile-label">ATR%</p>
                <p className="tile-val mono">{pct(data.breakdown.atr_pct)}</p>
              </div>
              <div className="tile">
                <p className="tile-label">Max Drawdown</p>
                <p className="tile-val mono num-down">{pct(data.breakdown.max_drawdown)}</p>
              </div>
              <div className="tile">
                <p className="tile-label">Beta</p>
                <p className="tile-val mono">
                  {data.breakdown.beta === null ? "-" : fmtScore(data.breakdown.beta, 2)}
                </p>
              </div>
            </div>
          )}
        </>
      )}
    </VCard>
  );
}
