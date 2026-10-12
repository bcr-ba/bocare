import pytest

from app.pipeline.follow_up import next_follow_up_questions
from app.pipeline.triage import analyze_symptoms, care_recommendation


@pytest.mark.parametrize("text, expected", [
    ("I took an overdose of my pills", 5),
    ("j'ai une douleur thoracique depuis ce matin", 5),
    ("my son had a seizure", 5),
    ("high fever since yesterday", 4),
    ("the rash keeps spreading", 3),
    ("a mild cough", 1),
])
def test_urgency_levels(text, expected):
    _, urgency, _ = analyze_symptoms(text)
    assert urgency == expected


def test_specialist_only_suggested_at_level_3():
    advice, _ = care_recommendation(3, "neurology", "en")
    assert "neurologist" in advice
    advice, _ = care_recommendation(5, "neurology", "en")
    assert "neurologist" not in advice


def test_follow_up_questions_are_not_repeated():
    first = next_follow_up_questions([], "fr")
    second = next_follow_up_questions(first, "fr")
    assert first and second
    assert not set(first) & set(second)


def test_every_care_path_exists_in_both_languages():
    for level in range(1, 6):
        for language in ("fr", "en"):
            assert care_recommendation(level, None, language)
