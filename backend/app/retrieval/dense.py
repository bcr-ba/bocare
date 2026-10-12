"""Semantic (dense) retrieval: embed the patient's message, return the closest MedlinePlus chunks."""
import logging
from typing import List, Optional

from app.core.settings import Settings, get_settings
from app.retrieval.base import Source
from app.retrieval.embeddings import Embedder, EmbeddingError
from app.retrieval.vector_index import VectorIndex

logger = logging.getLogger(__name__)


class DenseRetriever:
    def __init__(self, index: VectorIndex, embedder: Embedder, settings: Optional[Settings] = None):
        self.index = index
        self.embedder = embedder
        self.settings = settings or get_settings()

    def warm_up(self) -> None:
        """Load the embedding model now so the first patient message doesn't wait for it."""
        try:
            self.embedder.embed_query("warm up")
            logger.info("Embedding model %s loaded", self.embedder.model_name)
        except EmbeddingError as exc:
            logger.warning("Could not preload embedding model: %s", exc)

    def search(self, query: str, limit: Optional[int] = None) -> List[Source]:
        limit = limit or self.settings.retrieval_max_sources
        try:
            query_vector = self.embedder.embed_query(query)
        except EmbeddingError as exc:
            logger.warning("Dense retrieval unavailable: %s", exc)
            return []  # the answer is generated without sources rather than failing

        # Several chunks of the same topic often score high; keep the best one per page so the
        # sources cover different pages.
        sources: List[Source] = []
        seen_topics = set()
        for chunk, _score in self.index.search(query_vector, self.settings.dense_candidates):
            if chunk.topic_id in seen_topics:
                continue
            seen_topics.add(chunk.topic_id)
            sources.append(Source(f"MedlinePlus: {chunk.title}", chunk.url, chunk.text))
            if len(sources) == limit:
                break
        return sources
