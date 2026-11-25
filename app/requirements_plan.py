from __future__ import annotations

from typing import Any


def calculate_boxes_for_quantity(quantity: Any, standard_pkg: Any, box_qty: Any) -> dict[str, Any]:
    try:
        requested = int(float(str(quantity).replace(",", "")))
    except Exception:
        requested = 0

    try:
        std_pkg = int(float(str(standard_pkg).replace(",", ""))) if standard_pkg not in (None, "", "N/A") else 0
    except Exception:
        std_pkg = 0

    try:
        box_qty_val = int(float(str(box_qty).replace(",", ""))) if box_qty not in (None, "", "N/A") else 0
    except Exception:
        box_qty_val = 0

    if std_pkg <= 0 and box_qty_val <= 0:
        return {"boxes_required": 0, "standard_pkg": 0, "box_qty": 0, "reason": "no_packaging_data"}

    effective_box_qty = box_qty_val if box_qty_val > 0 else std_pkg
    boxes_required = 0 if requested <= 0 else (requested + effective_box_qty - 1) // effective_box_qty

    return {
        "boxes_required": boxes_required,
        "standard_pkg": std_pkg,
        "box_qty": effective_box_qty,
        "reason": "calculated",
    }
