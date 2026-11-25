from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.services.requirement_service import RequirementService, validate_requirement_fields

CENT = Decimal("0.01")
UNIT_ALIASES = {
    "pc": "piece", "pcs": "piece", "piece": "piece", "pieces": "piece", "each": "piece", "no": "piece", "nos": "piece",
    "m": "m", "meter": "m", "meters": "m", "metre": "m", "metres": "m", "mtr": "m", "mtrs": "m",
    "length": "length", "lengths": "length", "stick": "length", "sticks": "length",
    "box": "box", "boxes": "box",
}
PRICE_UNITS = {"PER_PIECE": "piece", "PER_BOX": "box", "PER_METER": "m", "PER_LENGTH": "length"}


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError, TypeError):
        return None


class LineItemService:
    """Validate, match, and calculate each requested product independently."""

    def __init__(self, requirement_service: RequirementService | None = None):
        self.requirements = requirement_service or RequirementService()

    def prepare(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        prepared: list[dict[str, Any]] = []
        for index, source in enumerate(items):
            item = self._prepare_one(source, index)
            prepared.append(item)

        seen: dict[tuple[str, str], int] = {}
        for index, item in enumerate(prepared, start=1):
            product_key = str(item.get("selected_product_id") or item.get("part_number") or "").strip().lower()
            unit = str(item.get("unit") or "")
            if not product_key:
                continue
            key = (product_key, unit)
            if key in seen:
                item["duplicate_of"] = seen[key]
                if not item.get("duplicate_confirmed"):
                    item["validation_errors"].append(f"Duplicate of line {seen[key]}; confirm it or remove this line.")
            else:
                seen[key] = index
            item["review_status"] = "needs_review" if item["validation_errors"] else "ready_for_review"
            if item["review_status"] == "needs_review":
                item["line_total"] = None

        complete = bool(prepared) and all(item.get("review_status") == "ready_for_review" and item.get("line_total") is not None for item in prepared)
        total = sum((Decimal(str(item["line_total"])) for item in prepared), Decimal("0")) if complete else None
        return {
            "line_items": prepared,
            "grand_total": float(total.quantize(CENT, rounding=ROUND_HALF_UP)) if total is not None else None,
            "is_complete": complete,
            "validation_errors": [f"Line {index}: {error}" for index, item in enumerate(prepared, start=1) for error in item["validation_errors"]],
        }

    def _prepare_one(self, source: dict[str, Any], index: int) -> dict[str, Any]:
        item = dict(source)
        item.setdefault("line_item_id", str(index + 1))
        item.setdefault("product_name", "")
        item.setdefault("specifications", ", ".join(str(item.get(key)) for key in ("material", "system") if item.get(key)))
        matched = self.requirements.resolve_product(item)
        errors = list(matched.get("validation_errors") or [])
        confirmation_fields = list(matched.get("confirmation_required_fields") or [])
        candidate = matched.get("price_match_details") or {}
        catalog_match_is_verified = matched.get("price_source") == "local_catalog"
        pricing_candidate = candidate if catalog_match_is_verified else {}
        price_type = str(pricing_candidate.get("price_type") or "").upper()
        expected_unit = PRICE_UNITS.get(price_type)
        pack_capacity = _decimal(
            pricing_candidate.get("box_quantity") or pricing_candidate.get("standard_package_qty")
            or matched.get("quantity_per_box") or item.get("quantity_per_box")
        )
        if price_type in {"PER_LENGTH", "PER_METER"}:
            pack_capacity = None
        if pack_capacity is not None and pack_capacity <= 0:
            pack_capacity = None
        matched["quantity_per_box"] = float(pack_capacity) if pack_capacity is not None else ""
        raw_unit = str(item.get("unit") or "").strip().lower()
        unit = UNIT_ALIASES.get(raw_unit)
        raw_quantity = _decimal(item.get("quantity"))
        boxes = _decimal(item.get("number_of_boxes"))
        if boxes is None and unit == "box":
            boxes = raw_quantity
        if boxes is not None and boxes < 0:
            errors.append("Number of boxes cannot be negative.")
        if boxes is not None and boxes > 0 and boxes != boxes.to_integral_value():
            errors.append("Number of boxes must be a whole number.")

        quantity = raw_quantity
        if boxes is not None and boxes > 0:
            if price_type in {"PER_LENGTH", "PER_METER"}:
                errors.append("This product is priced by length or meter; enter its total quantity instead of boxes.")
            elif price_type == "PER_BOX":
                quantity = boxes
                unit = "box"
                matched["total_quantity"] = float(pack_capacity * boxes) if pack_capacity is not None else ""
            elif pack_capacity is None:
                errors.append("The catalog has no package capacity for this item; enter a loose quantity instead of boxes.")
            else:
                quantity = pack_capacity * boxes
                unit = "piece"
                matched["total_quantity"] = float(quantity)
            matched["number_of_boxes"] = int(boxes) if boxes == boxes.to_integral_value() else float(boxes)
        else:
            matched["number_of_boxes"] = float(quantity) if price_type == "PER_BOX" and quantity is not None else ""
            matched["total_quantity"] = float(quantity) if quantity is not None else ""
            if price_type == "PER_BOX" and quantity is not None:
                matched["total_quantity"] = float(pack_capacity * quantity) if pack_capacity is not None else ""

        if raw_unit and unit is None:
            errors.append(f"Unsupported unit '{raw_unit}'. Use piece, box, meter (m), or length when supported by the catalog.")
        if expected_unit and unit is None:
            unit = expected_unit
            matched["unit_source"] = "local_catalog"
        elif expected_unit is None:
            if unit:
                matched["unit_source"] = "user_confirmation"
                confirmation_fields.append("unit")
            else:
                errors.append("Enter a supported unit; the local catalog does not specify the price unit for this product.")
        elif unit and unit != expected_unit:
            errors.append(f"Entered unit '{unit}' does not match the catalog price unit '{expected_unit}'.")
        if unit:
            matched["unit"] = unit
        matched["price_basis"] = {
            "PER_PIECE": "piece", "PER_BOX": "box", "PER_METER": "m",
            "PER_LENGTH": f"{pricing_candidate.get('length') or pricing_candidate.get('price_length') or ''} {pricing_candidate.get('length_unit') or pricing_candidate.get('price_length_unit') or 'm'} length".strip(),
        }.get(price_type, unit or "unit")

        if quantity is None:
            errors.append("Enter a valid quantity.")
        elif quantity <= 0:
            errors.append("Quantity must be greater than zero.")
        matched["quantity"] = str(quantity) if quantity is not None else ""

        if matched.get("match_ambiguous"):
            errors.append("Select the correct product from the matching catalog candidates.")
        if matched.get("price_source") != "local_catalog" or not matched.get("unit_price"):
            errors.append("A verified local catalog price is unavailable.")

        price = _decimal(matched.get("unit_price"))
        line_total: float | None = None
        unit_compatible = bool(unit) and (expected_unit == unit or expected_unit is None)
        if quantity is not None and quantity > 0 and price is not None and price >= 0 and unit_compatible and not errors:
            line_total = float((quantity * price).quantize(CENT, rounding=ROUND_HALF_UP))
        if not matched.get("size_inch"):
            confirmation_fields.append("size_inch")
        if not matched.get("part_number"):
            confirmation_fields.append("part_number")
        matched["line_total"] = line_total
        matched["validation_errors"] = list(dict.fromkeys(errors))
        matched["confirmation_required_fields"] = sorted(set(confirmation_fields))
        matched["review_status"] = "needs_review" if errors else "ready_for_review"
        matched.setdefault("line_number", index + 1)
        return matched
