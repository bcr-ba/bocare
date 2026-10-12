import json
from typing import List

import pytest
from conftest import FakeRetriever

from app.llm.client import LLMError
from app.pipeline.orchestrator import Orchestrator
from app.pipeline.postprocessor import clean_answer, parse_answer, render_markdown
from app.pipeline.responder import Responder
from app.pipeline.verifier import Verifier, rule_failures
from app.schemas.llm import StructuredAnswer


def answer(summary="Chest pain can come from the heart.", **fields) -> StructuredAnswer:
    return StructuredAnswer(summary=summary, **fields)


class ScriptedLLM:
    """Returns the scripted replies in order (strings, or exceptions to raise)."""
    configured = True

    def __init__(self, replies: List):
        self.replies = list(replies)
        self.calls = []

    def complete(self, messages, schema=None, max_tokens=None):
        self.calls.append({"messages": messages, "schema": schema})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def as_json(**fields) -> str:
    return json.dumps(answer(**fields).model_dump())


# ---- rules ------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "You can wait until tomorrow.", "Monitor your symptoms at home.", "Surveillez l'évolution.",
    "Vous pouvez attendre demain.", "This is not urgent.",
])
def test_delay_advice_is_rejected_at_high_urgency(text):
    assert rule_failures(answer(summary=text), urgency_level=5) == ["delay_advice_at_high_urgency"]
    assert rule_failures(answer(summary=text), urgency_level=2) == []  # fine when the case is mild


@pytest.mark.parametrize("text", [
    "Do not wait: call 15 now.", "Don't wait, call emergency services.", "N'attendez pas, appelez le 15.",
    "Il ne faut pas attendre.",
])
def test_negated_delay_advice_is_accepted(text):
    assert rule_failures(answer(summary=text), urgency_level=5) == []


@pytest.mark.parametrize("text", ["Take 400 mg of ibuprofen.", "Prenez 2 comprimés.", "Give 5 ml of syrup."])
def test_doses_are_rejected(text):
    assert "dose" in rule_failures(answer(self_care=[text]), urgency_level=1)


def test_numbers_that_are_not_doses_are_fine():
    assert rule_failures(answer(summary="A fever over 39°C for 3 days, pain 7 on a scale of 1 to 10."), 1) == []


@pytest.mark.parametrize("text", [
    "You definitely have a heart attack.", "This is clearly a migraine.", "Vous souffrez d'une angine.",
    "Il s'agit certainement d'une grippe.",
])
def test_diagnostic_certainty_is_rejected(text):
    assert rule_failures(answer(summary=text), urgency_level=1) == ["diagnostic_certainty"]


def test_restating_a_symptom_is_not_a_diagnosis():
    assert rule_failures(answer(summary="You have a sore throat since Monday."), urgency_level=1) == []


# ---- regeneration and fallback ----------------------------------------------------------------

def run(llm, urgency_text="I have chest pain", verifier=None):
    orchestrator = Orchestrator(Responder(FakeRetriever(), llm, verifier or Verifier()))
    return orchestrator.handle(urgency_text, language="en")


def test_structured_answer_passes_and_is_returned():
    llm = ScriptedLLM([as_json(summary="Call now: chest pain can signal a heart problem.",
                               possible_explanations=[{"text": "Heart attack", "source_ids": [1, 9]}])])
    result = run(llm)
    assert result.verification == "passed"
    assert result.answer.possible_explanations[0].source_ids == [1]  # source 9 doesn't exist
    assert llm.calls[0]["schema"]["title"] == "StructuredAnswer"


def test_rejected_answer_is_regenerated_with_the_reason():
    llm = ScriptedLLM([as_json(summary="You can wait and see."), as_json(summary="Do not wait: call 15 now.")])
    result = run(llm)
    assert result.verification == "regenerated"
    assert result.failed_checks == ["delay_advice_at_high_urgency"]
    assert "delay_advice_at_high_urgency" in llm.calls[1]["messages"][-1]["content"]
    assert result.answer.summary == "Do not wait: call 15 now."


def test_two_rejections_fall_back_to_the_fixed_recommendation():
    llm = ScriptedLLM([as_json(summary="Take 500 mg of aspirin."), as_json(summary="Take 300 mg of aspirin.")])
    result = run(llm)
    assert result.verification == "fallback"
    assert result.answer is None
    assert "Call your local emergency number" in result.reply
    assert result.failed_checks == ["dose", "dose"]


def test_llm_outage_is_reported_as_such():
    result = run(ScriptedLLM([LLMError("timeout")]))
    assert result.verification == "llm_unavailable"
    assert result.recommendation is not None


# ---- judge ------------------------------------------------------------------------------------

def judge_reply(supported=True, contradicts=False):
    return json.dumps({"supported": supported, "contradicts_recommendation": contradicts, "reason": "x"})


def test_judge_runs_from_level_3_and_can_reject():
    llm = ScriptedLLM([as_json(), judge_reply(supported=False), as_json(), judge_reply()])
    result = run(llm, verifier=Verifier(judge=llm, judge_min_level=3))
    assert result.verification == "regenerated"
    assert result.failed_checks == ["judge_unsupported_claim"]


def test_judge_is_skipped_below_its_level():
    llm = ScriptedLLM([as_json(summary="A sore throat is usually viral.")])
    result = run(llm, "I have a sore throat", verifier=Verifier(judge=llm, judge_min_level=3))
    assert result.verification == "passed" and len(llm.calls) == 1


def test_unavailable_judge_does_not_block_an_answer_that_passed_the_rules():
    llm = ScriptedLLM([as_json(summary="Do not wait: call 15 now."), LLMError("judge timeout")])
    result = run(llm, verifier=Verifier(judge=llm))
    assert result.verification == "passed"


# ---- parsing and rendering --------------------------------------------------------------------

def test_parse_answer_handles_json_wrapped_in_prose():
    parsed, structured = parse_answer('Sure! {"summary": "Rest."} Hope it helps.')
    assert structured and parsed.summary == "Rest."


def test_parse_answer_keeps_plain_text_as_summary():
    parsed, structured = parse_answer("Rest and drink water.")
    assert not structured and parsed.summary == "Rest and drink water."


def test_render_markdown_lists_sections_and_citations():
    rendered = render_markdown(clean_answer(answer(
        summary="Likely viral.", possible_explanations=[{"text": "A cold", "source_ids": [1]}],
        warning_signs=["Trouble breathing"], clarifying_question="Since when?"), source_count=1), "en")
    assert rendered == ("Likely viral.\n\n**Possible explanations**\n\n- A cold [1]\n\n"
                        "**Warning signs**\n\n- Trouble breathing\n\nSince when?")


def test_negation_too_far_away_does_not_excuse_delay_advice():
    assert rule_failures(answer(summary="Do not hesitate, you can wait until tomorrow."), 5) == [
        "delay_advice_at_high_urgency"]
