"use client";

import { AiReportCard } from "./AiReportCard";
import { CandlestickChart } from "./CandlestickChart";
import { DashboardShell } from "./DashboardShell";
import { RiskMeterCard } from "./RiskMeterCard";
import { SupportResistanceCard } from "./SupportResistanceCard";

// Dashboard menampilkan KONTEKS PASAR: IHSG (Indeks Harga Saham Gabungan).
// Simbol dikunci ke IHSG - chart, verdict AI, risk meter, dan support/resistance.
// Kartu menyesuaikan kedalaman sendiri lewat useMode (Lite vs Pro).
const IHSG_SYMBOL = "IHSG";

export function Dashboard() {
  return (
    <DashboardShell
      activeNav="Dashboard"
      eyebrow="IDX Market Context"
      title="IHSG · Indeks Harga Saham Gabungan"
    >
      <CandlestickChart symbol={IHSG_SYMBOL} />

      <div className="grid-3">
        <AiReportCard symbol={IHSG_SYMBOL} />
        <RiskMeterCard symbol={IHSG_SYMBOL} />
        <SupportResistanceCard symbol={IHSG_SYMBOL} />
      </div>
    </DashboardShell>
  );
}
