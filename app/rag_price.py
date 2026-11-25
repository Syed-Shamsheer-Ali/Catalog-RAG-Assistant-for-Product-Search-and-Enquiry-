from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.catalog.matcher import match_products
from app.config import PRODUCT_DATA_PATH

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = Path(PRODUCT_DATA_PATH)


def local_rag_price_lookup(product_name: str | None = None, size_inch: str | None = None, quantity: str | int | None = None, category: str | None = None, part_number: str | None = None, *, product_kind: str | None = None, product_variant: str | None = None, specifications: str | None = None, class_name: str | None = None, sdr: str | None = None, schedule: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "max_results": 10,
    }
    if product_name:
        payload["product_name"] = str(product_name)
    combined_specs = " ".join(str(value or "") for value in (product_name, specifications))
    inferred_kind = product_kind
    if not inferred_kind and product_name:
        normalized_name = str(product_name).upper()
        inferred_kind = "PIPE" if any(token in normalized_name for token in ("PIPE", "SDR", "SCH")) else "VALVE" if "VALVE" in normalized_name else "CEMENT" if "CEMENT" in normalized_name else "FITTING"
    if inferred_kind:
        payload["kind"] = inferred_kind
    if category:
        payload["category"] = category
    if size_inch:
        payload["size"] = str(size_inch)
    if part_number:
        payload["part_number"] = str(part_number)
    if product_variant:
        payload["product_variant"] = str(product_variant)
    if specifications:
        payload["specifications"] = str(specifications)
    class_match = re.search(r"\bclass\s*\d+", combined_specs, re.I)
    sdr_match = re.search(r"\bSDR\s*[\d.]+", combined_specs, re.I)
    schedule_match = re.search(r"\b(?:SCH|schedule)\s*\d+", combined_specs, re.I)
    if class_name or class_match:
        payload["class_name"] = class_name or class_match.group(0)
    if sdr or sdr_match:
        payload["sdr"] = sdr or sdr_match.group(0)
    if schedule or schedule_match:
        payload["schedule"] = schedule or schedule_match.group(0)

    matches = match_products(payload, CATALOG_PATH)
    if not matches:
        return {
            "price": 0,
            "source": "no_local_match",
            "matches": [],
            "product_code": "",
            "part_number": "",
            "std_pkg": None,
            "box_quantity": None,
            "boxes_required": 0,
        }

    best = matches[0]
    price = best.get("price")
    if price is None:
        price = 0.0

    std_pkg = best.get("standard_package_qty")
    box_qty = best.get("box_quantity")
    quantity_value = quantity if quantity not in (None, "") else 0
    try:
        requested_quantity = int(float(str(quantity_value).replace(",", "")))
    except Exception:
        requested_quantity = 0

    effective_box_qty = box_qty if box_qty not in (None, "", "N/A") else std_pkg
    boxes_required = 0
    if requested_quantity and effective_box_qty:
        boxes_required = (requested_quantity + effective_box_qty - 1) // effective_box_qty

    return {
        "price": float(price),
        "source": "local_catalog_rag",
        "matches": matches,
        "best_match": best,
        "product_code": best.get("product_id") or best.get("part_number") or "",
        "part_number": best.get("part_number") or "",
        "std_pkg": std_pkg,
        "box_quantity": box_qty,
        "boxes_required": boxes_required,
    }


def enrich_requirement_with_local_price(form_data: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(form_data)
    
    # Always look up price from catalog to get accurate pricing
    lookup = local_rag_price_lookup(
        product_name=enriched.get("product_kind") or enriched.get("product_name"),
        size_inch=enriched.get("size_inch"),
        quantity=enriched.get("quantity"),
        category=enriched.get("product_category"),
    )
    
    # Use catalog price if available and greater than 0, otherwise use entered price
    catalog_price = lookup.get("price", 0) or 0
    if catalog_price > 0:
        enriched["unit_price"] = catalog_price
        enriched["price_source"] = "catalog"
    elif not enriched.get("unit_price"):
        enriched["unit_price"] = catalog_price
        enriched["price_source"] = lookup.get("source", "unknown")
    
    enriched["product_code"] = lookup.get("product_code") or enriched.get("product_code") or ""
    enriched["part_number"] = lookup.get("part_number") or enriched.get("part_number") or ""
    enriched["std_pkg"] = lookup.get("std_pkg") or enriched.get("std_pkg")
    enriched["box_quantity"] = lookup.get("box_quantity") or enriched.get("box_quantity")
    enriched["boxes_required"] = lookup.get("boxes_required") or enriched.get("boxes_required", 0)
    enriched["price_match_details"] = lookup.get("best_match", {})
    
    return enriched
