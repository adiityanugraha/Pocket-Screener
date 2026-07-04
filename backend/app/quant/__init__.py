"""Mesin kuantitatif Pocket Screener - Phase 4 (Quant Analytics & Validation).

Berisi logika murni numerik (numpy/pandas/scipy) untuk MEMVALIDASI 9 strategi
Phase 3 secara historis - tanpa menambah model AI baru. Modul ditambahkan per
hari sesuai Step_by_Step_Phase4:

  reconstruct.py        (Day 2-3)  rekonstruksi histori point-in-time + return series
  performance_metrics.py(Day 4)    CAGR/Sharpe/Sortino/Calmar/ProfitFactor/Recovery/MaxDD
  equity_curve.py       (Day 5)    kurva modal + drawdown
  benchmark.py          (Day 6)    perbandingan lintas strategi + IHSG
  market_replay.py      (Day 7)    putar ulang kandidat tanggal historis
  risk_profile.py       (Day 8)    profil risiko per strategi
  correlation_matrix.py (Day 9)    korelasi Pearson universe terbatas
  monte_carlo.py        (Day 10)   bootstrap resampling distribusi hasil
  walk_forward.py       (Day 11)   backtest rolling/anchored out-of-sample
  portfolio_builder.py  (Day 12)   alokasi portofolio per profil risiko

CATATAN VALIDASI (keputusan 2026-06-12): hanya 5 strategi TEKNIKAL (bsjp, bpjs,
breakout, trend_following, potential_reversal) yang divalidasi historis -
strategi fundamental dikecualikan karena tidak ada data fundamental
point-in-time (akan mengakibatkan look-ahead bias).
"""
