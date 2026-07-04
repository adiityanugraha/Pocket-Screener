"use client";

// Explainable AI + Explain Why Selected (Phase 3).
// Kiri : /api/explain - confidence + bullish/risk factors.
// Kanan: /api/why - strategi yang cocok + alasan per kriteria yang lolos.

import { getExplain, getWhy } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { VCard } from "./vestigo/Card";
import { CardError, CardSkeleton } from "./CardStatus";

function FactorList({
  factors,
  dir,
  emptyText,
}: {
  factors: string[];
  dir: "up" | "down";
  emptyText: string;
}) {
  if (factors.length === 0) {
    return <p className="t3 small">{emptyText}</p>;
  }
  return (
    <ul className="factor-list">
      {factors.map((factor) => (
        <li key={factor}>
          <span className={`fi fi-${dir}`}>{dir === "up" ? "↑" : "!"}</span>
          {factor}
        </li>
      ))}
    </ul>
  );
}

function ExplainSide({ symbol }: { symbol: string }) {
  const { status, data, error, reload } = useApi(() => getExplain(symbol), [symbol]);

  return (
    <div>
      <div className="card-head" style={{ marginBottom: 12 }}>
        <h3 className="section-label" style={{ margin: 0 }}>
          Explainable AI
        </h3>
        {data && <span className="badge badge-info badge-full">Confidence {data.confidence}%</span>}
      </div>

      {status === "loading" && <CardSkeleton lines={6} />}
      {status === "error" && <CardError message={error} onRetry={reload} />}
      {status === "ready" && data && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div>
            <p className="section-label">Faktor bullish</p>
            <FactorList
              emptyText="Tidak ada sinyal bullish menonjol."
              factors={data.bullish_factors}
              dir="up"
            />
          </div>
          <div>
            <p className="section-label">Faktor risiko</p>
            <FactorList
              emptyText="Tidak ada sinyal risiko menonjol."
              factors={data.risk_factors}
              dir="down"
            />
          </div>
        </div>
      )}
    </div>
  );
}

function WhySide({ symbol }: { symbol: string }) {
  const { status, data, error, reload } = useApi(() => getWhy(symbol), [symbol]);

  return (
    <div>
      <div className="card-head" style={{ marginBottom: 12 }}>
        <h3 className="section-label" style={{ margin: 0 }}>
          Why Selected
        </h3>
        {data && data.matched.length > 0 && (
          <span className="badge badge-up badge-full">{data.matched.length} strategi cocok</span>
        )}
      </div>

      {status === "loading" && <CardSkeleton lines={6} />}
      {status === "error" && <CardError message={error} onRetry={reload} />}
      {status === "ready" && data && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {data.matched_strategies.length === 0 ? (
            <p className="t3 small">Saham ini tidak lolos strategi screening mana pun hari ini.</p>
          ) : (
            data.matched_strategies.map((strategy) => (
              <div className="tile" key={strategy.key}>
                <p className="section-label" style={{ marginBottom: 8 }}>
                  <span className="num-up">✓ </span>
                  {strategy.name}
                  <span
                    className={`badge badge-${strategy.type === "fundamental" ? "warn" : "info"}`}
                    style={{ marginLeft: 8 }}
                  >
                    {strategy.type}
                  </span>
                </p>
                <FactorList emptyText="-" factors={strategy.reasons} dir="up" />
                {strategy.skipped.length > 0 && (
                  <p className="t3 small mt" style={{ fontStyle: "italic" }}>
                    {strategy.skipped.length} kriteria dilewati (data tidak tersedia di sumber gratis)
                  </p>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

export function ExplainPanel({ symbol }: { symbol: string }) {
  return (
    <VCard
      title={`Explain · ${symbol}`}
      sub="Kenapa saham ini terpilih - dari kriteria yang benar-benar lolos"
      subMono={false}
    >
      <div className="xai-grid">
        <ExplainSide symbol={symbol} />
        <WhySide symbol={symbol} />
      </div>
    </VCard>
  );
}
