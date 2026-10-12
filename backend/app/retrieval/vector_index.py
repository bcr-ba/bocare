"""Vector index: chunk embeddings stored as one matrix, searched exactly with a matrix product.

At a few thousand chunks this is faster and simpler than a vector database, which only pays off
(through approximate search) at millions of vectors. Each embedding model gets its own folder:

    <index_dir>/<model>/vectors.npy   one normalised row per chunk
                        chunks.jsonl  the chunks, in the same order as the rows
                        meta.json     model, size, corpus fingerprint, build date
"""
import hashlib
import json
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

import numpy as np

from app.retrieval.corpus import Chunk, read_chunks
from app.retrieval.embeddings import Embedder


class VectorIndexError(Exception):
    """The index is missing or was built with another model or corpus."""


def model_folder(index_dir: Path, model_name: str) -> Path:
    return index_dir / re.sub(r"[^\w.-]", "_", model_name)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class VectorIndex:
    chunks: List[Chunk]
    vectors: np.ndarray  # shape (len(chunks), dim), rows normalised
    model_name: str

    def search(self, query_vector: np.ndarray, top: int) -> List[Tuple[Chunk, float]]:
        """The `top` chunks closest to the query, best first, with their cosine similarity."""
        scores = self.vectors @ query_vector
        top = min(top, len(scores))
        best = np.argpartition(-scores, top - 1)[:top]
        best = best[np.argsort(-scores[best])]
        return [(self.chunks[i], float(scores[i])) for i in best]

    # ---- persistence ----------------------------------------------------------------------------

    @classmethod
    def build(cls, chunks_file: Path, embedder: Embedder, index_dir: Path) -> "VectorIndex":
        chunks = list(read_chunks(chunks_file))
        started = time.perf_counter()
        vectors = embedder.embed_documents([c.embedding_text for c in chunks])
        folder = model_folder(index_dir, embedder.model_name)
        folder.mkdir(parents=True, exist_ok=True)
        np.save(folder / "vectors.npy", vectors)
        shutil.copyfile(chunks_file, folder / "chunks.jsonl")
        (folder / "meta.json").write_text(json.dumps({
            "model": embedder.model_name,
            "dim": int(vectors.shape[1]),
            "count": len(chunks),
            "chunks_sha256": file_sha256(chunks_file),
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "build_seconds": round(time.perf_counter() - started, 1),
        }, indent=2), encoding="utf-8")
        return cls(chunks, vectors, embedder.model_name)

    @classmethod
    def load(cls, index_dir: Path, model_name: str) -> "VectorIndex":
        folder = model_folder(index_dir, model_name)
        if not (folder / "meta.json").exists():
            raise VectorIndexError(f"No index for {model_name} in {folder}. Build it: python scripts/build_index.py")
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        chunks = list(read_chunks(folder / "chunks.jsonl"))
        vectors = np.load(folder / "vectors.npy")
        if meta["model"] != model_name or len(chunks) != vectors.shape[0]:
            raise VectorIndexError(f"Index in {folder} is inconsistent; rebuild it: python scripts/build_index.py")
        return cls(chunks, vectors, model_name)
