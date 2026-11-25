from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RequirementRequest(BaseModel):
    """A normalized product requirement to match against the local catalog."""

    product_kind: str | None = Field(default=None, alias="kind")
    product_name: str | None = None
    product_variant: str | None = None
    specifications: str | None = None
    product_category: str | None = Field(default=None, alias="category")
    size_inch: str | None = Field(default=None, alias="size")
    material: str | None = None
    system: str | None = None
    class_name: str | None = None
    pressure_class: str | None = None
    sdr: str | None = None
    schedule: str | None = None
    part_number: str | None = None
    product_code: str | None = None
    hsn_code: str | None = None
    max_results: int = 10

    model_config = {"populate_by_name": True, "extra": "ignore"}

    @property
    def kind(self) -> str | None:
        return self.product_kind

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        data = super().model_dump(*args, **kwargs)
        if self.product_kind is not None and "product_kind" not in data:
            data["product_kind"] = self.product_kind
        if self.product_category is not None and "product_category" not in data:
            data["product_category"] = self.product_category
        if self.size_inch is not None and "size_inch" not in data:
            data["size_inch"] = self.size_inch
        return data
