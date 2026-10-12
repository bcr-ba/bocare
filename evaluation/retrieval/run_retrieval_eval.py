"""Scores a retriever on queries.yml: hit@1, hit@k and MRR, overall and per language and style.

    python evaluation/retrieval/run_retrieval_eval.py medlineplus_api

Results are printed and saved to evaluation/retrieval/results/<retriever>.json for comparison.
"""
import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, List

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "backend"))

from app.retrieval.base import Retriever  # noqa: E402


def medlineplus_api() -> Retriever:
    from app.retrieval.medlineplus import MedlinePlusRetriever
    return MedlinePlusRetriever()


def dense(provider: str, model: str) -> Callable[[], Retriever]:
    def make() -> Retriever:
        from app.core.settings import ROOT_DIR, get_settings
        from app.retrieval.dense import DenseRetriever
        from app.retrieval.embeddings import build_embedder
        from app.retrieval.vector_index import VectorIndex

        settings = get_settings().model_copy(update={"embedding_provider": provider, "embedding_model": model})
        index = VectorIndex.load(ROOT_DIR / settings.index_dir, model)
        return DenseRetriever(index, build_embedder(settings), settings)
    return make


# Retrievers that can be evaluated, by name. Later steps add theirs here.
RETRIEVERS: Dict[str, Callable[[], Retriever]] = {
    "medlineplus_api": medlineplus_api,
    "dense_minilm": dense("fastembed", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
    "dense_qwen3": dense("ollama", "qwen3-embedding:0.6b"),
}
# Seconds between queries, to stay under MedlinePlus's limit of 85 requests per minute.
PAUSE = {"medlineplus_api": 1.0}


def page_id(url: str) -> str:
    """https://medlineplus.gov/sorethroat.html -> sorethroat"""
    return url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".html")


def evaluate(name: str) -> dict:
    dataset = yaml.safe_load((HERE / "queries.yml").read_text(encoding="utf-8"))
    k = dataset["k"]
    retriever = RETRIEVERS[name]()
    rows = []
    for query in dataset["queries"]:
        started = time.perf_counter()
        sources = retriever.search(query["text"], limit=k)
        latency = time.perf_counter() - started
        retrieved = [page_id(s.url) for s in sources]
        rank = next((i for i, page in enumerate(retrieved, 1) if page in query["expected"]), None)
        rows.append({**query, "retrieved": retrieved, "rank": rank, "latency_s": round(latency, 3)})
        time.sleep(PAUSE.get(name, 0))
    return {"retriever": name, "k": k, "rows": rows}


def scores(rows: List[dict]) -> Dict[str, float]:
    return {
        "n": len(rows),
        "hit@1": sum(r["rank"] == 1 for r in rows) / len(rows),
        "hit@k": sum(r["rank"] is not None for r in rows) / len(rows),
        "mrr": sum(1 / r["rank"] for r in rows if r["rank"]) / len(rows),
        "empty": sum(not r["retrieved"] for r in rows) / len(rows),
        "median_latency_s": statistics.median(r["latency_s"] for r in rows),
    }


def report(result: dict) -> dict:
    rows = result["rows"]
    groups = defaultdict(list)
    for row in rows:
        groups["all"].append(row)
        groups[row["lang"]].append(row)
        groups[row["style"]].append(row)
        groups[f"{row['lang']}/{row['style']}"].append(row)

    summary = {name: scores(group) for name, group in groups.items()}
    print(f"\nRetriever: {result['retriever']}   (k = {result['k']})\n")
    print(f"{'group':<16}{'n':>4}{'hit@1':>8}{'hit@k':>8}{'MRR':>7}{'empty':>8}{'latency':>9}")
    for name in ["all", "en", "fr", "direct", "paraphrase", "en/direct", "en/paraphrase", "fr/direct",
                 "fr/paraphrase"]:
        s = summary[name]
        print(f"{name:<16}{s['n']:>4}{s['hit@1']:>8.0%}{s['hit@k']:>8.0%}{s['mrr']:>7.2f}{s['empty']:>8.0%}"
              f"{s['median_latency_s']:>8.2f}s")

    print("\nMisses (no expected page in the top k):")
    for row in rows:
        if row["rank"] is None:
            got = ", ".join(row["retrieved"]) or "nothing"
            print(f"  {row['id']}  {row['text'][:55]:<55}  expected {'/'.join(row['expected'])}  got {got}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("retriever", choices=sorted(RETRIEVERS))
    args = parser.parse_args()
    result = evaluate(args.retriever)
    result["summary"] = report(result)
    out = HERE / "results" / f"{args.retriever}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to {out.relative_to(HERE.parents[1])}")


if __name__ == "__main__":
    main()
