"""Sector Rotation - kekuatan relatif & rotasi sektor lintas waktu (Phase 5 Day 2).

Fitur ini "ditunda sejak Phase 1"; diimplementasikan di Phase 5 karena menjadi
PRASYARAT AI Analyst Engine & Market Narrator (mereka butuh konteks sektor).
Berbeda dari `market_breadth` yang hanya memberi performa sektor SATU hari,
modul ini mengukur kekuatan sektor pada beberapa horizon (1M/3M/6M), kekuatan
RELATIF terhadap IHSG, dan arah rotasi (kuadran gaya Relative Rotation Graph).

Modul ini MURNI (tanpa DB/cache) agar mudah diuji dengan data sintetis. API
(app/api/sector_rotation.py) yang memuat seri harga dari market_data,
mengelompokkan per sektor, lalu memanggil compute_rotation().

Definisi:
  - return window  : close[-1]/close[-1-w] - 1 (per saham, w = jumlah hari bursa).
  - return sektor  : rata-rata equal-weight return anggota sektor pada window itu.
  - relative strength (RS) : return sektor - return IHSG pada window yang sama
                              (kelebihan/kekurangan vs pasar).
  - momentum       : RS(1M) - RS(3M) - RS yang membaik (>0) berarti akselerasi.
  - kuadran rotasi : LEADING (RS>0, mom>0), WEAKENING (RS>0, mom<0),
                     LAGGING (RS<0, mom<0), IMPROVING (RS<0, mom>0).

Anti-halusinasi (relevan Phase 5): output ini adalah ANGKA dari sistem; LLM
nanti hanya menarasikannya.
"""

from __future__ import annotations

from dataclasses import dataclass

# Window default dalam HARI BURSA (≈21/63/126 = 1/3/6 bulan).
DEFAULT_WINDOWS: dict[str, int] = {"1m": 21, "3m": 63, "6m": 126}

# Kunci window yang dipakai untuk momentum & ranking rotasi.
SHORT_KEY = "1m"
MED_KEY = "3m"

DEFAULT_TOP_N = 3


@dataclass(frozen=True)
class SectorInput:
    """Masukan per sektor: nama + seri close tiap anggota (urut tanggal naik)."""

    sector: str
    member_closes: list[list[float]]


@dataclass(frozen=True)
class SectorRotation:
    sector: str
    members: int
    returns: dict[str, float | None]            # window -> return sektor
    relative_strength: dict[str, float | None]  # window -> excess vs IHSG
    momentum: float | None                       # RS(1M) - RS(3M)
    quadrant: str                                # LEADING/WEAKENING/LAGGING/IMPROVING/UNKNOWN
    rank: int | None                             # peringkat by RS(3M), 1 = terkuat


@dataclass(frozen=True)
class RotationResult:
    as_of: str
    windows: dict[str, int]
    market_available: bool
    market_returns: dict[str, float | None]
    sectors: list[SectorRotation]
    leaders: list[str]
    laggards: list[str]
    limitations: list[str]


def window_return(closes: list[float], window: int) -> float | None:
    """Return harga selama `window` hari bursa terakhir. None bila data kurang."""
    if window <= 0 or len(closes) < window + 1:
        return None
    base = closes[-1 - window]
    last = closes[-1]
    if not base or base <= 0 or last is None:
        return None
    return last / base - 1


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def classify_quadrant(rs: float | None, momentum: float | None) -> str:
    """Kuadran rotasi dari relative strength (3M) & momentum (RS 1M - RS 3M)."""
    if rs is None or momentum is None:
        return "UNKNOWN"
    if rs >= 0:
        return "LEADING" if momentum >= 0 else "WEAKENING"
    return "IMPROVING" if momentum >= 0 else "LAGGING"


def compute_rotation(
    sector_inputs: list[SectorInput],
    market_closes: list[float],
    *,
    as_of: str,
    windows: dict[str, int] | None = None,
    top_n: int = DEFAULT_TOP_N,
) -> RotationResult:
    """Hitung rotasi sektor. Aman terhadap data IHSG/anggota yang tidak lengkap."""
    windows = windows or DEFAULT_WINDOWS

    market_returns: dict[str, float | None] = {
        key: window_return(market_closes, w) for key, w in windows.items()
    }
    market_available = any(v is not None for v in market_returns.values())

    rotations: list[SectorRotation] = []
    for item in sector_inputs:
        # Return sektor per window = rata-rata return anggota yang datanya cukup.
        sector_returns: dict[str, float | None] = {}
        for key, w in windows.items():
            member_rets = [
                r
                for closes in item.member_closes
                if (r := window_return(closes, w)) is not None
            ]
            sector_returns[key] = _mean(member_rets)

        # Relative strength = return sektor - return IHSG (None bila salah satu None).
        rs: dict[str, float | None] = {}
        for key in windows:
            sr, mr = sector_returns[key], market_returns[key]
            rs[key] = (sr - mr) if (sr is not None and mr is not None) else None

        rs_short, rs_med = rs.get(SHORT_KEY), rs.get(MED_KEY)
        momentum = (rs_short - rs_med) if (rs_short is not None and rs_med is not None) else None

        rotations.append(
            SectorRotation(
                sector=item.sector,
                members=len(item.member_closes),
                returns=sector_returns,
                relative_strength=rs,
                momentum=momentum,
                quadrant=classify_quadrant(rs_med, momentum),
                rank=None,  # diisi setelah ranking
            )
        )

    # Ranking by RS(3M) desc; sektor tanpa RS(3M) ditaruh di akhir tanpa rank.
    ranked = sorted(
        rotations,
        key=lambda s: (s.relative_strength.get(MED_KEY) is None, -(s.relative_strength.get(MED_KEY) or 0.0)),
    )
    final: list[SectorRotation] = []
    rank_counter = 0
    for s in ranked:
        if s.relative_strength.get(MED_KEY) is not None:
            rank_counter += 1
            final.append(_with_rank(s, rank_counter))
        else:
            final.append(s)

    rankable = [s for s in final if s.rank is not None]
    leaders = [s.sector for s in rankable[:top_n]]
    laggards = [s.sector for s in rankable[-top_n:][::-1]] if rankable else []

    limitations: list[str] = []
    if not market_available:
        limitations.append(
            "Data IHSG tidak tersedia pada rentang ini - relative strength & "
            "kuadran rotasi tidak dapat dihitung (hanya return absolut sektor)."
        )
    if not sector_inputs:
        limitations.append("Tidak ada sektor dengan data yang cukup.")

    return RotationResult(
        as_of=as_of,
        windows=dict(windows),
        market_available=market_available,
        market_returns=market_returns,
        sectors=final,
        leaders=leaders,
        laggards=laggards,
        limitations=limitations,
    )


def _with_rank(s: SectorRotation, rank: int) -> SectorRotation:
    return SectorRotation(
        sector=s.sector,
        members=s.members,
        returns=s.returns,
        relative_strength=s.relative_strength,
        momentum=s.momentum,
        quadrant=s.quadrant,
        rank=rank,
    )
