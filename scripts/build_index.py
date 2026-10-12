"""Embed the corpus chunks and save the vector index.

    python scripts/build_index.py                       # model from settings.yml
    python scripts/build_index.py --provider fastembed --model <fastembed model name>

Run scripts/build_corpus.py first. One index is kept per embedding model, so models can be compared.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.settings import get_settings  # noqa: E402
from app.retrieval.embeddings import build_embedder  # noqa: E402
from app.retrieval.vector_index import VectorIndex, model_folder  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", choices=["ollama", "fastembed"])
    parser.add_argument("--model")
    args = parser.parse_args()
    overrides = {k: v for k, v in (("embedding_provider", args.provider), ("embedding_model", args.model)) if v}
    settings = get_settings().model_copy(update=overrides)

    embedder = build_embedder(settings)
    print(f"Embedding {settings.corpus_chunks_file} with {settings.embedding_model} ({settings.embedding_provider})")
    started = time.perf_counter()
    index = VectorIndex.build(ROOT / settings.corpus_chunks_file, embedder, ROOT / settings.index_dir)
    elapsed = time.perf_counter() - started
    folder = model_folder(ROOT / settings.index_dir, settings.embedding_model)
    size_mb = (folder / "vectors.npy").stat().st_size / 1e6
    print(f"{len(index.chunks)} chunks x {index.vectors.shape[1]} dimensions = {size_mb:.1f} MB, "
          f"built in {elapsed:.0f} s ({len(index.chunks) / elapsed:.0f} chunks/s)")
    print(f"saved to {folder.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
