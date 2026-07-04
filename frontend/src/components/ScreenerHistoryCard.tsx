"use client";

import { getHistory } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { fmtPctFromFraction, fmtScore } from "@/lib/format";
import { VCard } from "./vestigo/Card";
import { CardError, CardSkeleton } from "./CardStatus";

function outcomeClass(outcome: string): string {
  if (outcome === "WIN") return "num-up";
  if (outcome === "LOSS") return "num-down";
  return "t3";
}

export function ScreenerHistoryCard() {
  const { status, data, error, reload } = useApi(() => getHistory({ horizon: 7, limit: 30 }), []);

  return (
    <VCard
      title="Screener History"
      sub={`Performa ${data?.horizon ?? 7} hari setelah lolos screener`}
      subMono={false}
    >
      {status === "loading" && <CardSkeleton lines={6} />}
      {status === "error" && <CardError message={error} onRetry={reload} />}
      {status === "ready" && data && (
        <>
          <div className="grid-2">
            {data.summary.map((s) => (
              <div className="wr-box" key={s.strategy}>
                <p className="section-label">{s.strategy} winrate</p>
                <p className="big-num mono num-up">
                  {s.winrate === null ? "-" : `${fmtScore(s.winrate * 100, 1)}%`}
                </p>
                <p className="card-sub mono">
                  {s.wins}W / {s.losses}L dari {s.evaluated}
                </p>
              </div>
            ))}
            {data.summary.length === 0 && (
              <p className="empty-state">
                Belum ada data winrate (butuh ≥7 hari riwayat terevaluasi).
              </p>
            )}
          </div>

          <div className="table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Tanggal</th>
                  <th>Symbol</th>
                  <th>Strat</th>
                  <th className="ta-r">Return</th>
                  <th className="ta-r">Hasil</th>
                </tr>
              </thead>
              <tbody>
                {data.entries.slice(0, 15).map((e, index) => (
                  <tr key={`${e.date}-${e.ticker}-${e.strategy}-${index}`}>
                    <td className="mono t2">{e.date}</td>
                    <td>
                      <span className="tk-pill">{e.ticker}</span>
                    </td>
                    <td className="t2">{e.strategy}</td>
                    <td className="ta-r mono">{fmtPctFromFraction(e.forward_return, 2)}</td>
                    <td className={`ta-r mono ${outcomeClass(e.outcome)}`}>{e.outcome}</td>
                  </tr>
                ))}
                {data.entries.length === 0 && (
                  <tr>
                    <td colSpan={5} className="t3">
                      Belum ada riwayat screener.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </VCard>
  );
}
