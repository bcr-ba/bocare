"""Embedding models: turn text into vectors whose distance reflects meaning, across languages.

Vectors are L2-normalised, so the dot product of two vectors is their cosine similarity.
"""
from typing import List, Optional, Protocol, Sequence

import numpy as np
import requests

from app.core.settings import Settings, get_settings


class EmbeddingError(Exception):
    pass


class Embedder(Protocol):
    model_name: str

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        """One normalised row per text."""
        ...

    def embed_query(self, text: str) -> np.ndarray:
        """A normalised vector for a search query (may use a different prompt than documents)."""
        ...


def normalise(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


class OllamaEmbedder:
    """Embedding model served by Ollama (e.g. qwen3-embedding), through its /api/embed endpoint."""

    def __init__(self, settings: Optional[Settings] = None):
        s = settings or get_settings()
        self.model_name = s.embedding_model
        self.url = s.ollama_url.rstrip("/") + "/api/embed"
        self.instruction = s.embedding_query_instruction
        self.batch_size = s.embedding_batch_size
        self.timeout = s.embedding_timeout_seconds
        self.keep_alive = s.ollama_keep_alive
        self.num_ctx = s.embedding_num_ctx

    def _embed(self, texts: List[str]) -> np.ndarray:
        try:
            response = requests.post(self.url, timeout=self.timeout, json={
                "model": self.model_name, "input": texts, "keep_alive": self.keep_alive,
                "options": {"num_ctx": self.num_ctx}})
            response.raise_for_status()
            return normalise(response.json()["embeddings"])
        except (requests.RequestException, KeyError, ValueError) as exc:
            raise EmbeddingError(f"Ollama embedding failed: {exc}") from exc

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        batches = [self._embed(list(texts[i:i + self.batch_size])) for i in range(0, len(texts), self.batch_size)]
        return np.vstack(batches)

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([self.instruction + text])[0]


class FastEmbedEmbedder:
    """ONNX model on the CPU through fastembed (e.g. paraphrase-multilingual-MiniLM-L12-v2). No instruction
    prefix: these older models embed queries and documents the same way."""

    def __init__(self, settings: Optional[Settings] = None):
        from fastembed import TextEmbedding  # optional dependency, only needed for this provider

        s = settings or get_settings()
        self.model_name = s.embedding_model
        self.batch_size = s.embedding_batch_size
        self._model = TextEmbedding(self.model_name)

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return normalise(list(self._model.embed(list(texts), batch_size=self.batch_size)))

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]


def build_embedder(settings: Optional[Settings] = None) -> Embedder:
    s = settings or get_settings()
    return OllamaEmbedder(s) if s.embedding_provider == "ollama" else FastEmbedEmbedder(s)
