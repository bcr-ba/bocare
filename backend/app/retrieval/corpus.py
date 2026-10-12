"""MedlinePlus corpus: parse the health-topics XML export and split topics into retrievable chunks.

Run through scripts/build_corpus.py; the retriever then loads the chunks file.
"""
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, List, Tuple

from bs4 import BeautifulSoup, NavigableString, Tag

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Topic:
    id: str
    title: str
    url: str
    synonyms: List[str]           # "also called" names and see-references: often the patient's own words
    groups: List[str]             # MedlinePlus categories, e.g. "Ear, Nose and Throat"
    organization: str = ""        # credited source, e.g. "NIH: National Cancer Institute"
    blocks: List[str] = field(default_factory=list)  # paragraphs and lists, headings joined to what follows


@dataclass
class Chunk:
    id: str        # "<topic id>-<n>"
    topic_id: str
    title: str
    url: str
    header: str    # title and synonyms, repeated in every chunk of the topic
    text: str
    organization: str = ""

    @property
    def embedding_text(self) -> str:
        """What gets embedded and searched: the header gives a mid-topic chunk its context."""
        return f"{self.header}\n{self.text}"


# ---- parsing ----------------------------------------------------------------------------------

def _clean(text: str) -> str:
    return " ".join(text.split())


def _list_lines(list_tag: Tag, depth: int = 0) -> List[str]:
    """One line per item; nested lists are indented under their parent item, not repeated."""
    lines = []
    for item in list_tag.find_all("li", recursive=False):
        nested = item.find_all(["ul", "ol"], recursive=False)
        for sub in nested:
            sub.extract()
        lines.append("  " * depth + "- " + _clean(item.get_text(" ")))
        for sub in nested:
            lines += _list_lines(sub, depth + 1)
    return lines


def _is_heading(block: str) -> bool:
    """'What is drug use?' or 'Other causes can include:' introduce the next block."""
    return block.endswith(("?", ":")) and "\n" not in block


def _is_credit(block: str) -> bool:
    """The closing credit line, e.g. 'NIH: National Cancer Institute': short, no sentence punctuation."""
    return len(block) < 120 and not block.endswith((".", "?", "!")) and "\n" not in block


def summary_blocks(html: str) -> Tuple[List[str], str]:
    """Split a summary into blocks (paragraphs and lists) and return them with the credited
    organisation. Headings are joined to the block they introduce, since neither makes sense alone."""
    raw: List[str] = []
    for node in BeautifulSoup(html or "", "html.parser").children:
        if isinstance(node, NavigableString):
            text = _clean(str(node))
        elif isinstance(node, Tag) and node.name in ("ul", "ol"):
            text = "\n".join(_list_lines(node))
        elif isinstance(node, Tag):
            text = _clean(node.get_text(" "))
        else:
            continue
        if text:
            raw.append(text)

    credit = raw.pop() if len(raw) > 1 and _is_credit(raw[-1]) else ""
    blocks: List[str] = []
    for text in raw:
        if blocks and _is_heading(blocks[-1]):
            blocks[-1] += "\n" + text
        else:
            blocks.append(text)
    return blocks, credit


def parse_medlineplus(path: Path) -> List[Topic]:
    """English topics from the export (the Spanish ones are skipped)."""
    topics = []
    for element in ET.parse(path).getroot().findall("health-topic"):
        if element.get("language") != "English":
            continue
        names = [e.text for tag in ("also-called", "see-reference") for e in element.findall(tag) if e.text]
        blocks, credit = summary_blocks(element.findtext("full-summary"))
        topic = Topic(
            id=element.get("id"),
            title=element.get("title"),
            url=element.get("url"),
            synonyms=list(dict.fromkeys(n for n in names if n.lower() != element.get("title").lower())),
            groups=[e.text for e in element.findall("group") if e.text],
            organization=credit,
            blocks=blocks,
        )
        if topic.blocks:
            topics.append(topic)
    return topics


# ---- chunking ---------------------------------------------------------------------------------

def _split_long_block(block: str, target_chars: int) -> List[str]:
    """A block longer than the target is cut between list items (lines), then at sentence ends,
    never mid-sentence."""
    if len(block) <= target_chars:
        return [block]
    units = [u for line in block.split("\n") for u in
             (_SENTENCE_END.split(line) if len(line) > target_chars else [line])]
    pieces, current = [], ""
    for unit in units:
        separator = "\n" if unit.lstrip().startswith("- ") else " "
        if current and len(current) + len(unit) + 1 > target_chars:
            pieces.append(current)
            current = unit
        else:
            current = f"{current}{separator}{unit}" if current else unit
    return pieces + ([current] if current else [])


def chunk_topic(topic: Topic, target_chars: int, max_synonyms: int) -> List[Chunk]:
    """Pack consecutive blocks into chunks of about `target_chars`. Splits only fall between blocks."""
    synonyms = topic.synonyms[:max_synonyms]
    header = topic.title + (f" (also called: {', '.join(synonyms)})" if synonyms else "")

    texts: List[str] = []
    current: List[str] = []
    for block in (piece for b in topic.blocks for piece in _split_long_block(b, target_chars)):
        if current and sum(map(len, current)) + len(block) > target_chars:
            texts.append("\n".join(current))
            current = []
        current.append(block)
    if current:
        texts.append("\n".join(current))

    return [Chunk(f"{topic.id}-{i}", topic.id, topic.title, topic.url, header, text, topic.organization)
            for i, text in enumerate(texts)]


def write_chunks(chunks: Iterable[Chunk], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")
            count += 1
    return count


def read_chunks(path: Path) -> Iterator[Chunk]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield Chunk(**json.loads(line))
