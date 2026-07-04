"""Knowledge base RAG - dokumen KONSEP statis (Phase 5 Day 3).

Sumber penjelasan domain agar jawaban LLM tidak generik: definisi indikator,
arti 9 strategi, makna metrik quant, dan konsep analitik. Hanya PENJELASAN yang
di-embed di sini; ANGKA aktual TIDAK disimpan - diambil live via tool call
(Day 4) agar selalu mutakhir & akurat (anti-halusinasi).

Jalankan untuk seed/index ke vector store lokal (butuh GEMINI_API_KEY):
    python -m app.rag.knowledge_base

Dokumen sengaja ringkas (1-3 kalimat) & berbahasa Indonesia, selaras UI app.
"""

from __future__ import annotations

from app.rag import embeddings, vector_store

# (id, source, title, content). source: indicator | strategy | quant | concept
DOCUMENTS: list[dict[str, str]] = [
    # ----------------------------- INDIKATOR ----------------------------- #
    {"id": "ind_rsi", "source": "indicator", "title": "RSI (Relative Strength Index)",
     "content": "RSI mengukur kecepatan & besaran perubahan harga pada skala 0-100. Di atas 70 sering dianggap overbought (rawan koreksi), di bawah 30 oversold (rawan pantulan). RSI ~50 menunjukkan momentum netral."},
    {"id": "ind_macd", "source": "indicator", "title": "MACD (Moving Average Convergence Divergence)",
     "content": "MACD = selisih EMA cepat dan EMA lambat, dibandingkan garis sinyal. MACD memotong sinyal dari bawah ke atas (golden cross) = momentum bullish; sebaliknya bearish. Histogram MACD menunjukkan kekuatan momentum."},
    {"id": "ind_bb", "source": "indicator", "title": "Bollinger Bands",
     "content": "Pita atas/bawah berjarak beberapa standar deviasi dari MA tengah (umumnya 20 hari). Harga menyentuh pita atas = relatif mahal/volatil tinggi; pita menyempit = volatilitas rendah (sering mendahului breakout)."},
    {"id": "ind_atr", "source": "indicator", "title": "ATR (Average True Range)",
     "content": "ATR mengukur rata-rata rentang pergerakan harga (volatilitas), bukan arah. ATR tinggi = ayunan harga besar, dipakai untuk menetapkan stop loss & ukuran posisi yang sadar-risiko."},
    {"id": "ind_vwap", "source": "indicator", "title": "VWAP (Volume Weighted Average Price)",
     "content": "Harga rata-rata tertimbang volume sepanjang periode. Harga di atas VWAP = pembeli mengendalikan (bullish bias); di bawah VWAP = penjual dominan."},
    {"id": "ind_vol_ma", "source": "indicator", "title": "Volume MA 20",
     "content": "Rata-rata volume 20 hari, acuan likuiditas & lonjakan. Volume hari ini jauh di atas Volume MA 20 = minat tak biasa, sering menyertai breakout atau berita."},
    {"id": "ind_price_ma", "source": "indicator", "title": "Moving Average harga (MA5/20/50/100/200)",
     "content": "Rata-rata harga pada beberapa periode untuk membaca tren. Susunan MA pendek di atas MA panjang (MA20>MA50>MA100>MA200) = tren naik sehat; harga di atas MA200 = bias jangka panjang bullish."},

    # ----------------------------- STRATEGI ------------------------------ #
    {"id": "strat_bsjp", "source": "strategy", "title": "Strategi BSJP (Beli Sore Jual Pagi)",
     "content": "Strategi teknikal jangka sangat pendek: cari saham yang hari ini menguat >=5% dari harga sebelumnya, di atas MA5, dengan volume naik >=1.2x dan nilai transaksi > 5 miliar. Ide: momentum sore berlanjut ke sesi pagi berikutnya."},
    {"id": "strat_bpjs", "source": "strategy", "title": "Strategi BPJS (Beli Pagi Jual Sore)",
     "content": "Strategi intraday: harga di atas MA5 & Open, menguat >=5% dari harga sebelumnya, dengan nilai transaksi > 5 miliar. Ide: kekuatan pagi diteruskan hingga sesi sore di hari yang sama."},
    {"id": "strat_breakout", "source": "strategy", "title": "Strategi Breakout",
     "content": "Mencari saham menembus ke atas dengan konfirmasi volume: harga naik, volume di atas Volume MA 20, Volume MA 20 likuid (>300 juta), harga > 100. Ide: awal pergerakan tren baru setelah konsolidasi."},
    {"id": "strat_trend", "source": "strategy", "title": "Strategi Trend Following",
     "content": "Mengikuti tren mapan: harga > MA20 > MA50 > MA100 > MA200 dengan likuiditas memadai. Ide: 'tren adalah teman' - ikut arah selama susunan MA tetap rapi."},
    {"id": "strat_reversal", "source": "strategy", "title": "Strategi Potential Reversal",
     "content": "Mencari saham keluar dari fase koreksi: harga mulai naik di atas MA10 sementara MA20 masih di atasnya, disertai volume di atas Volume MA 20. Ide: menangkap awal pembalikan arah, berisiko lebih tinggi."},
    {"id": "strat_high_growth", "source": "strategy", "title": "Strategi High Growth (fundamental)",
     "content": "Perusahaan bertumbuh cepat: pertumbuhan Revenue 3-tahun & YoY >=10%, sales growth streak >=3, likuiditas memadai. Catatan: belum divalidasi historis karena keterbatasan data fundamental point-in-time."},
    {"id": "strat_turnaround", "source": "strategy", "title": "Strategi Turnaround (fundamental)",
     "content": "Perusahaan mulai pulih: laba bersih tumbuh, PE annualised murah relatif terhadap PE biasa, revenue YoY membaik. Cocok untuk pemburu pemulihan kinerja. Belum divalidasi historis (data fundamental terbatas)."},
    {"id": "strat_timeless", "source": "strategy", "title": "Strategi Timeless (fundamental)",
     "content": "Compounder jangka panjang berkualitas: rata-rata RoE 5thn >=10%, laba besar & ekuitas kuat, streak dividen >=5thn, dividend yield >=2%. Belum divalidasi historis (butuh histori panjang & data fundamental)."},
    {"id": "strat_cash_rich", "source": "strategy", "title": "Strategi Cash Rich (fundamental)",
     "content": "Neraca sangat kuat: kas >=0.7x market cap, utang < 0.5x kas, PBV positif. Ide: margin keamanan tinggi dari kas berlimpah. Belum divalidasi historis (data fundamental terbatas)."},

    # --------------------------- METRIK QUANT ---------------------------- #
    {"id": "quant_cagr", "source": "quant", "title": "CAGR (Compound Annual Growth Rate)",
     "content": "Pertumbuhan majemuk tahunan rata-rata dari kurva ekuitas. Meratakan naik-turun menjadi satu angka 'berapa % per tahun'. Makin tinggi makin baik, tapi harus dibaca bersama risiko (drawdown/Sharpe)."},
    {"id": "quant_maxdd", "source": "quant", "title": "Max Drawdown",
     "content": "Penurunan terdalam dari puncak ke lembah pada kurva ekuitas (nilai negatif). Mengukur 'seberapa sakit' saat terburuk. -50% berarti modal pernah turun separuh dari puncaknya."},
    {"id": "quant_sharpe", "source": "quant", "title": "Sharpe Ratio",
     "content": "Return di atas suku bunga bebas risiko dibagi volatilitas total. Mengukur imbal hasil per unit risiko. >1 dianggap baik, ~0.3 modest; makin tinggi makin efisien."},
    {"id": "quant_sortino", "source": "quant", "title": "Sortino Ratio",
     "content": "Mirip Sharpe tetapi hanya menghukum volatilitas SISI BAWAH (downside). Lebih adil untuk strategi yang ayunannya banyak di sisi positif."},
    {"id": "quant_calmar", "source": "quant", "title": "Calmar Ratio",
     "content": "CAGR dibagi |Max Drawdown|. Mengukur imbal hasil relatif terhadap nyeri terburuk. Makin tinggi = pertumbuhan baik dengan drawdown terkendali."},
    {"id": "quant_profit_factor", "source": "quant", "title": "Profit Factor",
     "content": "Total profit kotor dibagi total loss kotor. >1 berarti menguntungkan; 1.5-2 tergolong solid. Di bawah 1 berarti rugi bersih."},
    {"id": "quant_recovery", "source": "quant", "title": "Recovery Factor",
     "content": "Laba bersih dibagi |Max Drawdown|. Menunjukkan seberapa cepat strategi memulihkan kerugian terburuknya."},
    {"id": "quant_winrate", "source": "quant", "title": "Winrate",
     "content": "Persentase trade yang untung. Winrate tinggi belum tentu profit besar (tergantung ukuran menang vs kalah); baca bersama Profit Factor."},

    # ------------------------------ KONSEP ------------------------------- #
    {"id": "concept_breadth", "source": "concept", "title": "Market Breadth",
     "content": "Konteks pasar menyeluruh: berapa saham naik vs turun, Bullish Ratio, top gainers/losers, performa per sektor. Membantu menilai apakah kenaikan merata atau hanya segelintir saham."},
    {"id": "concept_sector_rotation", "source": "concept", "title": "Sector Rotation",
     "content": "Mengukur kekuatan relatif tiap sektor pada beberapa horizon (1M/3M/6M) dibanding IHSG, plus arah rotasi (LEADING/WEAKENING/LAGGING/IMPROVING). Membantu melihat ke mana aliran dana sektor bergerak."},
    {"id": "concept_sr", "source": "concept", "title": "Support & Resistance",
     "content": "Support = area harga yang cenderung menahan penurunan; Resistance = area yang menahan kenaikan. Dipakai untuk menentukan entry, take profit, stop loss, dan zona breakout."},
    {"id": "concept_risk_meter", "source": "concept", "title": "Risk Meter (per saham)",
     "content": "Klasifikasi risiko saham (Low/Medium/High) dari ATR, volatilitas historis, drawdown, dan beta. Membantu menyesuaikan pilihan dengan profil risiko investor."},
    {"id": "concept_composite", "source": "concept", "title": "Composite Score",
     "content": "Skor gabungan 0-100 dari beberapa komponen berbobot: Technical 30%, Momentum 25%, Volume 20%, Volatility 10%, ML Prediction 15%. Menyederhanakan banyak indikator jadi satu angka peringkat."},
    {"id": "concept_forecast", "source": "concept", "title": "Probability Forecast",
     "content": "Probabilitas return positif pada horizon 1 hari / 5 hari / 20 hari dari model ML, plus tingkat keyakinan (Low/Medium/High). Lebih intuitif daripada sekadar skor."},
    {"id": "concept_strength", "source": "concept", "title": "Screener Strength Score",
     "content": "Skor kekuatan menyeluruh 0-100 yang melihat LINTAS strategi: berapa banyak strategi yang dilewati sebuah saham dan bobotnya. Berbeda dari Composite Score yang fokus indikator."},
    {"id": "concept_monte_carlo", "source": "concept", "title": "Monte Carlo Simulation",
     "content": "Resample (bootstrap) return historis ribuan kali untuk memetakan sebaran kemungkinan hasil setahun ke depan: probability of profit, skenario terburuk (P5), median, terbaik (P95). Bukan jaminan - berbasis asumsi pola historis berulang."},
    {"id": "concept_walkforward", "source": "concept", "title": "Walk-Forward Backtesting",
     "content": "Menguji strategi pada periode yang tidak dipakai saat penyetelan (out-of-sample) dengan jendela bergeser. Untuk strategi rule-based, berguna menguji KONSISTENSI performa antar tahun (deteksi overfitting)."},
    {"id": "concept_correlation", "source": "concept", "title": "Correlation Matrix",
     "content": "Korelasi pergerakan return antar saham (Pearson). Korelasi tinggi = bergerak seragam; memilih saham berkorelasi rendah membantu diversifikasi portofolio."},
    {"id": "concept_portfolio", "source": "concept", "title": "Portfolio Builder",
     "content": "Menyusun alokasi bobot portofolio sesuai profil risiko (Conservative/Moderate/Aggressive) dengan mempertimbangkan kualitas (Composite Score), risiko (Risk Meter), dan diversifikasi (korelasi). Alat bantu, bukan nasihat keuangan."},
]


