from __future__ import annotations

import json
import sqlite3
from functools import lru_cache

import numpy as np
from fastembed import TextEmbedding

from app.core.config import settings


@lru_cache(maxsize=1)
def embedding_model() -> TextEmbedding:
    return TextEmbedding(model_name=settings.embedding_model, cache_dir=str(settings.root / ".model_cache"))


class LocalVectorIndex:
    """Persistent exact cosine index for this small course corpus (about 500 chunks)."""

    def __init__(self) -> None:
        settings.vector_path.mkdir(parents=True, exist_ok=True)
        self.path = settings.vector_path / "vectors.sqlite3"
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS vectors (
                id TEXT PRIMARY KEY, document TEXT NOT NULL, metadata TEXT NOT NULL,
                dimension INTEGER NOT NULL, vector BLOB NOT NULL
            )""")

    def _connect(self):
        return sqlite3.connect(self.path)

    def count(self) -> int:
        with self._connect() as db:
            return db.execute("SELECT COUNT(*) FROM vectors").fetchone()[0]

    def get(self, include=None) -> dict:
        with self._connect() as db:
            return {"ids": [row[0] for row in db.execute("SELECT id FROM vectors")]}

    def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        with self._connect() as db:
            db.executemany("DELETE FROM vectors WHERE id=?", [(item,) for item in ids])

    def upsert(self, ids: list[str], documents: list[str], embeddings: list[list[float]], metadatas: list[dict]) -> None:
        records = []
        for item_id, document, vector, metadata in zip(ids, documents, embeddings, metadatas, strict=True):
            values = np.asarray(vector, dtype=np.float32)
            norm = np.linalg.norm(values)
            if norm:
                values /= norm
            records.append((item_id, document, json.dumps(metadata, ensure_ascii=False), len(values), values.tobytes()))
        with self._connect() as db:
            db.executemany("INSERT OR REPLACE INTO vectors (id,document,metadata,dimension,vector) VALUES (?,?,?,?,?)", records)

    def query(self, query_embeddings: list[list[float]], n_results: int, include=None, where: dict | None = None) -> dict:
        query = np.asarray(query_embeddings[0], dtype=np.float32)
        norm = np.linalg.norm(query)
        if norm:
            query /= norm
        with self._connect() as db:
            if where and "module" in where:
                rows = db.execute(
                    "SELECT id,document,metadata,dimension,vector FROM vectors "
                    "WHERE json_extract(metadata, '$.module') IN (?, '通用课程资料')",
                    (where["module"],),
                ).fetchall()
            else:
                rows = db.execute("SELECT id,document,metadata,dimension,vector FROM vectors").fetchall()
        scored = []
        for item_id, document, metadata, dimension, blob in rows:
            if dimension != len(query):
                continue
            vector = np.frombuffer(blob, dtype=np.float32)
            distance = 1.0 - float(np.dot(query, vector))
            scored.append((distance, item_id, document, json.loads(metadata)))
        scored.sort(key=lambda item: item[0])
        scored = scored[:n_results]
        return {"ids": [[item[1] for item in scored]], "documents": [[item[2] for item in scored]],
                "metadatas": [[item[3] for item in scored]], "distances": [[item[0] for item in scored]]}


@lru_cache(maxsize=1)
def collection() -> LocalVectorIndex:
    return LocalVectorIndex()


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return [vector.tolist() for vector in embedding_model().embed(texts, batch_size=32)]


def embed_query(query: str) -> list[float]:
    return next(embedding_model().query_embed(query)).tolist()
