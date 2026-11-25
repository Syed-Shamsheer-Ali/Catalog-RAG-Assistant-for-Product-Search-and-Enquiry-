"""Pydantic schemas for canonical product catalog records."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class PriceType(str, Enum):
    PER_PIECE = "PER_PIECE"
    PER_BOX = "PER_BOX"
    PER_METER = "PER_METER"
    PER_LENGTH = "PER_LENGTH"
    OTHER = "OTHER"


class ProductKind(str, Enum):
    PIPE = "PIPE"
    FITTING = "FITTING"
    VALVE = "VALVE"
    CEMENT = "CEMENT"
    ACCESSORY = "ACCESSORY"
    SPARE = "SPARE"
    OTHER = "OTHER"


class ReviewReason(str, Enum):
    MISSING_PART_NUMBER = "MISSING_PART_NUMBER"
    MISSING_PRICE = "MISSING_PRICE"
    MISSING_SIZE = "MISSING_SIZE"
    SPLIT_CELL_RECONSTRUCTION = "SPLIT_CELL_RECONSTRUCTION"
    AMBIGUOUS_COLUMNS = "AMBIGUOUS_COLUMNS"
    COMPOUND_SIZE_PARSE = "COMPOUND_SIZE_PARSE"
    PRICE_TYPE_UNCLEAR = "PRICE_TYPE_UNCLEAR"
    TABLE_STRUCTURE_ANOMALY = "TABLE_STRUCTURE_ANOMALY"
    CONFLICTING_EXTRACTION = "CONFLICTING_EXTRACTION"
    PLACEHOLDER_VALUE = "PLACEHOLDER_VALUE"


class ProductRecord(BaseModel):
    """Canonical product row derived from the local catalog PDF.

    Nullable fields are intentional. Missing source values stay null.
    """

    model_config = ConfigDict(extra="forbid")

    product_id: str
    product_kind: ProductKind
    product_category: Optional[str] = None
    product_name: str
    product_variant: Optional[str] = None
    material: Optional[str] = None
    system: Optional[str] = None
    class_name: Optional[str] = None
    sdr: Optional[str] = None
    schedule: Optional[str] = None
    size_cm: Optional[str] = None
    size_inch: Optional[str] = None
    size_text: Optional[str] = None
    compound_size: Optional[str] = None
    part_number: Optional[str] = None
    standard_package_qty: Optional[int] = None
    box_quantity: Optional[int] = None
    price: Optional[float] = None
    price_type: Optional[PriceType] = None
    length: Optional[float] = None
    length_unit: Optional[str] = None
    price_per_meter: Optional[float] = None
    price_per_length: Optional[float] = None
    price_length: Optional[float] = None
    price_length_unit: Optional[str] = None
    hsn_code: Optional[str] = None
    effective_from: Optional[str] = None
    price_list_version: Optional[str] = None
    source_document: str
    source_page: int
    source_section: Optional[str] = None
    source_row: Optional[int] = None
    original_text: Optional[str] = None
    needs_review: bool = False
    review_reasons: list[ReviewReason] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)

    def mark_review(self, reason: ReviewReason) -> None:
        self.needs_review = True
        if reason not in self.review_reasons:
            self.review_reasons.append(reason)
