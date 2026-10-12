"""Build the retrieval corpus from the MedlinePlus health-topics export.

    python scripts/build_corpus.py              # use the export already downloaded
    python scripts/build_corpus.py --download   # fetch the latest export first

Paths and chunk size come from backend/app/config/settings.yml.
"""
import argparse
import re
import statistics
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.settings import get_settings  # noqa: E402
from app.retrieval.corpus import chunk_topic, parse_medlineplus, write_chunks  # noqa: E402


def download_latest(export_page: str, destination: Path) -> None:
    page = requests.get(export_page, timeout=30)
    page.raise_for_status()
    urls = sorted(set(re.findall(r"https://medlineplus\.gov/xml/mplus_topics_\d{4}-\d{2}-\d{2}\.xml", page.text)))
    if not urls:
        sys.exit(f"No export link found on {export_page}")
    print(f"Downloading {urls[-1]}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(urls[-1], stream=True, timeout=300) as response:
        response.raise_for_status()
        with destination.open("wb") as f:
            for block in response.iter_content(1 << 20):
                f.write(block)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="fetch the latest export first")
    args = parser.parse_args()
    settings = get_settings()
    raw, out = ROOT / settings.corpus_raw_file, ROOT / settings.corpus_chunks_file

    if args.download or not raw.exists():
        download_latest(settings.medlineplus_export_page, raw)

    topics = parse_medlineplus(raw)
    chunks = [c for t in topics for c in chunk_topic(t, settings.chunk_target_chars, settings.chunk_max_synonyms)]
    write_chunks(chunks, out)

    sizes = [len(c.text) for c in chunks]
    per_topic = [len(chunk_topic(t, settings.chunk_target_chars, settings.chunk_max_synonyms)) for t in topics]
    print(f"{len(topics)} English topics -> {len(chunks)} chunks (target {settings.chunk_target_chars} chars)")
    print(f"chunk size: median {statistics.median(sizes):.0f}, min {min(sizes)}, max {max(sizes)} chars")
    print(f"chunks per topic: median {statistics.median(per_topic):.0f}, max {max(per_topic)}")
    print(f"topics with synonyms: {sum(bool(t.synonyms) for t in topics) / len(topics):.0%}")
    print(f"written to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
