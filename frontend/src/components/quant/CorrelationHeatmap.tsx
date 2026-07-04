"use client";

// Correlation Matrix (Phase 4). Korelasi return harian LQ45 dari GET /api/correlation.
// Sel: bronze = korelasi positif tinggi, abu = rendah/negatif.

import { getCorrelation } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { VCard } from "../vestigo/Card";
import { CardError, CardSkeleton } from "../CardStatus";

function cellColor(corr: number): string {
  const a = Math.min(Math.abs(corr), 1);
  return corr >= 0
    ? `rgba(193, 154, 107, ${a * 0.8})`
    : `rgba(156, 163, 175, ${a * 0.5})`;
}

export function CorrelationHeatmap() {
  const { status, data, error, reload } = useApi(() => getCorrelation("lq45", 90), []);

  return (
    <VCard
      title="Correlation Matrix"
      sub="Korelasi return harian LQ45 (90 hari) - bantu diversifikasi"
      subMono={false}
      cached={!!data?.cached}
    >
      {status === "loading" && <CardSkeleton lines={8} />}
      {status === "error" && <CardError message={error} onRetry={reload} />}
      {status === "ready" && data && (
        <>
          <div className="overflow-auto">
            <table className="border-separate border-spacing-0 text-[9px]">
              <thead>
                <tr>
                  <th
                    className="sticky left-0 z-10 p-1"
                    style={{ background: "var(--s1)" }}
                  />
                  {data.tickers.map((t) => (
                    <th key={t} className="h-16 w-5 p-0 align-bottom font-normal t3">
                      <span className="inline-block origin-bottom-left translate-y-1 rotate-[-60deg] whitespace-nowrap">
                        {t}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.tickers.map((rowTicker, i) => (
                  <tr key={rowTicker}>
                    <th
                      className="sticky left-0 z-10 pr-2 text-right font-medium mono t2"
                      style={{ background: "var(--s1)" }}
                    >
                      {rowTicker}
                    </th>
                    {data.matrix[i].map((corr, j) => (
                      <td
                        key={j}
                        className="h-5 w-5"
                        style={{
                          backgroundColor: cellColor(corr),
                          border: "1px solid var(--s1)",
                        }}
                        title={`${rowTicker} vs ${data.tickers[j]}: ${corr.toFixed(2)}`}
                      />
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div>
            <p className="section-label">Pasangan paling berkorelasi (waspadai konsentrasi)</p>
            <div className="feat-chips">
              {data.top_correlated.slice(0, 8).map((p) => (
                <span key={`${p.ticker_a}-${p.ticker_b}`} className="feat-chip mono">
                  {p.ticker_a}-{p.ticker_b} {p.correlation.toFixed(2)}
                </span>
              ))}
            </div>
          </div>
          <p className="feature-note">
            Seberapa seragam pergerakan saham LQ45 - bantu hindari konsentrasi risiko.
          </p>
          <p className="disclaimer">{data.disclaimer}</p>
        </>
      )}
    </VCard>
  );
}
