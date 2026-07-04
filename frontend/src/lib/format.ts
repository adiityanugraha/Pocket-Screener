// Vestigo - one centralized id-ID number formatter (design.txt §3.4).
// Never mix "6,275" and "6.012,94" on the same screen: everything routes here.

const ID = "id-ID";

export type Dir = "up" | "down" | "flat";

export function signDir(v: number | null | undefined): Dir {
  if (v === null || v === undefined || Number.isNaN(v)) return "flat";
  return v > 0 ? "up" : v < 0 ? "down" : "flat";
}

/** Harga / nilai: 6.275,00 (titik ribuan, koma desimal). */
export function fmtPrice(v: number | null | undefined, dp = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "-";
  return v.toLocaleString(ID, {
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  });
}

export function fmtInt(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "-";
  return v.toLocaleString(ID);
}

/** Persen dengan tanda eksplisit: +6,2% / −2,4%. Accepts a percent value (not a fraction). */
export function fmtPct(v: number | null | undefined, dp = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "-";
  const s = v > 0 ? "+" : v < 0 ? "−" : "";
  return (
    s +
    Math.abs(v).toLocaleString(ID, {
      minimumFractionDigits: dp,
      maximumFractionDigits: dp,
    }) +
    "%"
  );
}

/** Convenience for APIs that return a fraction (0.062 → +6,2%). */
export function fmtPctFromFraction(v: number | null | undefined, dp = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "-";
  return fmtPct(v * 100, dp);
}

/** Nilai besar rupiah: Rp 3,01 M / Rp 57,5 T / Rp 850 Jt. */
export function fmtValue(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "-";
  const abs = Math.abs(v);
  if (abs >= 1e12)
    return "Rp " + (v / 1e12).toLocaleString(ID, { maximumFractionDigits: 1 }) + " T";
  if (abs >= 1e9)
    return "Rp " + (v / 1e9).toLocaleString(ID, { maximumFractionDigits: 2 }) + " M";
  if (abs >= 1e6)
    return "Rp " + (v / 1e6).toLocaleString(ID, { maximumFractionDigits: 0 }) + " Jt";
  return "Rp " + fmtInt(v);
}

/** Skor 0-100: 75,5. */
export function fmtScore(v: number | null | undefined, dp = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "-";
  return v.toLocaleString(ID, {
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  });
}
