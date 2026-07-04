"""Vector store LOKAL ringan (Phase 5 Day 3).

Pengganti pgvector: karena knowledge base RAG sangat kecil (~puluhan dokumen
konsep statis), tidak perlu extension DB/Docker. Vektor disimpan sebagai file
numpy + metadata JSON di disk, pencarian via cosine similarity (numpy). Cukup,
gratis, cepat, dan tidak menambah infrastruktur. (Bila kelak pindah ke container
pgvector, hanya modul ini yang diganti - antarmuka search() tetap.)

File persisten (di-gitignore, karena turunan dari knowledge_base.py):
  app/rag/data/knowledge_base.meta.json     -> daftar dokumen {id, source, title, content}
  app/rag/data/knowledge_base.vectors.npy   -> matriks vektor (N x D), sudah dinormalkan
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

DATA_DIR = Path(__file__).parent / "data"
META_PATH = DATA_DIR / "knowledge_base.meta.json"
VEC_PATH = DATA_DIR / "knowledge_base.vectors.npy"


def _normalize(matrix: np.ndarray) -> np.ndarray:
    """Normalkan tiap baris ke panjang 1 (untuk cosine = dot product)."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # hindari bagi nol
    return matrix / norms


class LocalVectorStore:
    def __init__(self, meta_path: Path = META_PATH, vec_path: Path = VEC_PATH) -> None:
        self.meta_path = meta_path
        self.vec_path = vec_path
        self.documents: list[dict[str, Any]] = []
        self.vectors: np.ndarray | None = None  # (N, D), ternormalkan

    def __len__(self) -> int:
        return len(self.documents)

    def replace(self, documents: list[dict[str, Any]], vectors: list[list[float]]) -> None:
        """Ganti seluruh isi store dengan dokumen + vektor baru (rebuild penuh)."""
        if len(documents) != len(vectors):
            raise ValueError("Jumlah dokumen dan vektor harus sama.")
        self.documents = list(documents)
        self.vectors = _normalize(np.asarray(vectors, dtype=np.float32)) if vectors else None

    def save(self) -> None:
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        self.meta_path.write_text(
            json.dumps(self.documents, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if self.vectors is not None:
            np.save(self.vec_path, self.vectors)

    def load(self) -> bool:
        """Muat dari disk. True bila berhasil, False bila file belum ada."""
        if not self.meta_path.exists() or not self.vec_path.exists():
            return False
        self.documents = json.loads(self.meta_path.read_text(encoding="utf-8"))
        self.vectors = np.load(self.vec_path)
        return True

    def search(self, query_vector: list[float], top_k: int = 4) -> list[dict[str, Any]]:
        """Kembalikan top_k dokumen termirip (cosine), tiap item + field 'score'."""
        if self.vectors is None or len(self.documents) == 0:
            return []
        q = np.asarray(query_vector, dtype=np.float32)
        norm = np.linalg.norm(q)
        if norm == 0:
            return []
        q = q / norm
        scores = self.vectors @ q  # (N,) cosine similarity
        k = min(top_k, len(self.documents))
        top_idx = np.argsort(-scores)[:k]
        results: list[dict[str, Any]] = []
        for i in top_idx:
            doc = dict(self.documents[int(i)])
            doc["score"] = float(scores[int(i)])
            results.append(doc)
        return results


# Singleton (lazy-load dari path default).
_store: LocalVectorStore | None = None


def get_store() -> LocalVectorStore:
    """Store default, otomatis dimuat dari disk pada akses pertama bila ada."""
    global _store
    if _store is None:
        _store = LocalVectorStore()
        _store.load()
    return _store


def reset_store() -> None:
    """Reset singleton (untuk testing / setelah re-seed)."""
    global _store
    _store = None
