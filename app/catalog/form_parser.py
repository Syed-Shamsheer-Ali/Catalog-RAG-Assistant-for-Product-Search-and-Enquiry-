from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

LOCALIZED_TERMS = {
    "పైపు": "pipe", "పైపులు": "pipes", "అంగుళం": "inch", "అంగుళాల": "inch",
    "కావాలి": "need", "సిపివిసి": "cpvc", "ఎల్బో": "elbow", "వాల్వ్": "valve",
    "पाइप": "pipe", "पाइपों": "pipes", "इंच": "inch", "चाहिए": "need", "सीपीवीसी": "cpvc",
    "एल्बो": "elbow", "वाल्व": "valve", "मात्रा": "quantity", "ग्राहक": "customer",
}


def _normalize_localized_terms(text: str) -> str:
    normalized = text
    for source, target in LOCALIZED_TERMS.items():
        normalized = normalized.replace(source, target)
    return normalized


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_first(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _parse_quantity(text: str) -> str:
    match = re.search(r"(?:qty|quantity)\s*[:=]?\s*(\d+)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"\b(?:need|required|require)\s+(\d+)\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"\b(\d+)\s+(?:(?:cpvc\s+)?(?:pipe|pipes|elbow|elbows|tee|tees|valve|valves|fitting|fittings|coupler))\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    # Natural phrasing may put the requested count after "of" and include a
    # product modifier, as in "1.5 size of 10 Ball Valve - Handle".
    match = re.search(
        r"\bof\s+(\d+)\s+(?=(?:[A-Za-z][A-Za-z0-9-]*\s+){0,3}(?:pipe|pipes|elbow|elbows|tee|tees|valve|valves|fitting|fittings|coupler|cement)\b)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1)
    match = re.search(r"\b(\d+)\s*(?:pcs|pieces|nos|no\.)\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return ""


def _parse_size(text: str) -> str:
    patterns = [
        r"\b(\d+(?:\.\d+)?)\s*(?:mm|cm)?\s*size\b",
        r"(?:size|diameter)\s*[:=]?\s*((?:\d+\s*/\s*\d+|\d+(?:\.\d+)?)\s*(?:[xX×]\s*(?:\d+\s*/\s*\d+|\d+(?:\.\d+)?))+(?:\s*(?:mm|cm|inches|inch))?)",
        r"(?:size|diameter)\s*[:=]?\s*(\d+\s*/\s*\d+)",
        r"(?:size|diameter)\s*[:=]?\s*(\d+\.\d+\s*x\s*\d+\s*/\s*\d+)",
        r"(?:size|diameter)\s*[:=]?\s*(\d+\s*x\s*\d+\s*/\s*\d+)",
        r"\b((?:\d+\s*/\s*\d+|\d+(?:\.\d+)?)\s*(?:[xX×]\s*(?:\d+\s*/\s*\d+|\d+(?:\.\d+)?))+)\b",
        r"\b(\d+\s*/\s*\d+)\b",
        r"\b(\d+(?:\.\d+)?\s*(?:mm|cm|inches|inch))\b",
    ]
    for pattern in patterns:
        value = _extract_first(pattern, text)
        if value:
            return re.sub(r"\s*([xX×])\s*", r" × ", value).strip()
    return ""


def _parse_price(text: str) -> str:
    match = re.search(r"(?:rate|price|unit price|per pc|mrp)\s*[:=]?\s*₹?\s*(\d+(?:\.\d+)?)", text, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _parse_unit(text: str) -> str:
    explicit = _extract_first(r"\bunit\s*[:=]\s*([A-Za-z]+)\b", text)
    if explicit:
        return explicit
    unit_pattern = r"(pcs|pieces|nos|no|each|m|meters?|metres?|mtrs?|lengths?|boxes|box)\b"
    labelled = _extract_first(r"\b(?:qty|quantity)\s*[:=]?\s*\d+(?:\.\d+)?\s*" + unit_pattern, text)
    if labelled:
        return labelled
    requested = _extract_first(r"\b(?:need|required|require)\s+\d+(?:\.\d+)?\s*" + unit_pattern, text)
    if requested:
        return requested
    leading = _extract_first(r"^\s*\d+(?:\.\d+)?\s*" + unit_pattern, text)
    return leading


def parse_requirement_text(raw_text: str) -> dict[str, Any]:
    source_text = _clean_text(raw_text)
    text = _normalize_localized_terms(source_text)
    if not text:
        return {}

    fields: dict[str, Any] = {
        "customer_name": _extract_first(r"(?:customer|client|name)\s*[:=]?\s*([A-Za-z][A-Za-z0-9 .&'-]+)", text) or "",
        "product_kind": "",
        "product_category": "",
        "size_inch": _parse_size(text),
        "material": "CPVC" if "cpvc" in text.lower() else "",
        "system": "" ,
        "quantity": _parse_quantity(text),
        "unit": _parse_unit(text),
        "unit_price": _parse_price(text),
        "notes": source_text[:180],
    }

    lowered = text.lower()
    if any(word in lowered for word in ["pipe", "sdr", "sch"]):
        fields["product_kind"] = "PIPE"
        fields["product_category"] = "CPVC pipes"
    elif any(word in lowered for word in ["washer", "gasket", "clamp", "strap", "saddle"]):
        fields["product_kind"] = "ACCESSORY"
        fields["product_category"] = "CPVC fittings and accessories"
    elif any(word in lowered for word in ["elbow", "tee", "coupler", "bushing", "adapter", "union", "nipple", "cap", "reducer", "flange", "cartridge", "filter"]):
        fields["product_kind"] = "FITTING"
        fields["product_category"] = "CPVC fittings and accessories"
    elif "valve" in lowered:
        fields["product_kind"] = "VALVE"
        fields["product_category"] = "CPVC fittings and accessories"
    elif "cement" in lowered:
        fields["product_kind"] = "CEMENT"
        fields["product_category"] = "CPVC accessories"

    if not fields["product_kind"] and "cpvc" in lowered:
        fields["product_kind"] = "PIPE"

    if "sch 40" in lowered or "schedule 40" in lowered:
        fields["system"] = "SCH 40"
    elif "sch 80" in lowered or "schedule 80" in lowered:
        fields["system"] = "SCH 80"
    elif "sdr 11" in lowered:
        fields["system"] = "SDR 11"

    if not fields["customer_name"]:
        for key in ["customer", "name", "client"]:
            if f"{key}:" in text.lower():
                fields["customer_name"] = text.split(":", 1)[1].strip()
                break

    explicit_name = _extract_first(r"(?:product(?:\s+name)?|item)\s*[:=]\s*([^,;]+)", text)
    fields["product_name"] = explicit_name
    if not fields["product_name"] and fields["product_kind"]:
        description = re.sub(r"^\s*(?:please\s+)?(?:i\s+)?(?:need|required|require)\s+\d+(?:\.\d+)?\s*", "", text, flags=re.I)
        description = re.sub(r"^\s*\d+(?:\.\d+)?\s*(?:mm|cm)?\s*size\s*(?:of\s*)?", "", description, flags=re.I)
        description = re.sub(r"^\s*of\s+", "", description, flags=re.I)
        if fields.get("quantity"):
            description = re.sub(r"^\s*" + re.escape(str(fields["quantity"])) + r"\s+", "", description)
        description = re.sub(r"\b(?:qty|quantity)\s*[:=]?\s*\d+(?:\.\d+)?", "", description, flags=re.I)
        description = re.sub(r"\s+", " ", description).strip(" ,;:-")
        fields["product_name"] = description or ""
    fields["specifications"] = ", ".join(value for value in (fields.get("material"), fields.get("system")) if value)
    fields["part_number"] = _extract_first(r"\b(?:part(?:\s*(?:number|no\.?))?|sku|product\s*code)\s*[:=#-]?\s*([A-Za-z0-9][A-Za-z0-9/-]*)", text)
    fields["hsn_code"] = _extract_first(r"\bHSN\s*(?:CODE)?\s*[:=#-]?\s*(\d{4,10})\b", text)

    return {key: value for key, value in fields.items() if value not in (None, "")}


@lru_cache(maxsize=2)
def _get_easyocr_reader(languages: tuple[str, ...]):
    import easyocr  # type: ignore
    return easyocr.Reader(list(languages), gpu=False, download_enabled=False)


def _ocr_image(image_path: str | Path) -> list[tuple[list[list[float]], str, float]]:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path}")
    try:
        from PIL import Image
        from PIL import ImageEnhance, ImageFilter, ImageOps
        import numpy as np

        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("L")
            original_width, original_height = image.size
            scale = min(4.0, max(1.0, 1400 / max(original_width, 1)))
            if scale > 1:
                image = image.resize((round(original_width * scale), round(original_height * scale)))
            image = ImageOps.autocontrast(image)
            image = ImageEnhance.Contrast(image).enhance(1.5).filter(ImageFilter.SHARPEN)
        try:
            reader = _get_easyocr_reader(("en", "hi", "te"))
        except Exception:
            reader = _get_easyocr_reader(("en",))
        result = reader.readtext(np.asarray(image), detail=1, paragraph=False)
        if scale != 1:
            result = [([[float(x) / scale, float(y) / scale] for x, y in box], text, confidence) for box, text, confidence in result]
        return [(box, str(text), float(confidence)) for box, text, confidence in result]
    except Exception:
        return []


def _group_ocr_rows(ocr: list[tuple[list[list[float]], str, float]]) -> list[list[tuple[float, str, float]]]:
    words = []
    heights = []
    for box, text, confidence in ocr:
        if not text.strip():
            continue
        ys = [point[1] for point in box]
        xs = [point[0] for point in box]
        heights.append(max(1.0, max(ys) - min(ys)))
        words.append(((min(ys) + max(ys)) / 2, (min(xs) + max(xs)) / 2, text.strip(), confidence))
    if not words:
        return []
    tolerance = max(4.0, sorted(heights)[len(heights) // 2] * 0.75)
    rows: list[tuple[float, list[tuple[float, str, float]]]] = []
    for center_y, center_x, text, confidence in sorted(words, key=lambda word: (word[0], word[1])):
        row = next((candidate for candidate in reversed(rows) if abs(candidate[0] - center_y) <= tolerance), None)
        if row is None:
            row = (center_y, [])
            rows.append(row)
        row[1].append((center_x, text, confidence))
    return [sorted(row, key=lambda word: word[0]) for _, row in rows]


def _infer_product_kind(name: str) -> str:
    lowered = name.lower()
    if any(token in lowered for token in ("clip", "cowl", "clamp", "strap", "washer", "gasket")):
        return "ACCESSORY"
    if "pipe" in lowered or re.search(r"\b(sdr|sch(?:edule)?)\s*\d", lowered):
        return "PIPE"
    if "cement" in lowered:
        return "CEMENT"
    if "valve" in lowered:
        return "VALVE"
    if re.search(r"\bplain\s+y\b", lowered) or any(token in lowered for token in ("elbow", "bend", "tee", "coupl", "bush", "adapter", "union", "nipple", "cap", "reducer", "plug")):
        return "FITTING"
    return ""


def parse_invoice_ocr_rows(ocr: list[tuple[list[list[float]], str, float]]) -> list[dict[str, Any]]:
    """Convert positioned OCR words into editable product rows from a bill table."""
    rows = _group_ocr_rows(ocr)
    if not rows:
        return []

    header_index = None
    anchors: dict[str, float] = {}
    for row_index, row in enumerate(rows):
        normalized = " ".join(word[1].lower().replace(".", "") for word in row)
        if ("qty" in normalized or "quantity" in normalized) and "rate" in normalized and ("item" in normalized or "name" in normalized):
            header_index = row_index
            labels = {
                "serial": ("sno", "s no", "s no"), "name": ("item", "name", "description"),
                "quantity": ("qty", "quantity"), "rate": ("rate", "price"),
                "unit": ("uom", "unit"),
                "amount": ("amount",), "discount": ("disc", "discount"), "net": ("netvalue", "net", "value"),
            }
            for field, tokens in labels.items():
                candidates = [x for x, text, _ in row if any(token.replace(" ", "") in text.lower().replace(".", "").replace(" ", "") for token in tokens)]
                if candidates:
                    anchors[field] = sum(candidates) / len(candidates)
            break

    if header_index is None or not {"name", "quantity", "rate"}.issubset(anchors):
        return []

    fields = sorted(anchors.items(), key=lambda value: value[1])
    products: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for row in rows[header_index + 1:]:
        cells: dict[str, list[tuple[str, float]]] = {key: [] for key in anchors}
        line_text = " ".join(text for _, text, _ in row)
        if not line_text.strip() or any(word in line_text.lower() for word in ("subtotal", "grand total", "terms and conditions")):
            continue
        for x, text, confidence in row:
            field = min(fields, key=lambda item: abs(item[1] - x))[0]
            cells[field].append((text, confidence))
        name = " ".join(text for text, _ in cells["name"]).strip(" -:|")
        qty_text = " ".join(text for text, _ in cells["quantity"])
        rate_text = " ".join(text for text, _ in cells["rate"])
        unit_text = " ".join(text for text, _ in cells.get("unit", []))
        quantity_match = re.search(r"\d[\d,]*(?:\.\d+)?", qty_text)
        rate_match = re.search(r"\d[\d,]*(?:\.\d+)?", rate_text)
        # Wrapped descriptions often produce continuation rows with no quantity.
        if not name or not quantity_match:
            if name and previous and not quantity_match:
                previous["product_name"] = f"{previous['product_name']} {name}".strip()
                previous["source_text"] = f"{previous['source_text']} {line_text}".strip()
                previous["confidence"]["product_name"] = min(previous["confidence"].get("product_name", 0.0), min((score for _, score in cells["name"]), default=0.0))
            continue

        product_name = re.sub(r"(?<=\d)O(?=\s*(?:X|×)?\s*\d*\s*MM\b)", "0", name, flags=re.I)
        product_name = re.sub(r"\b(\d+)\*(?=\s|$)", r"\1°", product_name)
        product_name = re.sub(r"\s+", " ", product_name).strip()
        size_match = re.search(r"\b\d+(?:\.\d+)?\s*(?:[xX×]\s*\d+(?:\.\d+)?\s*)?(?:mm|cm|inches|inch|in\b)|\b\d+\s*/\s*\d+(?:\s*[xX×]\s*\d+\s*/\s*\d+)+", product_name, re.I)
        size = re.sub(r"\s*([xX×])\s*", r" × ", size_match.group(0)).strip() if size_match else ""
        specs = re.findall(r"\b(?:SDR\s*\d+(?:\.\d+)?|SCH(?:EDULE)?\s*\d+|CLASS\s*\d+|\d+\s*(?:FT|MTRS?|METERS?|METRES?))\b", product_name, re.I)
        part = re.search(r"\b\d{5,}\b", product_name)
        unit_match = re.search(r"\b(pcs?|pieces?|nos?|each|m|mtr|meters?|metres?|lengths?)\b", unit_text, re.I)
        kind = _infer_product_kind(product_name)
        confidence = {
            "product_name": sum(value for _, value in cells["name"]) / max(1, len(cells["name"])),
            "quantity": sum(value for _, value in cells["quantity"]) / max(1, len(cells["quantity"])),
        }
        if rate_match:
            confidence["source_unit_price"] = sum(value for _, value in cells["rate"]) / max(1, len(cells["rate"]))
        product = {
            "product_name": product_name,
            "product_kind": kind,
            "product_category": "CPVC pipes" if kind == "PIPE" else "CPVC fittings and accessories" if kind in {"FITTING", "VALVE"} else "",
            "size_inch": size,
            "specifications": ", ".join(specs),
            "part_number": part.group(0) if part else "",
            "quantity": quantity_match.group(0).replace(",", ""),
            "unit": unit_match.group(0) if unit_match else "",
            "source_unit_price": rate_match.group(0).replace(",", "") if rate_match else "",
            "source_text": line_text,
            "confidence": confidence,
            "input_source": "image",
        }
        products.append(product)
        previous = product
    return products


def extract_product_rows_from_pdf(pdf_path: str | Path) -> list[dict[str, Any]]:
    """Read text-bearing PDF bill tables with local PDF word coordinates."""
    import pdfplumber

    products: list[dict[str, Any]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=2, y_tolerance=3, keep_blank_chars=False)
            positioned = []
            for word in words:
                positioned.append(([
                    [float(word["x0"]), float(word["top"])],
                    [float(word["x1"]), float(word["top"])],
                    [float(word["x1"]), float(word["bottom"])],
                    [float(word["x0"]), float(word["bottom"])],
                ], str(word["text"]), 1.0))
            page_products = parse_invoice_ocr_rows(positioned)
            products.extend({**product, "input_source": "pdf"} for product in page_products)
    return products


def extract_product_rows_from_image(image_path: str | Path) -> tuple[list[dict[str, Any]], str]:
    ocr = _ocr_image(image_path)
    rows = _group_ocr_rows(ocr)
    text = "\n".join(" ".join(value for _, value, _ in row) for row in rows)
    return parse_invoice_ocr_rows(ocr), text


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    import pdfplumber

    with pdfplumber.open(str(pdf_path)) as pdf:
        return "\n".join(page.extract_text(layout=False) or "" for page in pdf.pages)


def extract_text_from_image(image_path: str | Path) -> str:
    rows = _group_ocr_rows(_ocr_image(image_path))
    return "\n".join(" ".join(text for _, text, _ in row) for row in rows)


def extract_fields_from_image(image_path: str | Path) -> dict[str, Any]:
    return parse_requirement_text(extract_text_from_image(image_path))
