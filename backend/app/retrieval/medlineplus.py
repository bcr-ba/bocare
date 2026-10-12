"""Health-topic summaries from the official MedlinePlus search web service (NLM).

https://medlineplus.gov/about/developers/webservices/ - free, no key, at most 85
requests per minute per IP, so results are cached.
"""
import logging
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from app.core.settings import Settings, get_settings
from app.retrieval.base import Source
from app.retrieval.query_terms import search_terms

logger = logging.getLogger(__name__)


def _plain(html_fragment: str) -> str:
    """Strip the HTML (search-term highlighting, paragraphs, lists) from a result field."""
    return " ".join(BeautifulSoup(html_fragment or "", "html.parser").get_text(" ").split())


def parse_results(xml_text: str, max_snippet_chars: Optional[int] = None) -> List[Source]:
    max_chars = max_snippet_chars or get_settings().retrieval_max_snippet_chars
    sources = []
    for document in ET.fromstring(xml_text).iter("document"):
        fields: Dict[str, str] = {}
        for content in document.findall("content"):
            fields.setdefault(content.get("name"), content.text or "")  # keep the first title
        title = _plain(fields.get("title", ""))
        summary = _plain(fields.get("FullSummary") or fields.get("snippet", ""))
        if title and summary:
            sources.append(Source(f"MedlinePlus: {title}", document.get("url", ""), summary[:max_chars]))
    return sources


class MedlinePlusRetriever:
    """Settings (URL, timeout, cache, limits) come from config/settings.yml."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._cache: Dict[str, Tuple[float, List[Source]]] = {}

    def search(self, query: str, limit: Optional[int] = None) -> List[Source]:
        limit = limit or self.settings.retrieval_max_sources
        terms = search_terms(query)
        if not terms:
            return []
        with ThreadPoolExecutor(max_workers=len(terms)) as pool:
            results = list(pool.map(self._search_term, terms))

        # Best match for every term, without duplicates. Runners-up are only used for a single
        # symptom: with several, they tend to be off-topic ("fever" -> "Hemorrhagic Fevers").
        sources: List[Source] = []
        seen = set()
        for rank in range(self.settings.retrieval_results_per_term if len(terms) == 1 else 1):
            for term_results in results:
                if rank < len(term_results) and term_results[rank].url not in seen:
                    seen.add(term_results[rank].url)
                    sources.append(term_results[rank])
        return sources[:limit]

    def _search_term(self, term: str) -> List[Source]:
        cached = self._cache.get(term)
        s = self.settings
        if cached and time.monotonic() - cached[0] < s.retrieval_cache_ttl_seconds:
            return cached[1]
        try:
            response = requests.get(
                s.medlineplus_url,
                params={"db": s.medlineplus_database, "term": term, "retmax": s.retrieval_results_per_term},
                timeout=s.retrieval_timeout_seconds)
            response.raise_for_status()
            sources = parse_results(response.text, s.retrieval_max_snippet_chars)
        except (requests.RequestException, ET.ParseError) as exc:
            logger.warning("MedlinePlus search for %r failed: %s", term, exc)
            return []  # not cached, so the next message retries
        self._cache[term] = (time.monotonic(), sources)
        return sources
