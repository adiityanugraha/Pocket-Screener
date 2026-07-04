"use client";

// Market Replay (Phase 4). Pemilih tanggal historis -> kandidat per strategi +
// performa forward (+1/+7/+30 hari) dari GET /api/replay/{date}.

import { useState } from "react";
import { getReplay, type ReplayCandidate } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { fmtInt, fmtPctFromFraction } from "@/lib/format";
import { STRATEGY_LABEL as STRATEGY_LABELS } from "@/lib/strategies";
import { VCard } from "../vestigo/Card";
import { CardError, CardSkeleton } from "../CardStatus";

const DEFAULT_DATE = "2024-01-15";

function Ret({ value }: { value: number | null }) {
  if (value === null) return <span className="t3">n/a</span>;
  const cls = value > 0 ? "num-up" : value < 0 ? "num-down" : "";
  return <span className={`mono ${cls}`}>{fmtPctFromFraction(value, 1)}</span>;
}

function StrategyBucket({ label, items }: { label: string; items: ReplayCandidate[] }) {
  if (items.length === 0) return null;
  return (
    <div className="tile">
      <p className="section-label chip-info">{label}</p>
      <div className="table-wrap">
        <table className="dtable">
          <thead>
            <tr>
              <th>Saham</th>
              <th className="ta-r">Harga</th>
              <th className="ta-r">+1h</th>
              <th className="ta-r">+7h</th>
              <th className="ta-r">+30h</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.ticker}>
                <td>
                  <span className="tk-pill">{c.ticker}</span>
                </td>
                <td className="ta-r mono t2">{c.price != null ? fmtInt(c.price) : "-"}</td>
                <td className="ta-r">
                  <Ret value={c.ret["1d"]} />
                </td>
                <td className="ta-r">
                  <Ret value={c.ret["7d"]} />
                </td>
                <td className="ta-r">
                  <Ret value={c.ret["30d"]} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function MarketReplay() {
  const [date, setDate] = useState(DEFAULT_DATE);
  const { status, data, error, reload } = useApi(() => getReplay(date), [date]);

  return (
    <VCard
      title="Market Replay"
      sub="Putar ulang kandidat screening pada tanggal historis + performa setelahnya"
      subMono={false}
      cached={!!data?.cached}
    >
      <div className="cmp-row">
        <input
          type="date"
          value={date}
          min={data?.data_range.earliest ?? undefined}
          max={data?.data_range.latest ?? undefined}
          onChange={(e) => e.target.value && setDate(e.target.value)}
          className="field-input"
          style={{ flex: "0 0 auto", colorScheme: "dark" }}
        />
        {data && <span className="t3 small">{data.total_candidates} kandidat</span>}
      </div>

      {status === "loading" && <CardSkeleton lines={5} />}
      {status === "error" && <CardError message={error} onRetry={reload} />}
      {status === "ready" && data && (
        <>
          {data.total_candidates === 0 ? (
            <p className="empty-state">
              Tidak ada kandidat lolos pada tanggal ini. Coba tanggal lain dalam rentang{" "}
              {data.data_range.earliest} - {data.data_range.latest}.
            </p>
          ) : (
            <div className="grid-2">
              {Object.entries(data.strategies).map(([key, items]) => (
                <StrategyBucket key={key} label={STRATEGY_LABELS[key] ?? key} items={items} />
              ))}
            </div>
          )}
          <p className="feature-note">
            Memutar ulang kandidat screening pada tanggal lampau dan performanya setelah itu.
          </p>
          <p className="disclaimer">{data.disclaimer}</p>
        </>
      )}
    </VCard>
  );
}
