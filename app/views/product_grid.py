from __future__ import annotations

import re
import math
from typing import Any

GRID_COLUMNS = [
    "Item Name", "Size / Specification", "Product Code / Part Number",
    "Quantity per Box", "Number of Boxes", "Total Quantity", "Unit", "Unit Price",
    "Total Price", "Status", "Actions",
]
RUPEE = "\u20b9"


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(str(value).replace(",", "").strip())
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _currency(value: Any, basis: str = "") -> str:
    amount = _number(value)
    if amount is None:
        return "Needs Review"
    return f"{RUPEE}{amount:,.2f}" + (f" / {basis}" if basis else "")


def build_grid_rows(source_items: list[dict[str, Any]], prepared_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, source in enumerate(source_items):
        prepared = prepared_items[index] if index < len(prepared_items) else source
        price_type = str((prepared.get("price_match_details") or {}).get("price_type") or "").upper()
        is_length_basis = price_type in {"PER_LENGTH", "PER_METER"}
        size_parts = [str(value).strip() for value in (source.get("size_inch") or prepared.get("size_inch"), source.get("specifications") or prepared.get("specifications")) if value]
        total_quantity = prepared.get("total_quantity", prepared.get("quantity", source.get("quantity", "")))
        boxes = source.get("number_of_boxes") or prepared.get("number_of_boxes", "")
        if not boxes and str(source.get("unit") or "").lower() in {"box", "boxes"}:
            boxes = source.get("quantity", "")
        package_size = "" if is_length_basis else prepared.get("quantity_per_box", source.get("quantity_per_box", ""))
        status = prepared.get("catalog_match_status") or ("Needs Review" if prepared.get("matches") else "Not Found")
        if prepared.get("validation_errors"):
            status = "Needs Review"
        price = prepared.get("unit_price") if prepared.get("price_source") == "local_catalog" else None
        rows.append({
            "line_item_id": source.get("line_item_id", prepared.get("line_item_id", str(index + 1))),
            "Item Name": source.get("product_name") or prepared.get("product_name") or "",
            "Size / Specification": " | ".join(size_parts),
            "Product Code / Part Number": source.get("part_number") or prepared.get("part_number") or prepared.get("product_code") or "",
            "Quantity per Box": package_size or "",
            "Number of Boxes": boxes or "",
            "Total Quantity": total_quantity if total_quantity not in (None, "") else "",
            "Unit": source.get("unit") or prepared.get("unit") or "",
            "Unit Price": _currency(price, prepared.get("price_basis") or "") if price is not None else "Needs Review",
            "Total Price": _currency(prepared.get("line_total")) if prepared.get("line_total") is not None else "—",
            "Status": status,
            "Actions": False,
        })
    return rows


def merge_grid_rows(grid_rows: list[dict[str, Any]], source_items: list[dict[str, Any]], prepared_items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    source_by_id = {str(item.get("line_item_id")): dict(item) for item in source_items if item.get("line_item_id")}
    prepared_by_id = {str(item.get("line_item_id")): item for item in prepared_items if item.get("line_item_id")}
    updated: list[dict[str, Any]] = []
    removed: list[str] = []
    for row in grid_rows:
        line_id = str(row.get("line_item_id") or "")
        if bool(row.get("Actions")):
            if line_id:
                removed.append(line_id)
            continue
        item = source_by_id.get(line_id, {"line_item_id": line_id})
        prepared = prepared_by_id.get(line_id, {})
        item["product_name"] = str(row.get("Item Name") or "").strip()
        size_spec = str(row.get("Size / Specification") or "").strip()
        if " | " in size_spec:
            item["size_inch"], item["specifications"] = (part.strip() for part in size_spec.split(" | ", 1))
        elif re.search(r"\b(?:SDR|SCH(?:EDULE)?|CLASS)\s*\d", size_spec, re.I):
            item["size_inch"] = ""
            item["specifications"] = size_spec
        else:
            item["size_inch"] = size_spec
            item["specifications"] = ""
        item["part_number"] = str(row.get("Product Code / Part Number") or "").strip()
        item["quantity_per_box"] = _number(row.get("Quantity per Box")) or ""
        item["number_of_boxes"] = _number(row.get("Number of Boxes")) or ""
        item["quantity"] = _number(row.get("Total Quantity")) or ""
        item["unit"] = str(row.get("Unit") or "").strip().lower()
        price_type = str((prepared.get("price_match_details") or {}).get("price_type") or "").upper()
        if price_type == "PER_BOX":
            item["unit"] = "box"
            if item["number_of_boxes"]:
                item["quantity"] = item["number_of_boxes"]
        updated.append(item)
    return updated, removed
