"""Build a searchable local product catalog from the converted Ashirvad CSV."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "data/raw/Ashirvad_CPVC_PriceList_converted.csv"
DEFAULT_OUTPUT = ROOT / "data/processed/ashirvad_products.json"
PART_RE = re.compile(r"(?<!\d)(?:[357]\d{7})(?!\d)")
FRAC = {"½": "1/2", "¼": "1/4", "¾": "3/4", "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8"}


def _clean(value: str) -> str:
    value = (value or "").strip().replace("\u00a0", " ")
    for char, fraction in FRAC.items():
        value = value.replace(char, fraction)
    return re.sub(r"\s+", " ", value)


def _number(value: str) -> float | None:
    value = _clean(value).replace(",", "")
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return float(value)
    # Repair common OCR splitting in merged cells (e.g. "53 600" -> 53600).
    if re.fullmatch(r"\d{1,3}(?: \d{3})+", value):
        return float(value.replace(" ", ""))
    return None


def _size(cells: list[str]) -> tuple[str | None, str | None]:
    cm = inch = None
    for value in cells:
        value = _clean(value)
        if not value:
            continue
        if re.search(r"\d(?:\.\d+)?\s*x\s*\d", value, re.I):
            # CSV headings can be repeated; keep likely dimension strings only.
            if re.search(r"\d", value):
                return value, value
        if re.fullmatch(r"\d+(?:\.\d+)?", value) and float(value) <= 25:
            cm = cm or value
        if re.fullmatch(r"\d+(?:/\d+)?(?:\s*\d+/\d+)?", value):
            inch = inch or value
    return cm, inch


def ingest_csv(source: str | Path = DEFAULT_SOURCE, output: str | Path = DEFAULT_OUTPUT) -> list[dict[str, Any]]:
    source = Path(source)
    records: list[dict[str, Any]] = []
    section = ""
    seen: set[str] = set()
    with source.open(encoding="utf-8-sig", newline="") as handle:
        for row_no, row in enumerate(csv.reader(handle), start=1):
            cells = [_clean(cell) for cell in row]
            content = [c for c in cells[1:] if c]
            if not content:
                continue
            # Section labels are rows without a product part number.
            joined = " ".join(content)
            # HSN codes are not product numbers; do not interpret section heading codes as SKUs.
            search_text = re.sub(r"HSN\s*CODE\s*:?\s*\d+", "", joined, flags=re.I)
            part_match = PART_RE.search(search_text)
            if not part_match:
                if "warranty" not in joined.lower() and "manufactured from" not in joined.lower() and any(word in joined.lower() for word in ("pipe", "elbow", "tee", "valve", "coupler", "adapter", "cement", "bushing", "nipple", "cap", "flange", "union", "bend", "reducer", "clamp", "plug", "washer", "cistern", "trap", "filter")):
                    section = re.sub(r"\s*[-–:]?\s*HSN\s*CODE.*", "", joined, flags=re.I).strip(" -:")
                continue
            part = part_match.group(0)
            if part in seen:
                continue
            # Ignore split/garbled OCR rows where the part number is embedded in prose.
            if len(cells) > 1 and len(part) != 8:
                continue
            part_cell = next((i for i, cell in enumerate(cells) if part in cell), len(cells) - 1)
            kind = "PIPE" if "pipe" in section.lower() else "VALVE" if "valve" in section.lower() else "FITTING"
            sdr_match = re.search(r"\bSDR\s*([\d.]+)", section, re.I)
            class_match = re.search(r"\bClass\s*(\d+)\b", section, re.I)
            all_values = [c for c in cells if c]
            cm, inch = _size(cells[1:part_cell])
            # The values after the SKU are package, box and price fields. Skip the page number.
            trailing = [_number(c) for c in cells[part_cell + 1:]]
            nums = [n for n in trailing if n is not None]
            nums = [n for n in nums if n is not None]
            # Product rows place price at the right; the last numeric cell is generally MRP.
            price = nums[-1] if nums else None
            # Standard package and box count are adjacent numeric fields before MRP in most tables.
            std_pkg = box_qty = None
            if len(nums) >= 3:
                std_pkg, box_qty = int(nums[0]), int(nums[1])
            elif len(nums) == 2:
                std_pkg = int(nums[0])
            if kind == "PIPE":
                before_sku = [_number(c) for c in cells[1:part_cell]]
                before_sku = [n for n in before_sku if n is not None]
                # Pipe rows list package count and per-metre MRP before the SKU;
                # OCR may split the separate 3 m / 5 m prices after it.
                std_pkg = int(before_sku[-2]) if len(before_sku) >= 2 else None
                price = before_sku[-1] if before_sku else price
                box_qty = None
            name = section or "Ashirvad CPVC product"
            record = {
                "product_id": f"ashirvad-{part}", "product_kind": kind,
                "product_category": "CPVC pipes" if kind == "PIPE" else "CPVC fittings and accessories",
                "product_name": name, "product_variant": None, "material": "CPVC",
                "system": "CPVC", "class_name": f"Class {class_match.group(1)}" if class_match else None,
                "sdr": sdr_match.group(1) if sdr_match else None, "schedule": None,
                "size_cm": cm, "size_inch": inch, "size_text": inch or cm,
                "compound_size": inch if inch and "x" in inch.lower() else None,
                "part_number": part, "standard_package_qty": std_pkg, "box_quantity": box_qty,
                "price": price, "price_type": "PER_METER" if kind == "PIPE" else "OTHER",
                "source_document": source.name, "source_page": int(cells[0]) if cells[0].isdigit() else 0,
                "source_section": name, "source_row": row_no,
                "original_text": " | ".join(c for c in cells if c), "needs_review": False,
                "review_reasons": [], "attributes": {},
            }
            records.append(record)
            seen.add(part)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return records


if __name__ == "__main__":
    products = ingest_csv()
    print(f"Indexed {len(products)} products into {DEFAULT_OUTPUT}")
