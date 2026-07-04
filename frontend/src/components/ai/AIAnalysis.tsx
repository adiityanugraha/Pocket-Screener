"use client";

// AI Analyst (Phase 5) - narasi AI ter-grounding per saham.
// Input ticker -> GET /api/ai-analysis/{ticker}.

import { useState } from "react";
import { getAiAnalysis, type AiAnalysisResponse } from "@/lib/api";
import { useAsyncAction } from "@/lib/useAsyncAction";
import { VCard } from "../vestigo/Card";
import { CardError } from "../CardStatus";

export function AIAnalysis() {
  const [ticker, setTicker] = useState("BBCA");
  const { status, data, error, run } = useAsyncAction<AiAnalysisResponse>();
  const analyze = () => run(() => getAiAnalysis(ticker));

  return (
    <VCard
      title="AI Analyst per-saham"
      sub="Ringkasan + faktor - angka dari sistem, dinarasikan AI"
      subMono={false}
    >
      <form
        className="field"
        onSubmit={(e) => {
          e.preventDefault();
          analyze();
        }}
      >
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          className="field-input"
          placeholder="mis. BBCA"
        />
        <button type="submit" disabled={status === "loading"} className="primary-btn">
          {status === "loading" ? "Menganalisis…" : "Analisis"}
        </button>
      </form>

      {status === "idle" && (
        <p className="empty-state">Masukkan ticker untuk analisis teknikal + naratif.</p>
      )}
      {status === "error" && <CardError message={error} onRetry={analyze} />}
      {status === "ready" && (
        <>
          <div className="card-head">
            <span className="card-title">{data.ticker}</span>
            <div className="cmp-row">
              {data.confidence != null && (
                <span className="badge badge-info badge-full">Confidence {data.confidence}</span>
              )}
              {data.date && <span className="t3 small mono">{data.date}</span>}
            </div>
          </div>
          {data.summary && <p className="narrator narrator-sm">{data.summary}</p>}
          {data.note && <p className="small chip-warn">{data.note}</p>}

          {data.bullish_factors.length > 0 && (
            <div>
              <p className="section-label">Faktor bullish</p>
              <ul className="factor-list">
                {data.bullish_factors.map((f, i) => (
                  <li key={i}>
                    <span className="fi fi-up">↑</span>
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {data.risk_factors.length > 0 && (
            <div>
              <p className="section-label">Faktor risiko</p>
              <ul className="factor-list">
                {data.risk_factors.map((f, i) => (
                  <li key={i}>
                    <span className="fi fi-down">!</span>
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="feature-note">
            Analisis satu saham - ringkasan, faktor bullish & risiko - dengan confidence
            dari Composite Score sistem.
          </p>
          <p className="disclaimer">{data.disclaimer}</p>
        </>
      )}
    </VCard>
  );
}
