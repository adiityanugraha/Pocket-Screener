"use client";

// AI Daily Report (Phase 5) - laporan harian + ekspor PDF/Markdown (Pro).
// GET /api/daily-report (auto-load); download via format=pdf|markdown.

import { dailyReportUrl, getDailyReport } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { fmtScore } from "@/lib/format";
import { useMode } from "../ModeProvider";
import { VCard } from "../vestigo/Card";
import { CardError, CardSkeleton } from "../CardStatus";

export function DailyReport() {
  const { pro } = useMode();
  const state = useApi(getDailyReport, []);

  const downloads = pro ? (
    <div className="chart-ctrls">
      <a
        href={dailyReportUrl("markdown")}
        target="_blank"
        rel="noopener noreferrer"
        className="ghost-btn"
      >
        Markdown
      </a>
      <a
        href={dailyReportUrl("pdf")}
        target="_blank"
        rel="noopener noreferrer"
        className="ghost-btn ghost-on"
      >
        Unduh PDF
      </a>
    </div>
  ) : null;

  return (
    <VCard
      title="AI Daily Report"
      sub="Top opportunities, sektor & peringatan risiko"
      subMono={false}
      cached={state.status === "ready" && state.data.cached}
      right={downloads}
    >
      {state.status === "loading" && <CardSkeleton lines={6} />}
      {state.status === "error" && <CardError message={state.error} onRetry={state.reload} />}
      {state.status === "ready" && (
        <>
          {state.data.date && <p className="card-sub mono">{state.data.date}</p>}
          {state.data.overview && <p className="narrator narrator-sm">{state.data.overview}</p>}

          <div className="grid-2">
            <div>
              <p className="section-label">Top opportunities</p>
              <ul className="report-list">
                {state.data.top_opportunities.map((o) => (
                  <li key={o.ticker} className="between">
                    <span className="mini-sym">{o.ticker}</span>
                    <span className="mono badge badge-info">{fmtScore(o.overall_score)}</span>
                  </li>
                ))}
                {state.data.top_opportunities.length === 0 && <li className="t3">-</li>}
              </ul>
            </div>

            <div>
              <p className="section-label">High confidence</p>
              {state.data.high_confidence.length > 0 ? (
                <ul className="report-list">
                  {state.data.high_confidence.map((h) => (
                    <li key={h.ticker} className="between">
                      <span className="mini-sym">{h.ticker}</span>
                      <span className="mono num-up">
                        {h.prob_5d != null ? `${fmtScore(h.prob_5d * 100, 0)}%` : "-"}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="empty-state">Tidak ada saham high-confidence.</p>
              )}
            </div>
          </div>

          <div className="factor-list" style={{ fontSize: 12 }}>
            <span>
              Sektor terkuat: <span className="num-up">{state.data.strongest_sector ?? "-"}</span>
            </span>
            <span>
              Sektor terlemah: <span className="num-down">{state.data.weakest_sector ?? "-"}</span>
            </span>
          </div>

          {state.data.risk_warnings.length > 0 && (
            <div>
              <p className="section-label">Risk warning</p>
              <ul className="factor-list">
                {state.data.risk_warnings.map((w) => (
                  <li key={w.ticker}>
                    <span className="fi fi-down">!</span>
                    {w.ticker}: risiko {w.risk} (skor {w.score ?? "-"})
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className="feature-note">
            Ringkasan harian: saham skor teratas, sektor terkuat/terlemah, dan peringatan risiko.
          </p>
          <p className="disclaimer">{state.data.disclaimer}</p>
        </>
      )}
    </VCard>
  );
}
