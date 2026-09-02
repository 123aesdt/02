from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.reviews.models import ReviewDecision


class ReviewDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_rejection_reason(self) -> "ReviewDecisionRequest":
        if self.decision is ReviewDecision.REJECT and len((self.reason or "").strip()) < 2:
            raise ValueError("拒绝原因至少需要 2 个字符")
        return self


class ReviewDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: str
    decision: ReviewDecision
    status: str
    reviewer: str
    decided_at: datetime
    dispatch_version: int

