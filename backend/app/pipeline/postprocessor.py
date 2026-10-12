"""Parsing and clean-up applied to model output before it is verified and returned."""
import re
from typing import Tuple

from app.core import config_loader
from app.schemas.llm import Explanation, StructuredAnswer

_CLEANUP = config_loader.conversation().output_cleanup

# Sentences where the model talks about itself ("As an AI language model, ...") add
# nothing for a patient. Remove the whole sentence rather than rewording it, so the
# meaning of what remains is unchanged.
SELF_REFERENCE = re.compile(
    r"[^.!?\n]*\b(" + "|".join(_CLEANUP.self_reference_phrases) + r")\b[^.!?\n]*[.!?]?", re.IGNORECASE)


# Reasoning models (e.g. Qwen3) can emit their chain of thought in <think> tags.
THINK_BLOCK = re.compile(r"<think>.*?(</think>|$)", re.DOTALL | re.IGNORECASE)


CITATION = re.compile(r"(\s?)\[(\d+(?:\s*,\s*\d+)*)\]")


def drop_invalid_citations(text: str, source_count: int) -> str:
    """Keep only citation numbers ([2], [1, 3]) that point to a source actually given to the model."""
    def keep_valid(match: re.Match) -> str:
        valid = [n for n in re.findall(r"\d+", match.group(2)) if 1 <= int(n) <= source_count]
        return f"{match.group(1)}[{', '.join(valid)}]" if valid else ""
    return CITATION.sub(keep_valid, text)


# "Here's my response:" / "Voici ma réponse :" openers small models add before the answer.
PREAMBLE = re.compile(_CLEANUP.preamble_pattern, re.IGNORECASE)


def strip_self_references(text: str) -> str:
    cleaned = PREAMBLE.sub("", SELF_REFERENCE.sub("", THINK_BLOCK.sub("", text)))
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def parse_answer(raw: str) -> Tuple[StructuredAnswer, bool]:
    """Parse the model's JSON. Returns (answer, structured); a model that ignored the schema
    gets its text treated as the summary, still subject to verification."""
    text = THINK_BLOCK.sub("", raw).strip()
    match = _JSON_OBJECT.search(text)
    for candidate in [text] + ([match.group(0)] if match else []):
        try:
            return StructuredAnswer.model_validate_json(candidate), True
        except ValueError:
            continue
    return StructuredAnswer(summary=text), False


def clean_answer(answer: StructuredAnswer, source_count: int) -> StructuredAnswer:
    """Strip self-references from every field and keep only source ids that exist."""
    def clean(text: str) -> str:
        return drop_invalid_citations(strip_self_references(text), source_count)

    explanations = [
        Explanation(text=clean(e.text), source_ids=sorted({i for i in e.source_ids if 1 <= i <= source_count}))
        for e in answer.possible_explanations
    ]
    return StructuredAnswer(
        summary=clean(answer.summary),
        possible_explanations=[e for e in explanations if e.text],
        warning_signs=[t for t in map(clean, answer.warning_signs) if t],
        self_care=[t for t in map(clean, answer.self_care) if t],
        clarifying_question=clean(answer.clarifying_question or "") or None,
    )


def render_markdown(answer: StructuredAnswer, language: str) -> str:
    """Plain Markdown version of a structured answer, for the `reply` field, history and export."""
    titles = config_loader.conversation().answer_sections[language]
    explanations_title, warnings_title, self_care_title = (
        titles["explanations"], titles["warning_signs"], titles["self_care"])
    parts = [answer.summary]
    if answer.possible_explanations:
        lines = [e.text + (f" [{', '.join(map(str, e.source_ids))}]" if e.source_ids else "")
                 for e in answer.possible_explanations]
        parts.append(f"**{explanations_title}**\n\n" + "\n".join(f"- {line}" for line in lines))
    for title, items in ((warnings_title, answer.warning_signs), (self_care_title, answer.self_care)):
        if items:
            parts.append(f"**{title}**\n\n" + "\n".join(f"- {item}" for item in items))
    if answer.clarifying_question:
        parts.append(answer.clarifying_question)
    return "\n\n".join(p for p in parts if p)
