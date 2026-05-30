# Pocket Screener

Screener saham harian **IDX** (Bursa Efek Indonesia) dengan prediksi machine
learning yang berjalan **sepenuhnya di browser** — tanpa backend. Data market
diambil langsung dari Yahoo Finance, indikator teknikal dihitung di sisi klien,
dan inferensi model dijalankan via **ONNX Runtime Web**.

> **Phase 1 — No-Backend.** Semua perhitungan live (data, indikator, screener,
> inferensi ML) berjalan di browser. Hasil backtesting & metrik model
> di-_pre-compute_ offline lalu ditampilkan sebagai snapshot JSON statis.

## Fitur

- **Screener BSJP** (Beli Sore Jual Pagi) & **BPJS** (Beli Pagi Jual Sore) —
  kriteria dihitung client-side sesuai blueprint.
- **Prediksi ML** — model `RandomForestClassifier` (di-export ke ONNX) memberi
  probabilitas kenaikan harga per saham; Top 5 di-ranking dari gabungan skor ML
  + skor kriteria.
- **Estimasi level trading** — Entry / Stop Loss / Take Profit / Exit berbasis
  ATR, dihitung di client.
- **Candlestick chart** interaktif (Lightweight-charts) — klik saham di tabel
  untuk menampilkan chart-nya.
- **Sector heatmap** — rata-rata return per sektor.
- **Halaman Backtesting** — winrate, cumulative return chart, max drawdown, dan
  statistik model (accuracy, precision, recall) dari snapshot offline.
- **Dark mode**, responsif (mobile & desktop), tabel sortable.

## Tech Stack

| Area        | Teknologi                                              |
| ----------- | ------------------------------------------------------ |
| Frontend    | Next.js 16 (App Router) · React 19 · Tailwind CSS v4   |
| ML (browser)| ONNX Runtime Web                                       |
| Chart       | Lightweight-charts (candlestick) · Recharts (lainnya)  |
| Data        | Yahoo Finance public API · JSON statis · localStorage  |
| ML (offline)| Python · scikit-learn → export ONNX (Jupyter/script)   |
| Deploy      | Vercel                                                 |

## Getting Started

Butuh **Node.js 20+**.

```bash
npm install
npm run dev
```

Buka [http://localhost:3000](http://localhost:3000).

> Request ke Yahoo Finance diproksikan lewat route internal
> `src/app/api/yahoo/route.ts` untuk menghindari masalah CORS dari browser.

## Scripts

| Perintah               | Fungsi                                                        |
| ---------------------- | ------------------------------------------------------------ |
| `npm run dev`          | Menjalankan dev server                                       |
| `npm run build`        | Build production                                             |
| `npm run start`        | Menjalankan hasil build                                      |
| `npm run lint`         | ESLint                                                       |
| `npm test`             | Unit test untuk `indicators` & `screener` (`src/lib/*.test.mts`) |
| `npm run backtest`     | Generate ulang hasil backtesting offline (`scripts/backtest-offline.mjs`) |
| `npm run train:model`  | Latih ulang model & export ONNX (`scripts/train_model_offline.py`) |

## Struktur Folder

```
pocket-screener/
├── public/
│   ├── model.onnx                 # Model ML (export offline)
│   ├── model_metrics.json         # accuracy / precision / recall
│   └── backtesting/
│       ├── bsjp_result.json       # Snapshot backtest BSJP
│       └── bpjs_result.json       # Snapshot backtest BPJS
├── src/
│   ├── lib/
│   │   ├── indicators.ts          # RSI, MACD, Bollinger, ATR, VWAP, dll
│   │   ├── screener.ts            # Logika kriteria BSJP & BPJS + level SL/TP
│   │   ├── mlInference.ts         # Wrapper ONNX Runtime Web
│   │   ├── predictionPipeline.ts  # data → indikator → fitur → inferensi → ranking
│   │   ├── fetchData.ts           # Fetch OHLCV Yahoo Finance + cache localStorage
│   │   ├── backtest.ts            # Loader & tipe data backtesting
│   │   ├── sectors.ts             # Pemetaan saham → sektor (heatmap)
│   │   └── watchlist.ts           # Universe saham (LQ45 + mid cap)
│   ├── components/
│   │   ├── Dashboard.tsx · DashboardShell.tsx
│   │   ├── ScreenerTable.tsx · CandlestickChart.tsx
│   │   ├── Heatmap.tsx · BacktestPanel.tsx · PredictionPanel.tsx
│   │   └── MarketDataStatus.tsx
│   └── app/
│       ├── page.tsx               # Dashboard + Screener
│       ├── backtest/page.tsx      # Backtesting + statistik model
│       └── api/yahoo/route.ts     # Proxy CORS Yahoo Finance
├── scripts/                       # Tooling offline (fetch, backtest, training)
└── notebooks/                     # Riset ML (Jupyter, tidak di-deploy)
```

## Kriteria Screener

**BSJP (Beli Sore Jual Pagi)**

- Price ≥ 1.05 × harga sebelumnya
- Price ≥ Price MA-5
- Volume ≥ 1.2 × volume sebelumnya
- Value > Rp 5.000.000.000

**BPJS (Beli Pagi Jual Sore)**

- Price ≥ Price MA-5
- Price ≥ 1.05 × harga sebelumnya
- Price ≥ harga Open
- Volume ≥ 0.2 × volume sebelumnya
- Value > Rp 5.000.000.000

## Alur Aplikasi

1. Fetch OHLCV harian (Yahoo Finance, fallback cache localStorage).
2. Hitung indikator teknikal (client-side).
3. Jalankan filter BSJP / BPJS.
4. Bentuk feature vector → inferensi model ONNX.
5. Ranking & scoring → Top 5 BSJP & Top 5 BPJS.
6. Render dashboard (tabel, chart, heatmap, estimasi level, snapshot backtest).

## Deployment

Dioptimalkan untuk **Vercel** (frontend-only). Push repo, import ke Vercel,
build dengan setelan default Next.js — tidak butuh environment variable maupun
backend terpisah.

## Catatan & Roadmap

- Data IDX intraday penuh sulit tanpa backend; Phase 1 fokus pada timeframe
  **harian**.
- Winrate & hasil backtesting **tidak** dihitung live — di-pre-compute offline.
- Fase berikutnya (saat backend tersedia): pindah fetching & inferensi ke
  FastAPI, tambah intraday 1m/5m, Foreign Flow & Sector Rotation, scheduled job,
  serta storage permanen.

---

Proyek edukasi. Bukan nasihat finansial.
