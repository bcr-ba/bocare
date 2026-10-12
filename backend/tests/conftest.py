import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pytest

# Before any app code loads: tests must never write a sessions database or send traces.
os.environ["STATE_BACKEND"] = "memory"
os.environ["TRACING_EXPORTER"] = "none"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.llm.client import LLMError  # noqa: E402
from app.pipeline.orchestrator import Orchestrator  # noqa: E402
from app.pipeline.responder import Responder  # noqa: E402
from app.retrieval.base import Source  # noqa: E402

NHS_HEADACHES = Source("NHS: Headaches", "https://www.nhs.uk/conditions/headaches/",
                       "Most headaches go away on their own.")


class FakeRetriever:
    def __init__(self, sources: Optional[List[Source]] = None):
        self.sources = [NHS_HEADACHES] if sources is None else sources
        self.queries: List[str] = []

    def search(self, query: str, limit: int = 4) -> List[Source]:
        self.queries.append(query)
        return self.sources[:limit]


class FakeLLM:
    configured = True

    def __init__(self, reply: str = "Tension headaches are common.", error: Optional[str] = None):
        self.reply = reply
        self.error = error
        self.calls: List[List[Dict[str, str]]] = []

    def complete(self, messages: List[Dict[str, str]], schema=None, max_tokens=None) -> str:
        self.calls.append(messages)
        if self.error:
            raise LLMError(self.error)
        return self.reply


@pytest.fixture
def retriever() -> FakeRetriever:
    return FakeRetriever()


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def orchestrator(retriever, llm) -> Orchestrator:
    return Orchestrator(Responder(retriever, llm))
