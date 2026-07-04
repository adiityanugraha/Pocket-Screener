"""Retrieval-Augmented Generation (RAG) - Phase 5.

Memberi LLM KONTEKS DOMAIN statis (definisi indikator, arti 9 strategi, cara
membaca metrik quant, konsep breadth/S-R/risk) agar jawaban tidak generik.
Pembagian peran tegas (anti-halusinasi):
  - Vector store menyimpan PENJELASAN/KONSEP (statis, di-embed sekali).
  - ANGKA aktual TIDAK di-embed - diambil live via tool call (app/ai/tools.py)
    agar selalu mutakhir & akurat.

Vector store = pgvector di Neon (extension PostgreSQL) - tanpa infra baru.
Embedding = Gemini text-embedding-004 (provider sama dengan LLM).

Modul ditambahkan per hari sesuai Step_by_Step_Phase5:

  vector_store.py   (Day 3)   tabel knowledge_base (kolom embedding vector) + query
  embeddings.py     (Day 3)   encode teks -> vektor (Gemini text-embedding-004)
  knowledge_base.py (Day 3)   seed & index dokumen konsep ke vector store
  retriever.py      (Day 4)   ambil konteks relevan dari vector store per query
"""
