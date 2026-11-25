from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RequirementLineItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    product_name: str = ""
    product_kind: str = ""
    product_category: str = ""
    size_inch: str = ""
    specifications: str = ""
    material: str = ""
    system: str = ""
    quantity: str = ""
    unit: str = ""
    part_number: str = ""
    notes: str = ""
    selected_product_id: str = ""
    duplicate_confirmed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class MultipleRequirementSubmission(BaseModel):
    customer_name: str = ""
    line_items: list[RequirementLineItem] = Field(default_factory=list)
    confirmed: bool = False
