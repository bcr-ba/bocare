"""Builds the messages sent to the model. The texts live in app/prompts/*.yml."""
import json
from typing import Dict, List, Optional, Sequence

from app.core import config_loader
from app.retrieval.base import Source
from app.schemas.llm import StructuredAnswer


def format_context(sources: List[Source]) -> str:
    """Render sources as a numbered block for a prompt."""
    template = config_loader.answer_prompts().source_format
    return "\n\n".join(template.format(number=i, title=s.name, url=s.url, content=s.content)
                       for i, s in enumerate(sources, 1))


def build_messages(text: str, history: Sequence[Dict[str, str]], sources: List[Source], language: str,
                   urgency_level: int, advice: str,
                   rejected_for: Optional[List[str]] = None) -> List[Dict[str, str]]:
    prompts = config_loader.answer_prompts()
    system = prompts.system[language].format(level=urgency_level, advice=advice)
    if urgency_level >= config_loader.verification().delay_advice_min_level:
        system += "\n" + prompts.urgent_rule[language]
    context = "Sources:\n" + format_context(sources) if sources else prompts.no_sources[language]

    messages = [{"role": "system", "content": system}]
    messages += list(history)[-prompts.history_turns:]
    messages.append({"role": "user", "content": f"{text}\n\n{context}"})
    if rejected_for:
        messages.append({"role": "system",
                         "content": prompts.retry_note[language].format(reasons=", ".join(rejected_for))})
    return messages


def build_judge_messages(answer: StructuredAnswer, sources: List[Source], urgency_level: int,
                         advice: str) -> List[Dict[str, str]]:
    prompts = config_loader.judge_prompts()
    content = prompts.user.format(
        level=urgency_level, advice=advice,
        sources=format_context(sources) if sources else prompts.no_sources,
        answer=json.dumps(answer.model_dump(), ensure_ascii=False),
    )
    return [{"role": "system", "content": prompts.system}, {"role": "user", "content": content}]
