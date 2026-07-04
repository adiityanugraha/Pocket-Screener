"use client";

// Risk Exposure per strategi (Phase 4) - profil risiko 5 strategi tervalidasi.
// GET /api/risk-profile/{s} (vol, beta, max DD, losing streak, Low/Medium/High).

import { getRiskProfile, type RiskProfileResponse } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { fmtPctFromFraction, fmtScore } from "@/lib/format";
import { TECHNICAL_STRATEGIES } from "@/lib/strategies";
import { VCard } from "../vestigo/Card";
import { CardError, CardSkeleton } from "../CardStatus";

const STRATEGIES = TECHNICAL_STRATEGIES.map((s) => s.key);

function levelTone(level: string): "up" | "warn" | "down" | "neutral" {
  if (level === "LOW") return "up";
  if (level === "MEDIUM") return "warn";
  if (level === "HIGH") return "down";
  return "neutral";
}

export function RiskExposure() {
  const { status, data, error, reload } = useApi(
    () => Promise.all(STRATEGIES.map((s) => getRiskProfile(s))),
    [],
  );

  return (
    <VCard
      title="Risk Exposure"
      sub="Profil risiko per strategi (berbeda dari Risk Meter per-saham)"
      subMono={false}
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
                  <th className="ta-r">Volatilitas</th>
                  <th className="ta-r">Beta</th>
                  <th className="ta-r">Max DD</th>
                  <th className="ta-r">Streak</th>
                  <th className="ta-r">Risiko</th>
                </tr>
              </thead>
              <tbody>
                {data.map((r: RiskProfileResponse) => (
                  <tr key={r.strategy}>
                    <td>{r.name ?? r.strategy}</td>
                    <td className="ta-r mono">{fmtScore(r.volatility * 100, 1)}%</td>
                    <td className="ta-r mono">{fmtScore(r.beta, 2)}</td>
                    <td className="ta-r mono num-down">{fmtPctFromFraction(r.max_drawdown, 1)}</td>
                    <td className="ta-r mono">{r.losing_streak}</td>
                    <td className="ta-r">
                      <span className={`badge badge-${levelTone(r.risk_level)} badge-full`}>
                        {r.risk_level}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="feature-note">
            Profil risiko tiap strategi - volatilitas, beta, max drawdown, dan losing streak.
          </p>
          <p className="disclaimer">{data[0]?.disclaimer}</p>
        </>
      )}
    </VCard>
  );
}
