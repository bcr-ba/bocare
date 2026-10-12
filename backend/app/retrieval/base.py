from dataclasses import dataclass
from typing import List, Optional, Protocol


@dataclass
class Source:
    name: str
    url: str
    content: str


class Retriever(Protocol):
    def search(self, query: str, limit: Optional[int] = None) -> List[Source]:
        """Return up to `limit` sources (retrieval_max_sources by default). Must not raise on network failures."""
        ...

