"use client";

// Pick harian Top 5 BSJP / BPJS (Screener Lite). Tabel deterministik dari
// GET /api/screener - tanpa ringkasan ML Screener (itu khusus Pro).

import { getScreener } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ScreenerTable, toScreenerRow } from "./ScreenerTable";

type DailyPicksProps = {
  onSelectSymbol: (symbol: string) => void;
  selectedSymbol: string;
};

export function DailyPicks({ onSelectSymbol, selectedSymbol }: DailyPicksProps) {
  const { status, data } = useApi(() => getScreener(5, true), []);
  const loading = status === "loading";

  return (
    <div className="grid-2">
      <ScreenerTable
        isLoading={loading}
        onSelectSymbol={onSelectSymbol}
        selectedSymbol={selectedSymbol}
        title="Top 5 BSJP"
        rows={data ? data.bsjp.map(toScreenerRow) : []}
      />
      <ScreenerTable
        isLoading={loading}
        onSelectSymbol={onSelectSymbol}
        selectedSymbol={selectedSymbol}
        title="Top 5 BPJS"
        rows={data ? data.bpjs.map(toScreenerRow) : []}
      />
    </div>
  );
}
