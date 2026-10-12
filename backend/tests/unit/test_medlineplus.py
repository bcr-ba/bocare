from pathlib import Path

import pytest
import requests

from app.retrieval.medlineplus import MedlinePlusRetriever, parse_results
from app.retrieval.query_terms import search_terms

# A real response from wsearch.nlm.nih.gov for "sore throat", saved for offline tests.
SORE_THROAT_XML = (Path(__file__).parents[1] / "fixtures" / "medlineplus_sore_throat.xml").read_text(encoding="utf-8")


@pytest.mark.parametrize("text, expected", [
    ("I have had a sore throat since Monday", ["sore throat"]),
    ("J'ai mal à la gorge depuis lundi", ["sore throat"]),
    ("J’ai mal à la tête et de la fièvre", ["headache", "fever"]),
    ("I took an overdose and now I'm dizzy", ["overdose", "dizziness and vertigo"]),
    ("I have heartburn after meals", ["heartburn"]),  # not "burns"
    ("chest pain, headache, fever and a cough", ["chest pain", "headache", "fever"]),  # emergencies first, max 3
    ("hello there", []),
])
def test_search_terms(text, expected):
    assert search_terms(text) == expected


def test_parse_real_response():
    sources = parse_results(SORE_THROAT_XML)
    assert sources[0].name == "MedlinePlus: Sore Throat"
    assert sources[0].url == "https://medlineplus.gov/sorethroat.html"
    assert "<" not in sources[0].content and "pharynx" in sources[0].content


class FakeResponse:
    def __init__(self, text="", status=200):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def test_search_queries_each_term_and_caches(monkeypatch):
    calls = []

    def fake_get(url, params, timeout):
        calls.append(params["term"])
        return FakeResponse(SORE_THROAT_XML)

    monkeypatch.setattr(requests, "get", fake_get)
    retriever = MedlinePlusRetriever()
    sources = retriever.search("mal de gorge et fièvre")
    assert sorted(calls) == ["fever", "sore throat"]
    assert len({s.url for s in sources}) == len(sources)  # identical pages are not repeated
    retriever.search("mal de gorge et fièvre")
    assert len(calls) == 2  # second call served from the cache


def test_runners_up_only_for_a_single_symptom(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, params, timeout: FakeResponse(SORE_THROAT_XML))
    assert len(MedlinePlusRetriever().search("sore throat")) == 2  # best match + runner-up
    sources = MedlinePlusRetriever().search("sore throat and fever")
    assert [s.url for s in sources] == ["https://medlineplus.gov/sorethroat.html"]  # one per term, deduplicated


def test_no_medical_terms_means_no_request(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("should not call the API"))
    assert MedlinePlusRetriever().search("what's the weather like?") == []


def test_network_errors_return_no_sources(monkeypatch):
    def down(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "get", down)
    assert MedlinePlusRetriever().search("sore throat") == []


def test_http_errors_are_not_cached(monkeypatch):
    responses = [FakeResponse(status=503), FakeResponse(SORE_THROAT_XML)]
    monkeypatch.setattr(requests, "get", lambda *a, **k: responses.pop(0))
    retriever = MedlinePlusRetriever()
    assert retriever.search("sore throat") == []
    assert retriever.search("sore throat")  # retried, now succeeds
