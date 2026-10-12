"""The structure the model must answer in. Urgency is deliberately absent: it comes from the triage rules."""
from typing import List, Optional

from pydantic import BaseModel, Field


class Explanation(BaseModel):
    text: str
    source_ids: List[int] = Field(default_factory=list, description="Numbers of the sources supporting this point.")


class StructuredAnswer(BaseModel):
    summary: str = Field(description="One or two sentences answering the person directly.")
    possible_explanations: List[Explanation] = Field(default_factory=list)
    warning_signs: List[str] = Field(default_factory=list, description="Signs that should prompt urgent care.")
    self_care: List[str] = Field(default_factory=list, description="Safe monitoring and self-care advice.")
    clarifying_question: Optional[str] = None

    def texts(self) -> List[str]:
        """Every piece of text shown to the user, for the verification rules."""
        texts = [self.summary, *(e.text for e in self.possible_explanations), *self.warning_signs, *self.self_care]
        return texts + ([self.clarifying_question] if self.clarifying_question else [])


class JudgeVerdict(BaseModel):
    supported: bool = Field(description="Every explanation is backed by the sources it cites.")
    contradicts_recommendation: bool = Field(description="The answer contradicts or downplays the recommendation.")
    reason: str = Field(default="", description="One short sentence.")


ANSWER_SCHEMA = StructuredAnswer.model_json_schema()
JUDGE_SCHEMA = JudgeVerdict.model_json_schema()
