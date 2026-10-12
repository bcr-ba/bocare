import numpy as np
import pytest

from app.core.settings import get_settings
from app.retrieval.corpus import Chunk, write_chunks
from app.retrieval.dense import DenseRetriever
from app.retrieval.embeddings import EmbeddingError, normalise
from app.retrieval.vector_index import VectorIndex, VectorIndexError

# A 3-dimensional "meaning space": throat, skin, urine.
VECTORS = {"throat": [1, 0, 0], "skin": [0, 1, 0], "urine": [0, 0, 1]}


def chunk(topic: str, n: int, meaning: str) -> Chunk:
    return Chunk(id=f"{topic}-{n}", topic_id=topic, title=topic.title(), url=f"https://medlineplus.gov/{topic}.html",
                 header=topic.title(), text=meaning)


class FakeEmbedder:
    """Embeds a text as the meaning it mentions; the query 'scratchy throat and itchy skin' mixes two."""
    model_name = "fake-embedder"

    def __init__(self, fail: bool = False):
        self.fail = fail

    def _vector(self, text: str) -> np.ndarray:
        return normalise(sum(np.array(v, float) for k, v in VECTORS.items() if k in text))

    def embed_documents(self, texts):
        return np.vstack([self._vector(t) for t in texts])

    def embed_query(self, text):
        if self.fail:
            raise EmbeddingError("ollama down")
        return self._vector(text)


@pytest.fixture
def index(tmp_path):
    chunks = [chunk("sorethroat", 0, "throat"), chunk("sorethroat", 1, "throat"),
              chunk("rashes", 0, "skin"), chunk("uti", 0, "urine")]
    write_chunks(chunks, tmp_path / "chunks.jsonl")
    return VectorIndex.build(tmp_path / "chunks.jsonl", FakeEmbedder(), tmp_path / "index")


def test_search_ranks_by_cosine_similarity(index):
    results = index.search(normalise(np.array([0.9, 0.1, 0.0])), top=3)
    assert [c.topic_id for c, _ in results][:2] == ["sorethroat", "sorethroat"]
    assert results[0][1] == pytest.approx(results[1][1]) and results[0][1] > results[2][1]


def test_retriever_keeps_one_chunk_per_page(index):
    sources = DenseRetriever(index, FakeEmbedder(), get_settings()).search("scratchy throat and itchy skin", limit=4)
    assert [s.url.rsplit("/", 1)[1] for s in sources][:2] in (["sorethroat.html", "rashes.html"],
                                                              ["rashes.html", "sorethroat.html"])
    assert len({s.url for s in sources}) == len(sources)


def test_limit_is_respected(index):
    assert len(DenseRetriever(index, FakeEmbedder(), get_settings()).search("throat", limit=1)) == 1


def test_embedding_failure_returns_no_sources(index):
    assert DenseRetriever(index, FakeEmbedder(fail=True), get_settings()).search("throat") == []


def test_index_round_trips_through_disk(index, tmp_path):
    loaded = VectorIndex.load(tmp_path / "index", "fake-embedder")
    assert loaded.chunks == index.chunks
    np.testing.assert_allclose(loaded.vectors, index.vectors)


def test_missing_index_explains_how_to_build_it(tmp_path):
    with pytest.raises(VectorIndexError, match="build_index.py"):
        VectorIndex.load(tmp_path, "qwen3-embedding:0.6b")


def test_vectors_are_normalised():
    vectors = normalise(np.array([[3.0, 4.0], [0.0, 0.0]]))
    np.testing.assert_allclose(np.linalg.norm(vectors[0]), 1.0)
    assert not np.isnan(vectors).any()  # a zero vector stays zero instead of dividing by zero
