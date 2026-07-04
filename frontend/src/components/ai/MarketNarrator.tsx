"use client";

// Market Narrator (Phase 5) - ringkasan kondisi pasar harian.
// GET /api/market-summary (auto-load).

import { getMarketSummary } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { fmtScore } from "@/lib/format";
import { VCard } from "../vestigo/Card";
import { CardError, CardSkeleton } from "../CardStatus";

export function MarketNarrator() {
  const state = useApi(getMarketSummary, []);

  return (
    <VCard
      title="Market Narrator"
      sub="Ringkasan pasar: breadth, rotasi sektor & strategi terbaik"
      subMono={false}
      cached={state.status === "ready" && state.data.cached}
    >
      {state.status === "loading" && <CardSkeleton />}
      {state.status === "error" && <CardError message={state.error} onRetry={state.reload} />}
      {state.status === "ready" && (
        <>
          {state.data.summary && <p className="narrator">{state.data.summary}</p>}

          <div className="tile-grid-3">
            <div className="tile">
              <p className="tile-label">Bullish ratio</p>
              <p className="tile-val mono">
                {state.data.bullish_ratio != null
                  ? `${fmtScore(state.data.bullish_ratio * 100, 0)}%`
                  : "-"}
              </p>
            </div>
            <div className="tile">
              <p className="tile-label">Naik / Turun</p>
              <p className="tile-val mono">
                <span className="num-up">{state.data.advancers ?? "-"}</span>
                <span className="t3"> / </span>
                <span className="num-down">{state.data.decliners ?? "-"}</span>
              </p>
            </div>
            <div className="tile">
              <p className="tile-label">Strategi terbaik</p>
              <p className="tile-val">{state.data.best_strategy ?? "-"}</p>
            </div>
          </div>

          <div className="factor-list" style={{ fontSize: 12 }}>
            <span>
              Sektor leading: <span className="num-up">{state.data.leading_sectors.join(", ") || "-"}</span>
            </span>
            <span>
              Sektor lagging: <span className="num-down">{state.data.lagging_sectors.join(", ") || "-"}</span>
            </span>
          </div>

          <p className="feature-note">
            Rangkuman arah pasar IDX hari ini dari breadth, rotasi sektor, dan strategi terbaik.
          </p>
          <p className="disclaimer">{state.data.disclaimer}</p>
        </>
      )}
    </VCard>
  );
}
