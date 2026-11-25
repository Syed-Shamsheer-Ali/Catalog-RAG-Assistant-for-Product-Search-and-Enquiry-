from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ExtractionResult(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    confidence: dict[str, float] = Field(default_factory=dict)
    validation_errors: list[str] = Field(default_factory=list)
    matches: list[dict[str, Any]] = Field(default_factory=list)
    review_status: str = "needs_review"
    input_source: str = "text"
    confirmed: bool = False
