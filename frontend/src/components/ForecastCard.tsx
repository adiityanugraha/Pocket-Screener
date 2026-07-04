"use client";

// Probability Forecast card (Phase 3).
// P(return > 0) untuk 1D / 5D / 20D dari GET /api/forecast/{ticker} + confidence
// + disclaimer (wajib tampil - alat bantu, bukan rekomendasi).

import { getForecast, type ForecastResponse } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { fmtScore } from "@/lib/format";
import { VCard } from "./vestigo/Card";
import { CardError, CardSkeleton } from "./CardStatus";

const HORIZON_LABELS: Array<{ key: keyof ForecastResponse["prob"]; label: string }> = [
  { key: "1d", label: "1 hari" },
  { key: "5d", label: "5 hari" },
  { key: "20d", label: "20 hari" },
];

function confidenceTone(confidence: string): "up" | "warn" | "neutral" {
  if (confidence === "HIGH") return "up";
  if (confidence === "MEDIUM") return "warn";
  return "neutral";
}

function probFill(p: number): string {
  if (p >= 0.5) return "var(--up)";
  if (p >= 0.45) return "var(--warn)";
  return "var(--down)";
}

/** A horizontal probability bar (0..100% of the track). */
function ProbRow({ label, value }: { label: string; value: number }) {
  const pct = value * 100;
  return (
    <div className="fc-row">
      <span className="fc-label">{label}</span>
      <div className="fc-track">
        <div
          className="fc-fill"
          style={{ width: `${Math.min(pct, 100)}%`, background: probFill(value) }}
        />
      </div>
      <span className="fc-val mono">{fmtScore(pct, 0)}%</span>
    </div>
  );
}

export function ForecastCard({ symbol }: { symbol: string }) {
  const { status, data, error, reload } = useApi(() => getForecast(symbol), [symbol]);

  return (
    <VCard
      title="Probability Forecast"
      sub={`Probabilitas return positif · ${data?.ticker ?? symbol}`}
      subMono={false}
      cached={!!data?.cached}
      right={
        data ? (
          <span className={`badge badge-${confidenceTone(data.confidence)} badge-full`}>
            {data.confidence}
          </span>
        ) : undefined
      }
    >
      {status === "loading" && <CardSkeleton lines={5} />}
      {status === "error" && <CardError message={error} onRetry={reload} />}
      {status === "ready" && data && (
        <>
          <div className="fc-list">
            {HORIZON_LABELS.map(({ key, label }) => (
              <ProbRow key={key} label={label} value={data.prob[key]} />
            ))}
          </div>
          <p className="feature-note">
            Peluang harga ditutup naik pada tiap horizon menurut model ML - di atas
            50% condong menguat.
          </p>
          <p className="disclaimer">{data.disclaimer}</p>
        </>
      )}
    </VCard>
  );
}
