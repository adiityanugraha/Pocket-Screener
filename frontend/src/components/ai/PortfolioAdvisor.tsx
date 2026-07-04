"use client";

// Portfolio AI Advisor (Phase 5) - alokasi (Phase 4) + penjelasan AI.
// POST /api/portfolio-advisor.

import { useState } from "react";
import { postPortfolioAdvisor, type PortfolioAdvisorResponse } from "@/lib/api";
import { fmtScore, fmtValue } from "@/lib/format";
import { useAsyncAction } from "@/lib/useAsyncAction";
import { RiskCapitalForm } from "../RiskCapitalForm";
import { VCard } from "../vestigo/Card";
import { CardError } from "../CardStatus";

function levelClass(level: string | null | undefined): string {
  if (level === "LOW") return "num-up";
  if (level === "HIGH") return "num-down";
  if (level === "MEDIUM") return "chip-warn";
  return "t2";
}

export function PortfolioAdvisor() {
  const [risk, setRisk] = useState("MODERATE");
  const [capital, setCapital] = useState(100_000_000);
  const { status, data, error, run } = useAsyncAction<PortfolioAdvisorResponse>();
  const advise = () => run(() => postPortfolioAdvisor({ risk, capital, universe: "lq45" }));

  return (
    <VCard
      title="Portfolio AI Advisor"
      sub="Alokasi sesuai profil risiko + penjelasan AI tiap bobot"
      subMono={false}
    >
      <RiskCapitalForm
        risk={risk}
        setRisk={setRisk}
        capital={capital}
        setCapital={setCapital}
        onSubmit={advise}
        loading={status === "loading"}
        submitLabel="Sarankan Portofolio"
      />

      {status === "error" && <CardError message={error} onRetry={advise} />}
      {status === "ready" && (
        <>
          <div className="table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Saham</th>
                  <th className="ta-r">Bobot</th>
                  <th className="ta-r">Alokasi</th>
                  <th className="ta-r">Risiko</th>
                </tr>
              </thead>
              <tbody>
                {data.allocations.map((a) => (
                  <tr key={a.ticker}>
                    <td>
                      <span className="tk-pill">{a.ticker}</span>
                    </td>
                    <td className="ta-r mono chip-info">{fmtScore(a.weight * 100, 1)}%</td>
                    <td className="ta-r mono">{a.amount != null ? fmtValue(a.amount) : "-"}</td>
                    <td className={`ta-r mono ${levelClass(a.risk_level)}`}>
                      {a.risk_level ?? "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.explanation && (
            <p className="narrator narrator-sm">{data.explanation}</p>
          )}
          <p className="feature-note">
            Saran alokasi portofolio sesuai profil risiko Anda, beserta alasan tiap bobot.
          </p>
          <p className="disclaimer">{data.disclaimer}</p>
        </>
      )}
    </VCard>
  );
}
