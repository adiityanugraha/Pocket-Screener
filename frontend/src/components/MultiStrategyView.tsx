"use client";

// Multi-Strategy Engine (Phase 3, Pro-only page).
// Pemilih 9 strategi (chips) -> kandidat strategi terpilih + Strategy Matrix.

import { useState } from "react";
import {
  getStrategies,
  getStrategyScreener,
  type StrategyCandidate,
  type StrategyMeta,
} from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { fmtInt, fmtValue } from "@/lib/format";
import { DashboardShell } from "./DashboardShell";
import { VCard } from "./vestigo/Card";
import { CardError, CardSkeleton } from "./CardStatus";
import { StrategyMatrix } from "./StrategyMatrix";

function StrategyChips({
  strategies,
  selected,
  onSelect,
}: {
  strategies: StrategyMeta[];
  selected: string;
  onSelect: (key: string) => void;
}) {
  const technical = strategies.filter((s) => s.type === "technical");
  const fundamental = strategies.filter((s) => s.type === "fundamental");

  const chip = (strategy: StrategyMeta) => (
    <button
      className={`pill-chip ${strategy.key === selected ? "pill-on" : ""}`}
      key={strategy.key}
      onClick={() => onSelect(strategy.key)}
      type="button"
    >
      {strategy.name}
    </button>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div>
        <p className="section-label chip-info">Teknikal</p>
        <div className="cmp-row">{technical.map(chip)}</div>
      </div>
      <div>
        <p className="section-label chip-warn">Fundamental</p>
        <div className="cmp-row">{fundamental.map(chip)}</div>
      </div>
    </div>
  );
}

function CandidateCard({ candidate }: { candidate: StrategyCandidate }) {
  return (
    <div className="tile">
      <div className="card-head">
        <div>
          <span className="card-title">{candidate.ticker}</span>
          {candidate.name && <span className="card-sub">{candidate.name}</span>}
        </div>
        <div className="ta-r">
          <p className="mono" style={{ fontWeight: 500 }}>
            {candidate.close != null ? fmtInt(candidate.close) : "-"}
          </p>
          <p className="card-sub mono">{fmtValue(candidate.value)}</p>
        </div>
      </div>
      <ul className="factor-list mt">
        {candidate.matched_criteria.map((reason) => (
          <li key={reason}>
            <span className="fi fi-up">↑</span>
            {reason}
          </li>
        ))}
      </ul>
    </div>
  );
}

function StrategyResults({ strategyKey }: { strategyKey: string }) {
  const { status, data, error, reload } = useApi(
    () => getStrategyScreener(strategyKey, 10),
    [strategyKey],
  );

  return (
    <VCard
      title={data?.output_label ?? "Hasil Screening"}
      sub="Kandidat + kriteria yang lolos (urut nilai transaksi)"
      subMono={false}
      cached={!!data?.cached}
      right={
        data ? (
          <span className="t3 mono small">
            {data.passed} lolos / {data.evaluated} dievaluasi
          </span>
        ) : undefined
      }
    >
      {status === "loading" && <CardSkeleton lines={6} />}
      {status === "error" && <CardError message={error} onRetry={reload} />}
      {status === "ready" && data && (
        <>
          {data.candidates.length === 0 ? (
            <p className="empty-state">Tidak ada saham yang lolos strategi ini hari ini.</p>
          ) : (
            <div className="grid-2">
              {data.candidates.map((candidate) => (
                <CandidateCard candidate={candidate} key={candidate.ticker} />
              ))}
            </div>
          )}
        </>
      )}
    </VCard>
  );
}

export function MultiStrategyView() {
  const [selected, setSelected] = useState("breakout");
  const strategies = useApi(() => getStrategies(), []);

  return (
    <DashboardShell activeNav="Strategies" eyebrow="Multi-Strategy Engine" title="Strategies">
      <VCard title="Pilih Strategi" sub="9 strategi screening - 5 teknikal & 4 fundamental" subMono={false}>
        {strategies.status === "loading" && <CardSkeleton lines={3} />}
        {strategies.status === "error" && (
          <CardError message={strategies.error} onRetry={strategies.reload} />
        )}
        {strategies.status === "ready" && strategies.data && (
          <StrategyChips onSelect={setSelected} selected={selected} strategies={strategies.data} />
        )}
      </VCard>

      <StrategyResults strategyKey={selected} />

      <StrategyMatrix />
    </DashboardShell>
  );
}
