"""Lapisan AI Pocket Screener - Phase 5 (AI Financial Analyst).

Orkestrasi LLM di ATAS seluruh data & perhitungan Phase 1-4. Prinsip inti =
GROUNDING: LLM hanya MENARASIKAN angka yang berasal dari endpoint/DB yang sudah
ada; LLM DILARANG mengarang angka/harga/metrik (anti-halusinasi). Setiap output
AI WAJIB menyertakan disclaimer (alat bantu analisis & edukasi, bukan nasihat
keuangan).

Modul ditambahkan per hari sesuai Step_by_Step_Phase5:

  llm_client.py        (Day 1)   wrapper provider LLM (Gemini), provider-agnostic
  tools.py             (Day 4)   definisi tool/function membungkus endpoint Phase 1-4
  prompt_builder.py    (Day 4)   susun prompt = sistem + konteks RAG + hasil tool
  guardrails.py        (Day 4)   batas cakupan + disclaimer wajib
  ai_analysis.py       (Day 5)   AI Analyst Engine -> ai_reports
  explain_score.py     (Day 6)   Explainable AI 2.0 (breakdown Composite Score)
  chat_engine.py       (Day 7-8) Chat With Stock (RAG + tools + history)
  natural_query.py     (Day 9)   Natural Language Screener
  strategy_comparator.py(Day 10) AI Strategy Comparator (5 strategi teknikal)
  portfolio_advisor.py (Day 11)  Portfolio AI Advisor
  market_narrator.py   (Day 12)  Market Narrator
  daily_report.py      (Day 13)  AI Daily Report

Provider: Google Gemini (free tier, model default gemini-2.5-flash). Wrapper
sengaja dibuat provider-agnostic agar pindah provider hanya mengubah llm_client.
"""
