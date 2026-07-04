"use client";

// Explainable AI 2.0 (Phase 5) - breakdown pembentukan Composite Score.
// Input ticker -> GET /api/explain-score/{ticker}.

import { useState } from "react";
import { getExplainScore, type ExplainScoreResponse } from "@/lib/api";
import { fmtScore } from "@/lib/format";
import { useAsyncAction } from "@/lib/useAsyncAction";
import { VCard } from "../vestigo/Card";
import { CardError } from "../CardStatus";

export function ExplainScore() {
  const [ticker, setTicker] = useState("BBCA");
  const { status, data, error, run } = useAsyncAction<ExplainScoreResponse>();
  const explain = () => run(() => getExplainScore(ticker));

  return (
    <VCard
      title="Explainable AI 2.0"
      sub="Kontribusi tiap komponen Composite Score + narasi"
      subMono={false}
    >
      <form
        className="field"
        onSubmit={(e) => {
          e.preventDefault();
          explain();
        }}
      >
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          className="field-input"
          placeholder="mis. BBRI"
        />
        <button type="submit" disabled={status === "loading"} className="primary-btn">
          {status === "loading" ? "Memuat…" : "Jelaskan"}
        </button>
      </form>

      {status === "idle" && (
        <p className="empty-state">
          Uraikan kontribusi Tech / Momentum / ML terhadap Composite Score.
        </p>
      )}
      {status === "error" && <CardError message={error} onRetry={explain} />}
      {status === "ready" && (
        <>
          <div className="card-head">
            <span className="card-title">{data.ticker}</span>
            <div className="cmp-row">
              {data.overall_score != null && (
                <span className="badge badge-info badge-full">Score {data.overall_score}</span>
              )}
              {!data.ml_available && (
                <span className="small chip-warn">ML tak tersedia (bobot direnormalisasi)</span>
              )}
            </div>
          </div>

          <div className="table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Komponen</th>
                  <th className="ta-r">Skor</th>
                  <th className="ta-r">Bobot</th>
                  <th className="ta-r">Kontribusi</th>
                </tr>
              </thead>
              <tbody>
                {data.breakdown.map((c) => (
                  <tr key={c.component}>
                    <td>{c.label}</td>
                    <td className="ta-r mono">{c.score}</td>
                    <td className="ta-r mono t2">{fmtScore(c.effective_weight * 100, 0)}%</td>
                    <td className="ta-r mono chip-info">{c.contribution}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.summary && <p className="narrator narrator-sm">{data.summary}</p>}
          <p className="feature-note">
            Menjabarkan kontribusi tiap komponen (teknikal, momentum, ML) terhadap
            Composite Score saham.
          </p>
          <p className="disclaimer">{data.disclaimer}</p>
        </>
      )}
    </VCard>
  );
}
