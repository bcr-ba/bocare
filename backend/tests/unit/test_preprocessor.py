import pytest

from app.pipeline.postprocessor import drop_invalid_citations, strip_self_references
from app.pipeline.preprocessor import small_talk_kind


@pytest.mark.parametrize("text, kind", [
    ("hi", "greeting"), ("Hi ", "greeting"), ("hello there!", "greeting"), ("Bonjour", "greeting"),
    ("salut !", "greeting"), ("good morning", "greeting"),
    ("Can you help me?", "help"), ("aide-moi", "help"), ("Pouvez-vous m'aider ?", "help"),
    ("thanks", "thanks"), ("Merci beaucoup", "thanks"), ("ok", "thanks"),
])
def test_small_talk_is_recognised(text, kind):
    assert small_talk_kind(text) == kind


@pytest.mark.parametrize("text", [
    "hi, I have a headache", "bonjour, j'ai de la fièvre", "thanks but the pain is worse", "hip pain",
    "can you help me with my back pain?",
])
def test_messages_with_content_are_not_small_talk(text):
    assert small_talk_kind(text) is None


def test_preamble_is_removed():
    assert strip_self_references("Here's my response: Rest well.") == "Rest well."
    assert strip_self_references("Voici ma réponse : Reposez-vous.") == "Reposez-vous."


def test_grouped_citations_keep_only_real_sources():
    assert drop_invalid_citations("Heart attack [1, 2]. Angina [2,5]. Other [7].", 2) == \
        "Heart attack [1, 2]. Angina [2]. Other."
