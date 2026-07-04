"use client";

// Strategy Comparison Matrix (Phase 3). Saham x 9 strategi, sel tiga-keadaan:
//   ✓ lolos / × dinilai-gagal / - tak dinilai. GET /api/strategy-matrix.

import { useState } from "react";
import { getStrategyMatrix, type StrategyMeta } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { STRATEGY_SHORT as SHORT_LABELS } from "@/lib/strategies";
import { VCard } from "./vestigo/Card";
import { CardError, CardSkeleton } from "./CardStatus";

function shortLabel(strategy: StrategyMeta): string {
  return SHORT_LABELS[strategy.key] ?? strategy.key.slice(0, 4).toUpperCase();
}

function Cell({ value }: { value: boolean | null }) {
  if (value === true) return <span className="mx-cell mx-pass">✓</span>;
  if (value === false) return <span className="mx-cell mx-fail">×</span>;
  return (
    <span className="mx-cell mx-na" title="Tidak dinilai (data tidak cukup)">
      -
    </span>
  );
}

export function StrategyMatrix() {
  const [minPassed, setMinPassed] = useState(1);
  const { status, data, error, reload } = useApi(
    () => getStrategyMatrix(minPassed),
    [minPassed],
  );

  return (
    <VCard
      title="Strategy Matrix"
      sub="Pass / fail per ticker · 9 strategi (✓ lolos · × gagal · - tak dinilai)"
      subMono={false}
      cached={!!data?.cached}
      right={
        <label className="select-wrap">
          <span className="chip-label">Min. lolos</span>
          <select
            className="select"
            value={minPassed}
            onChange={(event) => setMinPassed(Number(event.target.value))}
          >
            {[1, 2, 3, 4].map((n) => (
              <option key={n} value={n}>
                {n}+
              </option>
            ))}
          </select>
        </label>
      }
    >
      {status === "loading" && <CardSkeleton lines={7} />}
      {status === "error" && <CardError message={error} onRetry={reload} />}
      {status === "ready" && data && (
        <>
          {data.matrix.length === 0 ? (
            <p className="empty-state">Tidak ada saham yang lolos ≥ {minPassed} strategi.</p>
          ) : (
            <div className="matrix-wrap">
              <table className="dtable matrix">
                <thead>
                  <tr>
                    <th className="mx-sticky">Ticker</th>
                    <th className="ta-c">Lolos</th>
                    {data.strategies.map((strategy) => (
                      <th key={strategy.key} className="ta-c" title={strategy.name}>
                        <span className={strategy.type === "fundamental" ? "chip-warn" : "chip-info"}>
                          {shortLabel(strategy)}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.matrix.map((row) => (
                    <tr key={row.ticker}>
                      <td className="mx-sticky">
                        <span className="tk-pill">{row.ticker}</span>
                      </td>
                      <td className="ta-c mono num-up">
                        <strong>{row.passed_count}</strong>
                      </td>
                      {data.strategies.map((strategy) => (
                        <td key={strategy.key} className="ta-c">
                          <Cell value={row.results[strategy.key] ?? null} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="card-sub mt">
            <span className="chip-info">biru</span> = teknikal ·{" "}
            <span className="chip-warn">kuning</span> = fundamental · {data.universe_evaluated} saham
            dievaluasi. Geser horizontal untuk strategi lainnya.
          </p>
        </>
      )}
    </VCard>
  );
}
