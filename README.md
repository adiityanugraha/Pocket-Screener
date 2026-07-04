# Vestigo

**Vestigo** (Latin: _"aku menelusuri/melacak jejak"_) adalah screener saham harian
**IDX** (Bursa Efek Indonesia) dengan **multi-strategi** (teknikal & fundamental),
prediksi _machine learning_, penjelasan otomatis (_Explainable AI_), **validasi
kuantitatif** (backtest, benchmark, Monte Carlo, portfolio builder), serta **lapisan
AI Financial Analyst** (analisis, chat, dan screener bahasa alami berbasis LLM -
_grounded_ ke data sistem). UI bertema **"quiet trading terminal"** gelap dengan
sistem **mode Lite / Pro**. Proyek ini adalah **monorepo** dua bagian: frontend
Next.js dan backend FastAPI.

> ⚠️ Proyek edukasi. **Bukan nasihat finansial.**

**🔗 Live demo:** [vestigo-steel.vercel.app](https://vestigo-steel.vercel.app) · **API docs:** [/docs](https://vestigo-production.up.railway.app/docs)

> Di-host pada tier gratis (Vercel + Railway). Pemuatan pertama endpoint berat
> (Screener/Ranking) bisa ~15-20 detik karena _cold start_ inferensi ONNX, lalu
> hasilnya di-cache (Redis).

---

## Gambaran Besar

Vestigo dibangun dalam lima fase (lalu di-_rebrand_ & _redesign_ - lihat
[Tampilan & Mode Lite/Pro](#tampilan--vestigo--mode-litepro)):

- **Phase 1 - No-Backend.** Semua perhitungan (fetch data Yahoo, indikator teknikal,
  inferensi ML via ONNX Runtime Web) berjalan **sepenuhnya di browser**. Hasil
  backtesting di-_pre-compute_ offline.
- **Phase 2 - Backend.** Seluruh komputasi berat dipindah **server-side** ke
  FastAPI: data pipeline, indikator, inferensi ONNX, screener, composite score,
  AI report, risk meter, support/resistance, market breadth, screener history,
  dan scheduler harian. Frontend kini memanggil **REST API** dan jadi ringan.
- **Phase 3 - Intelligent Multi-Strategy Engine.** Fokus pada **logika** &
  **transparansi**: **9 strategi** (5 teknikal + 4 fundamental) via _Strategy
  Registry_ yang pluggable, data **fundamental** (Yahoo), **Probability Forecast**
  multi-horizon (1D/5D/20D), **Strategy Matrix**, **Strength Score** lintas-strategi,
  serta **Explainable AI** + **Explain Why Selected**.
- **Phase 4 - Quant Analytics & Validation.** Fokus **membuktikan** kualitas
  strategi (bukan menambah AI baru): rekonstruksi histori screening **point-in-time**
  (10 tahun, anti _look-ahead_) → **Market Replay**, **Walk-Forward Backtesting**,
  metrik lanjutan (**CAGR · Sharpe · Sortino · Calmar · Profit Factor · Max
  Drawdown**), **Strategy Benchmark** vs IHSG, **Equity Curve**, **Monte Carlo**,
  **Risk Exposure** per strategi, **Correlation Matrix**, dan **Portfolio Builder**.
  Hanya **5 strategi teknikal** yang divalidasi historis (fundamental dikecualikan -
  tak ada data _point-in-time_).
- **Phase 5 - AI Financial Analyst.** Lapisan **LLM bahasa alami** di atas seluruh
  data Phase 1-4. Prinsip inti **grounding**: LLM hanya **menarasikan** angka dari
  endpoint/DB sistem (anti-halusinasi - dilarang mengarang angka). Mencakup **AI
  Analyst Engine**, **Explainable AI 2.0**, **Chat With Stock** (RAG + tool call +
  streaming), **Natural Language Screener**, **AI Strategy Comparator**, **Portfolio
  AI Advisor**, **Market Narrator**, dan **AI Daily Report** (ekspor PDF). Provider
  LLM: **Google Gemini** (`gemini-2.5-flash-lite`); RAG memakai **vector store lokal**
  (numpy + embedding `gemini-embedding-001`). Setiap output AI wajib menyertakan
  _disclaimer_.

```
┌─────────────────────────┐         REST/JSON          ┌──────────────────────────┐
│  Frontend (Next.js 16)   │  ───────────────────────►  │  Backend (FastAPI)        │
│  Vercel                  │   /screener[/all], /ranking│  Railway                  │
│                          │   /strategies, /strategy-  │                           │
│  • Dashboard (IHSG)      │     matrix, /strength,     │  • Data pipeline (Yahoo)  │
│  • Screener + panel P3   │   /forecast, /explain,/why,│  • 9 strategi (registry)  │
│  • Strategies (matrix)   │   /fundamentals, /risk,    │  • Composite/AI/Risk/S&R  │
│  • Quant (P4 dashboard)  │   /stock-report, /history, │  • Forecast 1D/5D/20D (ML)│
│  • Backtest              │   /performance,/equity-    │  • Quant engine (P4)      │
│                          │     curve,/benchmark,      │  • APScheduler (WIB)      │
│                          │   /replay,/risk-profile,   │                           │
│                          │   /monte-carlo,/walkforward│                           │
│                          │   /correlation, /portfolio-│                           │
│                          │     builder (POST)         │                           │
└─────────────────────────┘                            └────────────┬──────────────┘
                                                                     │
                                       ┌─────────────────────────────┼───────────────┐
                                       ▼                             ▼                ▼
                                 PostgreSQL (Railway)       Redis (Upstash)     ONNX models
                                 market_data, stocks,       cache: harga,       model.onnx +
                                 fundamentals(+derived),    indikator, ranking, forecast_{1,5,20}d
                                 strategy_results,          matrix, report,     (RandomForest CPU)
                                 strength_score, forecast,  quant (benchmark,
                                 screening_history, breadth,  correlation, MC)
                                 replay_history,
                                 strategy_performance,
                                 equity_curve,
                                 correlation_matrix, portfolio
```

---

## Tampilan - Vestigo & Mode Lite/Pro

Desain mengikuti _handoff_ Claude Design: tema gelap **"quiet trading terminal"** -
tenang, padat-informasi, warna **hanya untuk makna** (hijau naik · merah turun ·
risiko). Tipografi **Inter** (UI) + **JetBrains Mono** dengan _tabular figures_ untuk
**semua angka** (harga, persen, skor, volume) sebagai _signature_ aplikasi; aksen
**bronze** `#C19A6B` di atas latar `#111111`, border tipis, tanpa gradient/shadow tebal.

Satu **toggle Lite / Pro** mengatur kedalaman setiap halaman:

- **Lite** - menjawab _"apa & seberapa yakin"_: 3 menu (**Dashboard · Screener · AI**),
  permukaan ringkas yang sudah dikurasi & langsung bisa ditindaklanjuti. Default untuk
  pengguna baru.
- **Pro** - menjawab _"kenapa, seberapa terbukti, bagaimana menyusunnya"_: 6 menu
  (**+ Strategies · Quant · Backtest**) dan seluruh kedalaman analitik & angka mentah.

Berpindah mode me-_reflow_ navigasi & konten (bukan sekadar menyembunyikan elemen),
preferensi disimpan di `localStorage`, dan transisinya menghormati
`prefers-reduced-motion`. Setiap output AI tetap menyertakan _disclaimer_ wajib.

---

## Struktur Repo

```
pocket-screener/
├── frontend/   Next.js 16 (App Router) · React 19 · Tailwind v4   → Vercel
├── backend/    FastAPI · SQLAlchemy · ONNX Runtime · APScheduler  → Railway
└── README.md   (file ini)
```

- **Vercel** harus diset **Root Directory = `frontend`**.
- **Backend** men-deploy folder `backend/` ke Railway.
- Database & cache memakai layanan cloud: **Railway Postgres** (produksi) & **Upstash** (Redis). Dev bisa pakai Postgres lokal/Neon.

---

## Fitur Utama

### Phase 2

| Fitur | Endpoint | Keterangan |
| ----- | -------- | ---------- |
| **Screener BSJP & BPJS** | `GET /api/screener` | Dua strategi intraday, kriteria + skor, level Entry/SL/TP, hasil disimpan ke `screening_history`. |
| **Composite Score / Ranking** | `GET /api/ranking` | Skor gabungan 0-100 (Technical 30% · Momentum 25% · Volume 20% · Volatility 10% · ML 15%). |
| **AI Stock Report** | `GET /api/stock-report/{ticker}` | Sentimen Bullish/Bearish, faktor pendukung & risiko, AI Confidence. |
| **Risk Meter** | `GET /api/risk/{ticker}` | Volatilitas, ATR%, Max Drawdown, Beta → Low/Medium/High. |
| **Support & Resistance** | `GET /api/support-resistance/{ticker}` | Swing High/Low, Pivot Point, ATR Band, Breakout Zone. |
| **Market Breadth** | `GET /api/market-breadth` | Naik/turun, Bullish Ratio, Top Gainers/Losers, performa sektor. |
| **Screener History** | `GET /api/history` | Riwayat lolos screener + tracking performa N hari + winrate per strategi. |
| **Market Data** | `GET /api/market-data/{ticker}` | OHLCV + indikator pre-computed (untuk chart). |

### Phase 3 - Multi-Strategy & Explainable

| Fitur | Endpoint | Keterangan |
| ----- | -------- | ---------- |
| **Daftar strategi** | `GET /api/strategies` | Metadata 9 strategi (5 teknikal + 4 fundamental). |
| **Screener 1 strategi** | `GET /api/screener?strategy={name}` | Kandidat 1 strategi + `matched_criteria` (alasan konkret). |
| **Screener semua strategi** | `GET /api/screener/all` | Jalankan 9 strategi sekaligus → tabel `strategy_results`. |
| **Strategy Matrix** | `GET /api/strategy-matrix` | Matriks saham × strategi (lolos / gagal / tak dinilai). |
| **Strength Score** | `GET /api/strength/{ticker}` | Skor kekuatan lintas-strategi 0-100 (bobot configurable). |
| **Probability Forecast** | `GET /api/forecast/{ticker}` | P(return > 0) untuk 1D/5D/20D + confidence + disclaimer. |
| **Explainable AI** | `GET /api/explain/{ticker}` | Confidence + bullish factors + risk factors. |
| **Explain Why Selected** | `GET /api/why/{ticker}` | Strategi yang cocok + alasan per-kriteria yang benar-benar lolos. |
| **Data fundamental** | `GET /api/fundamentals/{ticker}` | Laporan keuangan + metrik turunan (PE/PBV/MarketCap) + growth. |

**9 strategi screening** (via _Strategy Registry_ pluggable):

- **Teknikal:** BSJP · BPJS · Breakout · Trend Following · Potential Reversal
- **Fundamental:** High Growth · Turnaround · Timeless · Cash Rich

### Phase 4 - Quant Analytics & Validation

Memvalidasi **5 strategi teknikal** (BSJP · BPJS · Breakout · Trend Following ·
Potential Reversal) atas **histori 10 tahun** yang direkonstruksi _point-in-time_
(anti _look-ahead_), dengan asumsi biaya **0,3% per trade**.

| Fitur | Endpoint | Keterangan |
| ----- | -------- | ---------- |
| **Market Replay** | `GET /api/replay/{date}` | Kandidat tiap strategi pada tanggal historis + return forward (+1/+3/+7/+30 hari). |
| **Performance Metrics** | `GET /api/performance/{strategy}` | CAGR · Sharpe · Sortino · Calmar · Profit Factor · Recovery Factor · Max Drawdown · Winrate. |
| **Strategy Benchmark** | `GET /api/benchmark` | Semua strategi berdampingan vs **IHSG** (buy & hold) - apakah mengalahkan pasar? |
| **Equity Curve** | `GET /api/equity-curve/{strategy}` | Pertumbuhan modal + high-water mark + drawdown per tanggal. |
| **Risk Exposure** | `GET /api/risk-profile/{strategy}` | Volatilitas · Beta vs IHSG · Max DD · Losing Streak → Low/Medium/High (per **strategi**). |
| **Correlation Matrix** | `GET /api/correlation?universe=lq45` | Korelasi Pearson return harian (universe terbatas) untuk diversifikasi. |
| **Monte Carlo** | `GET /api/monte-carlo/{strategy}` | Bootstrap return historis → Probability of Profit, P5/median/P95, histogram. |
| **Walk-Forward** | `GET /api/walkforward/{strategy}` | Uji konsistensi out-of-sample per tahun (deteksi ketergantungan rezim). |
| **Portfolio Builder** | `POST /api/portfolio-builder` | Alokasi otomatis per profil risiko (Composite Score + Risk Meter + Correlation). |

> **Metodologi:** return series memakai **rebalancing kohort non-overlap** (blok
> 30 hari bursa, basket equal-weight) - adil terhadap biaya & tanpa _volatility
> drag_ sintetis. IHSG dihitung _buy & hold_ tanpa biaya. Semua hasil disertai
> _disclaimer_ (alat bantu analisis/edukasi, bukan rekomendasi).

**Scheduler harian (WIB / Asia-Jakarta):** 07:00 update data · **07:15 refresh
fundamental** · **07:30 jalankan 9 strategi** · 09:30 & 10:00 & 15:30 screener ·
16:00 ranking · **16:15 forecast** · **16:30 strength score** · 17:00 AI report ·
**18:00 performance + benchmark + equity curve** · **19:00 correlation** ·
**20:00 Monte Carlo** · **20:30 refresh knowledge base · 21:00 AI Analysis · 21:30
Market Narrator · 22:00 AI Daily Report** (Phase 5) · **Sabtu 06:00 update
fundamental · 07:00 refresh trade log · 08:00 walk-forward** (mingguan).

---

### Phase 5 - AI Financial Analyst

Lapisan LLM (**Google Gemini**, free tier) yang **menarasikan** data sistem.
**Grounding** dijaga ketat: konsep diambil dari **RAG** (knowledge base lokal),
**angka** diambil _live_ via _tool call_ ke endpoint Phase 1-4 - LLM tak pernah
mengarang angka. Setiap output menyertakan _disclaimer_.

| Fitur | Endpoint | Keterangan |
| ----- | -------- | ---------- |
| **AI Analyst Engine** | `GET /api/ai-analysis/{ticker}` | Ringkasan + bullish/risk factors + confidence (= Composite Score sistem). |
| **Explainable AI 2.0** | `GET /api/explain-score/{ticker}` | Breakdown kontribusi tiap komponen Composite Score + narasi. |
| **Chat With Stock** | `POST /api/chat` | Tanya-jawab bahasa alami (RAG + tool call), **streaming**, multi-giliran, scope guardrail. |
| **Natural Language Screener** | `POST /api/natural-query` | Prompt → filter terstruktur → **engine screener Phase 3 yang eksekusi** (LLM hanya buat filter). |
| **AI Strategy Comparator** | `GET /api/compare-strategy?a=&b=` | Bandingkan 2 strategi teknikal (metrik Phase 4) + narasi tradeoff. |
| **Portfolio AI Advisor** | `POST /api/portfolio-advisor` | Alokasi (Portfolio Builder Phase 4) + penjelasan AI kenapa tiap bobot. |
| **Market Narrator** | `GET /api/market-summary` | Narasi kondisi pasar (breadth + rotasi sektor + benchmark). |
| **AI Daily Report** | `GET /api/daily-report?format=json\|markdown\|pdf` | Top Opportunities, sektor, high-confidence, risk warning + ekspor **PDF**. |

> Prasyarat **Sector Rotation** (`GET /api/sector-rotation`) - kekuatan relatif &
> rotasi sektor (1M/3M/6M vs IHSG) - diimplementasikan di Phase 5 (Day 2) karena
> dipakai AI Analyst & Market Narrator. Generasi batch (analisis/narator/report)
> dijadwalkan **malam** lalu di-cache; hanya Chat & NL Screener yang _real-time_.

---

## Halaman Frontend

Navigasi & kedalaman tiap halaman mengikuti **mode Lite/Pro** (lihat
[Tampilan & Mode Lite/Pro](#tampilan--vestigo--mode-litepro)) - **Strategies**,
**Quant**, dan **Backtest** hanya muncul di mode **Pro**.

- **Dashboard (`/`)** - konteks pasar **IHSG** (Indeks Harga Saham Gabungan):
  candlestick + AI Report + Risk Meter + Support/Resistance. Simbol terkunci ke IHSG.
- **Screener (`/screener`)** - Market Breadth, tabel screener BSJP/BPJS, chart &
  analitik saham terpilih (AI/Risk/S&R), **Probability Forecast**, **Strength
  Score**, **Explain Panel** (Explainable AI + Why Selected), Composite Score, dan
  Screener History.
- **Strategies (`/strategies`)** - pemilih 9 strategi, hasil per-strategi dengan
  `matched_criteria`, dan **Strategy Comparison Matrix**.
- **Quant (`/quant`)** - dashboard validasi kuantitatif Phase 4: **Strategy
  Benchmark** (vs IHSG), **Equity Curve** + **Monte Carlo**, **Risk Exposure**,
  **Correlation Heatmap**, **Market Replay**, dan **Portfolio Builder**.
- **AI (`/ai`)** - dashboard AI Financial Analyst Phase 5: **Market Narrator**,
  **AI Daily Report** (+ unduh PDF), **Chat With Stock** (streaming), **AI Analyst**
  & **Explainable AI 2.0** per saham, **Strategy Comparator**, dan **Portfolio AI
  Advisor**.
- **Backtest (`/backtest`)** - winrate, cumulative return, drawdown, metrik model.

---

## Menjalankan Secara Lokal

Butuh **Python 3.11** dan **Node.js 20+**.

**1. Backend** (terminal 1)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env               # isi DATABASE_URL (Neon) & REDIS_URL (Upstash)
python -m app.db.init_db             # buat tabel + seed daftar saham
python -m app.core.market_data --range 10y  # ingest OHLCV 10 tahun + indikator
python -m app.data.fundamentals_fetch        # ingest data fundamental (Yahoo)
python -m app.data.fundamentals_derived      # hitung metrik fundamental harian
uvicorn app.main:app --reload --port 8000
```

> **Phase 4 - rekonstruksi histori (sekali, offline).** Setelah ingest 10 tahun,
> bangun trade log untuk fitur quant:
>
> ```powershell
> python -m app.quant.reconstruct        # jalankan 5 strategi point-in-time → strategy_results
> python -m app.quant.forward_returns    # hitung return forward → replay_history
> ```
>
> Endpoint quant (benchmark, equity curve, dst.) lalu menghitung dari trade log
> ini; job malam scheduler menyegarkannya otomatis.

> **Model forecast** (`forecast_{1,5,20}d.onnx`) sudah disertakan di repo. Untuk
> melatih ulang: `pip install scikit-learn skl2onnx` lalu
> `python -m app.ml.train_forecast` (offline, butuh market_data ≥ 2 tahun).

> **Phase 5 - lapisan AI (opsional).** Set `GEMINI_API_KEY` di `.env` (gratis dari
> [Google AI Studio](https://aistudio.google.com/apikey)) lalu seed knowledge base
> RAG: `python -m app.rag.knowledge_base`. Tanpa key, fitur AI nonaktif aman-gagal
> (endpoint lain tetap jalan). Vector store RAG memakai **file lokal** (numpy), bukan
> infrastruktur tambahan.

**2. Frontend** (terminal 2)

```bash
cd frontend
npm install
npm run dev
```

Buka http://localhost:3000. Frontend membaca `NEXT_PUBLIC_API_BASE_URL`
(default `http://localhost:8000`, jadi jalan tanpa konfigurasi tambahan).

---

## Deployment (Produksi)

Vestigo berjalan di **Vercel** (frontend) + **Railway** (backend + Postgres) +
**Upstash** (Redis) + **Google Gemini** (LLM). Backend di-deploy via `backend/Dockerfile`
(sudah menangani `$PORT` Railway); frontend adalah app Next.js standar.

**1. Backend → Railway**
- Tambah plugin **Postgres** (otomatis menyediakan `DATABASE_URL`).
- Buat service dari repo → **Root Directory = `backend`** (auto-deteksi Dockerfile).
- **Settings → Networking → Generate Domain** (URL backend publik).
- **Variables:**

  | Variable | Nilai |
  | -------- | ----- |
  | `DATABASE_URL` | `${{ Postgres.DATABASE_URL }}` |
  | `REDIS_URL` | `rediss://default:<PASSWORD>@<host>.upstash.io:6379` |
  | `GEMINI_API_KEY` | API key Google AI Studio |
  | `CORS_ORIGINS` | URL Vercel **tanpa** trailing slash, mis. `https://<app>.vercel.app` |
  | `ENVIRONMENT` | `production` |
  | `SCHEDULER_ENABLED` | `false` saat isi data awal, lalu `true` (job malam mengisi & cache) |

**2. Isi data ke Postgres Railway** (sekali, dari lokal - arahkan `DATABASE_URL` ke
`DATABASE_PUBLIC_URL` Railway, host `…proxy.rlwy.net`):

```powershell
$env:DATABASE_URL  = "<DATABASE_PUBLIC_URL Railway>"
$env:GEMINI_API_KEY = "<key>"
python -m app.db.init_db                      # buat tabel + seed 81 saham
python -m app.core.market_data --range 10y    # ingest OHLCV + indikator
python -m app.data.fundamentals_fetch ; python -m app.data.fundamentals_derived
python -m app.quant.reconstruct ; python -m app.quant.forward_returns
python -m app.rag.knowledge_base              # seed RAG (vector store lokal)
```

**3. Frontend → Vercel**
- Import repo → **Root Directory = `frontend`** (preset **Next.js**, bukan "Services").
- Env **`NEXT_PUBLIC_API_BASE_URL`** = URL backend Railway.
- Deploy → catat URL, lalu set `CORS_ORIGINS` backend ke URL tsb. → redeploy backend.

> **Catatan:** (a) `NEXT_PUBLIC_API_BASE_URL` di-_bake_ saat build - pastikan terisi
> sebelum deploy. (b) Hindari `.npmrc` berisi `script-shell=powershell` di repo -
> menggagalkan `npm install` di Linux Vercel. (c) Tier gratis: endpoint berat
> (Screener/Ranking) lambat di pemuatan pertama (cold start ONNX) lalu di-cache.

---

## Tech Stack

| Area | Teknologi |
| ---- | --------- |
| Frontend | Next.js 16 (App Router) · React 19 · Tailwind CSS v4 · Lightweight-charts · Recharts · design tokens "Vestigo" (mode Lite/Pro) · font Inter + JetBrains Mono |
| Backend | FastAPI · SQLAlchemy 2.0 · APScheduler · httpx |
| Database | PostgreSQL - Railway (produksi) · lokal/Neon (dev) |
| Cache | Redis (Upstash) |
| ML | scikit-learn + skl2onnx (training offline) → ONNX → onnxruntime (inferensi server-side) |
| Forecast | 3 model RandomForest terkalibrasi (1D/5D/20D), binary classification P(return > 0) |
| Explainability | Rule-based (`matched_criteria`) + interpretasi fitur teknikal per-saham |
| Quant (P4) | numpy · pandas · scipy - backtest, performance metrics, Monte Carlo, korelasi, portfolio |
| AI (P5) | Google Gemini (`gemini-2.5-flash-lite`) via `google-genai` · embedding `gemini-embedding-001` · RAG vector store lokal (numpy) · fpdf2 (ekspor PDF) |
| Deploy | Vercel (frontend) · Railway (backend) |

Detail tiap bagian: **[backend/README.md](backend/README.md)** dan
**[frontend/README.md](frontend/README.md)**.

---

## Kontribusi & Pengembangan

Dikembangkan oleh **Anak Agung Aryadipa Aditya Nugraha**
([@adiityanugraha](https://github.com/adiityanugraha)).

Backend **Phase 2** (data pipeline, composite score, AI report, risk meter,
support/resistance, market breadth, screener history, scheduler), **Phase 3**
(Strategy Registry 9 strategi, data fundamental, Strategy Matrix, Strength Score,
Probability Forecast, Explainable AI), & **Phase 4** (rekonstruksi histori
point-in-time, Market Replay, performance metrics, benchmark, equity curve, Monte
Carlo, walk-forward, correlation, portfolio builder, Quant dashboard), & **Phase 5**
(lapisan AI Financial Analyst: Sector Rotation, RAG + grounding, AI Analyst,
Explainable AI 2.0, Chat With Stock, NL Screener, Strategy Comparator, Portfolio
Advisor, Market Narrator, AI Daily Report, AI Analyst Dashboard), **integrasi
frontend ke REST API**, serta **redesign & rebranding Vestigo** (design system bronze
"quiet trading terminal", mode Lite/Pro, dari _handoff_ Claude Design), dikerjakan
dengan bantuan **Claude
(Anthropic)** sebagai AI pair-programmer melalui Claude Code - sehingga "Claude"
tercatat sebagai _contributor_ pada riwayat Git repositori ini.

---

## Lisensi

© 2026 Anak Agung Aryadipa Aditya Nugraha. Dirilis di bawah
**[MIT License](LICENSE)** - bebas dipakai/dimodifikasi selama mencantumkan
notice hak cipta & lisensi ini.
