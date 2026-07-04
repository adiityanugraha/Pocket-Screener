// Sumber tunggal metadata strategi (frontend). Backend Strategy Registry tetap
// jadi sumber kebenaran sebenarnya; ini hanya label/kode tampilan agar tidak
// di-hardcode berulang di banyak komponen.

export type StrategyType = "technical" | "fundamental";

export type StrategyInfo = {
  key: string;
  /** Nama tampilan penuh, mis. "Trend Following". */
  label: string;
  /** Kode singkat untuk Strategy Matrix, mis. "TRND". */
  short: string;
  type: StrategyType;
};

export const STRATEGIES: StrategyInfo[] = [
  { key: "bsjp", label: "BSJP", short: "BSJP", type: "technical" },
  { key: "bpjs", label: "BPJS", short: "BPJS", type: "technical" },
  { key: "breakout", label: "Breakout", short: "BRK", type: "technical" },
  { key: "trend_following", label: "Trend Following", short: "TRND", type: "technical" },
  { key: "potential_reversal", label: "Potential Reversal", short: "RVSL", type: "technical" },
  { key: "high_growth", label: "High Growth", short: "GRWT", type: "fundamental" },
  { key: "cash_rich", label: "Cash Rich", short: "CASH", type: "fundamental" },
  { key: "turnaround", label: "Turnaround", short: "TURN", type: "fundamental" },
  { key: "timeless", label: "Timeless", short: "TMLS", type: "fundamental" },
];

/** 5 strategi teknikal - satu-satunya yang divalidasi historis (Phase 4). */
export const TECHNICAL_STRATEGIES: StrategyInfo[] = STRATEGIES.filter(
  (s) => s.type === "technical",
);

/** key -> kode singkat (Strategy Matrix). */
export const STRATEGY_SHORT: Record<string, string> = Object.fromEntries(
  STRATEGIES.map((s) => [s.key, s.short]),
);

/** key -> nama tampilan penuh. */
export const STRATEGY_LABEL: Record<string, string> = Object.fromEntries(
  STRATEGIES.map((s) => [s.key, s.label]),
);
