"""Follow-up questions (config/follow_up_questions.yml)."""
from typing import List, Sequence, Tuple

from app.core import config_loader

QuestionId = Tuple[str, int]


def next_follow_up_questions(asked: Sequence[QuestionId], language: str) -> List[QuestionId]:
    """Pick the first unasked question from each category, as (category, index) pairs."""
    config = config_loader.follow_up()
    picked: List[QuestionId] = []
    for category, by_language in config.categories.items():
        for index in range(len(by_language[language])):
            if (category, index) not in asked:
                picked.append((category, index))
                break
        if len(picked) == config.max_per_turn:
            break
    return picked


def question_text(question: QuestionId, language: str) -> str:
    category, index = question
    return config_loader.follow_up().categories[category][language][index]
