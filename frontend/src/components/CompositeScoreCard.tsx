"use client";

import { getRanking } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { fmtScore } from "@/lib/format";
import { VCard } from "./vestigo/Card";
import { CardError, CardSkeleton } from "./CardStatus";

function scoreClass(score: number): string {
  if (score >= 65) return "num-up";
  if (score >= 45) return "chip-warn";
  return "num-down";
}

export function CompositeScoreCard({
  onSelectSymbol,
  selectedSymbol,
}: {
  onSelectSymbol: (symbol: string) => void;
  selectedSymbol: string;
}) {
  const { status, data, error, reload } = useApi(() => getRanking(15, true), []);
  const selectedBare = selectedSymbol.replace(/\.JK$/i, "");

  return (
    <VCard
      title="Composite Score"
      sub="Ranking penuh · klik baris untuk detail"
      subMono={false}
      cached={!!data?.cached}
      right={data ? <span className="t3 mono small">{data.items.length} baris</span> : undefined}
    >
      {status === "loading" && <CardSkeleton lines={6} />}
      {status === "error" && <CardError message={error} onRetry={reload} />}
      {status === "ready" && data && (
        <div className="table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>#</th>
                <th>Symbol</th>
                <th className="ta-r">Score</th>
                <th className="ta-r">Tech</th>
                <th className="ta-r">Mom</th>
                <th className="ta-r">ML</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => {
                const sel = item.ticker === selectedBare;
                return (
                  <tr
                    key={item.ticker}
                    className={sel ? "row-sel" : "row-click"}
                    onClick={() => onSelectSymbol(item.ticker)}
                  >
                    <td className="mono t3">{item.rank}</td>
                    <td>
                      <span className={`tk-pill ${sel ? "tk-sel" : ""}`}>{item.ticker}</span>
                    </td>
                    <td className="ta-r mono">
                      <strong className={scoreClass(item.overall_score)}>
                        {fmtScore(item.overall_score)}
                      </strong>
                    </td>
                    <td className="ta-r mono">{fmtScore(item.breakdown.technical, 0)}</td>
                    <td className="ta-r mono">{fmtScore(item.breakdown.momentum, 0)}</td>
                    <td className="ta-r mono">
                      {item.breakdown.ml === null ? "-" : fmtScore(item.breakdown.ml, 0)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </VCard>
  );
}
