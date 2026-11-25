from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RequirementForm:
    customer_name: str = ""
    product_kind: str = ""
    product_category: str = ""
    size_inch: str = ""
    material: str = ""
    system: str = ""
    quantity: str = ""
    unit_price: str = ""
    notes: str = ""
    source_text: str = ""
    image_path: str | None = None
    auto_filled: bool = False
    editable_fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_name": self.customer_name,
            "product_kind": self.product_kind,
            "product_category": self.product_category,
            "size_inch": self.size_inch,
            "material": self.material,
            "system": self.system,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "notes": self.notes,
            "source_text": self.source_text,
            "image_path": self.image_path,
            "auto_filled": self.auto_filled,
        }
