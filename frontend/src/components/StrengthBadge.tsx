"use client";

// Strength Score card (Phase 3) - skor kekuatan lintas-strategi 0-100 dari
// GET /api/strength/{ticker} + daftar strategi yang lolos beserta bobotnya.

import { getStrength } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { fmtScore } from "@/lib/format";
import { VCard } from "./vestigo/Card";
import { CardError, CardSkeleton } from "./CardStatus";

function strengthMeta(strength: number): { color: string; label: string } {
  if (strength >= 66) return { color: "var(--up)", label: "Kuat" };
  if (strength >= 40) return { color: "var(--warn)", label: "Sedang" };
  return { color: "var(--down)", label: "Lemah" };
}

function Gauge({ value }: { value: number }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const frac = Math.max(0, Math.min(1, value / 100));
  const { color, label } = strengthMeta(value);
  return (
    <div className="gauge">
      <svg viewBox="0 0 128 128" width={128} height={128}>
        <circle cx="64" cy="64" r={r} fill="none" stroke="var(--s2)" strokeWidth="10" />
        <circle
          cx="64"
          cy="64"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - frac)}
          transform="rotate(-90 64 64)"
          style={{ transition: "stroke-dashoffset .6s ease" }}
        />
        <text x="64" y="60" textAnchor="middle" className="gauge-num" fill="var(--t1)">
          {value}
        </text>
        <text x="64" y="80" textAnchor="middle" className="gauge-max" fill="var(--t3)">
          / 100
        </text>
      </svg>
      <div className="gauge-meta">
        <span
          className="badge badge-full"
          style={{ color, borderColor: `${color}55`, background: `${color}1f` }}
        >
          {label}
        </span>
      </div>
    </div>
  );
}

export function StrengthBadge({ symbol }: { symbol: string }) {
  const { status, data, error, reload } = useApi(() => getStrength(symbol), [symbol]);
  const maxWeight =
    data && data.breakdown.length > 0
      ? Math.max(...data.breakdown.map((b) => b.weight))
      : 1;

  return (
    <VCard
      title="Strength Score"
      sub="Kekuatan lintas 9 strategi screening"
      subMono={false}
      cached={!!data?.cached}
      right={data ? <span className="t3 mono small">{data.ticker}</span> : undefined}
    >
      {status === "loading" && <CardSkeleton lines={5} />}
      {status === "error" && <CardError message={error} onRetry={reload} />}
      {status === "ready" && data && (
        <div className="gauge-row">
          <Gauge value={data.strength} />
          <div className="flex1" style={{ minWidth: 200 }}>
            {data.breakdown.length === 0 ? (
              <p className="empty-state">Tidak lolos strategi apa pun hari ini.</p>
            ) : (
              <>
                <ul className="contrib-list">
                  {data.breakdown.map((component) => (
                    <li key={component.strategy}>
                      <span className="contrib-label">{component.strategy}</span>
                      <span
                        className={`mono small ${
                          component.type === "fundamental" ? "chip-warn" : "chip-info"
                        }`}
                      >
                        {component.type === "fundamental" ? "fund" : "tech"}
                      </span>
                      <div className="contrib-track">
                        <div
                          className="contrib-fill"
                          style={{ width: `${(component.weight / maxWeight) * 100}%` }}
                        />
                      </div>
                      <span className="mono contrib-v">+{fmtScore(component.weight)}</span>
                    </li>
                  ))}
                </ul>
                <p className="card-sub mono mt">
                  {fmtScore(data.points)} / {fmtScore(data.max_points, 0)} poin berbobot
                </p>
              </>
            )}
          </div>
        </div>
      )}
    </VCard>
  );
}