def seed(store: vector_store.LocalVectorStore | None = None) -> int:
    """Embed seluruh DOCUMENTS dan simpan ke vector store lokal. Kembalikan jumlah dokumen."""
    if not embeddings.is_available():
        from app.ai.llm_client import LLMError

        raise LLMError("Lapisan AI nonaktif (GEMINI_API_KEY belum diisi) - tak bisa seed KB.")
    store = store or vector_store.get_store()
    # Embed gabungan judul + isi agar query cocok ke keduanya.
    contents = [f"{d['title']}. {d['content']}" for d in DOCUMENTS]
    vectors = embeddings.embed_documents(contents)
    store.replace(DOCUMENTS, vectors)
    store.save()
    return len(DOCUMENTS)


def search(query: str, top_k: int = 4) -> list[dict]:
    """Cari konsep relevan untuk query (delegasi ke rag.retriever)."""
    from app.rag import retriever

    return retriever.retrieve(query, top_k=top_k)


def main() -> None:
    print(f"Seeding {len(DOCUMENTS)} dokumen konsep ke vector store lokal...")
    n = seed()
    print(f"  OK: {n} dokumen ter-embed & tersimpan.")
    # Demo retrieval singkat.
    for q in ("apa itu sharpe ratio", "strategi breakout itu bagaimana"):
        hits = search(q, top_k=2)
        titles = [f"{h['title']} ({h['score']:.2f})" for h in hits]
        print(f"  query '{q}' -> {titles}")


if __name__ == "__main__":
    main()
