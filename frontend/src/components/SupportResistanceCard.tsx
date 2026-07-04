"use client";

import { getSupportResistance } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { fmtInt } from "@/lib/format";
import { useMode } from "./ModeProvider";
import { VCard } from "./vestigo/Card";
import { CardError, CardSkeleton } from "./CardStatus";

export function SupportResistanceCard({ symbol }: { symbol: string }) {
  const { pro } = useMode();
  const { status, data, error, reload } = useApi(
    () => getSupportResistance(symbol),
    [symbol],
  );

  return (
    <VCard title="Support & Resistance" sub={symbol} cached={!!data?.cached}>
      {status === "loading" && <CardSkeleton lines={4} />}
      {status === "error" && <CardError message={error} onRetry={reload} />}
      {status === "ready" && data && (
        <>
          <div className="sr-rows">
            <div className="sr-row sr-res">
              <span className="sr-label">Resistance</span>
              <span className="sr-val mono">{fmtInt(data.resistance)}</span>
            </div>
            <div className="sr-row sr-now">
              <span className="sr-label">Harga saat ini</span>
              <span className="sr-val mono">{fmtInt(data.current)}</span>
            </div>
            <div className="sr-row sr-sup">
              <span className="sr-label">Support</span>
              <span className="sr-val mono">{fmtInt(data.support)}</span>
            </div>
          </div>

          {pro && (
            <div className="tile-grid-2">
              <div className="tile">
                <p className="tile-label">Pivot Point</p>
                <p className="tile-val mono">{fmtInt(data.methods.pivot.pivot)}</p>
              </div>
              <div className="tile">
                <p className="tile-label">Breakout Zone</p>
                <p className="tile-val mono">
                  {data.breakout_zone
                    ? `${fmtInt(data.breakout_zone.lower)}-${fmtInt(data.breakout_zone.upper)}`
                    : "-"}
                </p>
              </div>
            </div>
          )}
        </>
      )}
    </VCard>
  );
}
