"""Extract sellable catalog rows from the local Ashirvad price-list PDF."""
from __future__ import annotations

import json
import re
from datetime import datetime
from collections import Counter
from pathlib import Path
from typing import Any

import pdfplumber

from app.config import CATALOG_PDF_PATH, PRODUCT_DATA_PATH

ROOT = Path(__file__).resolve().parents[2]
PART_RE = re.compile(r"^[357]\d{7}$")
FRACTIONS = {"¼": "1/4", "½": "1/2", "¾": "3/4", "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8"}
CM_TO_INCH = {
    "1.5": "1/2", "2.0": "3/4", "2.5": "1", "3.2": "1 1/4", "4.0": "1 1/2",
    "5.0": "2", "6.5": "2 1/2", "8.0": "3", "10.0": "4",
}
PIPE_COLUMNS = {
    11: {"cm": 2, "inch": 3, "package": 4, "meter_price": 5, "sku3": 6, "price3": 8, "sku5": 9, "price5": 10},
    9: {"cm": 1, "inch": 2, "package": 3, "meter_price": 4, "sku3": 5, "price3": 6, "sku5": 7, "price5": 8},
}


def _clean(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ").strip()
    for source, target in FRACTIONS.items():
        text = text.replace(source, target)
    text = text.replace("�", "")
    return re.sub(r"\s+", " ", text).strip()


def _number(value: Any) -> float | None:
    text = _clean(value).replace(",", "")
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number >= 0 else None


def _size_inches(metric: str, printed_inches: str) -> str | None:
    metric = _clean(metric)
    printed_inches = _clean(printed_inches)
    if metric:
        parts = re.split(r"\s*[xX]\s*", metric)
        mapped = [CM_TO_INCH.get(part.strip()) for part in parts]
        if all(mapped):
            return " x ".join(mapped)
    if printed_inches:
        return printed_inches
    return None


def _section_title(row: list[Any]) -> str | None:
    title_cells = [str(cell or "").replace("�", "°") for cell in row]
    text = " ".join(_clean(cell) for cell in title_cells if _clean(cell))
    if "HSN CODE" not in text.upper():
        return None
    title = re.split(r"\bHSN\s*CODE\b", text, maxsplit=1, flags=re.IGNORECASE)[0]
    title = re.sub(r"\s*[-:]\s*$", "", title)
    title = title.strip()
    schedule_pipe = re.search(r"pipes? available .*?\((sch\s*\d+)\)", title, re.I)
    if schedule_pipe:
        return f"CPVC Pipe {schedule_pipe.group(1).upper()}"
    title = re.sub(r"CPVC Pipes in SCH.*?Pipes available", "Pipes available", title, flags=re.I)
    title = re.sub(r"\s+MRP\s+`.*$", "", title, flags=re.I)
    return title.strip() or None


def _hsn_code(text: str) -> str | None:
    # HSN headings in this catalog use eight-digit codes. Some PDFs place
    # adjacent column text on the same baseline, so capture the code's known
    # width instead of absorbing trailing digits from that neighboring text.
    match = re.search(r"\bHSN\s*CODE\s*[:#-]?\s*(\d{8})", text, re.I)
    return match.group(1) if match else None


def _nearby_section_heading(words: list[dict[str, Any]], table: Any) -> tuple[str, str, str | None] | None:
    """Find a section heading printed just above a table but outside its grid."""
    lines: list[dict[str, Any]] = []
    for word in sorted(words, key=lambda item: (item["top"], item["x0"])):
        line = next((candidate for candidate in reversed(lines) if abs(candidate["top"] - word["top"]) <= 2.5), None)
        if line is None:
            line = {"top": word["top"], "words": []}
            lines.append(line)
        line["words"].append(word)

    candidates: list[tuple[float, str, str, str | None]] = []
    for line in lines:
        line_words = sorted(line["words"], key=lambda item: item["x0"])
        line_text = " ".join(str(word["text"]) for word in line_words)
        title = _section_title([line_text])
        distance = table.bbox[1] - line["top"]
        line_center = (line_words[0]["x0"] + line_words[-1]["x1"]) / 2
        if (
            title
            and 0 <= distance <= 20
            and table.bbox[0] - 12 <= line_center <= table.bbox[2] + 12
        ):
            hsn = _hsn_code(line_text)
            source_heading = f"{title} - HSN CODE : {hsn}" if hsn else title
            candidates.append((distance, title, source_heading, hsn))
    if not candidates:
        return None
    _, title, source_heading, hsn = min(candidates, key=lambda item: item[0])
    return title, source_heading, hsn


def _attach_search_metadata(
    record: dict[str, Any], section_title: str, source_heading: str, hsn_code: str | None
) -> dict[str, Any]:
    record["section_title"] = section_title
    record["source_heading"] = source_heading or section_title
    record["hsn_code"] = hsn_code
    terms = (
        section_title, source_heading, hsn_code, record.get("product_name"),
        record.get("product_variant"), record.get("product_kind"),
        record.get("product_category"), record.get("size_inch"),
        record.get("size_cm"), record.get("compound_size"),
        record.get("part_number"), record.get("material"), record.get("system"),
        record.get("class_name"), record.get("sdr"), record.get("schedule"),
        record.get("original_text"),
    )
    record["search_text"] = " ".join(str(term).strip() for term in terms if term not in (None, ""))
    return record


def _kind(section: str) -> str:
    name = section.lower()
    if "valve" in name:
        return "VALVE"
    if "cement" in name:
        return "CEMENT"
    if any(token in name for token in ("washer", "gasket", "clamp", "strap", "saddle")):
        return "ACCESSORY"
    if "pipe clip" in name or "pipe clamp" in name or "pipe support" in name:
        return "ACCESSORY"
    if any(token in name for token in ("elbow", "tee", "coupler", "adapter", "nipple", "bend", "bushing", "cap", "union", "flange", "trap", "filter")):
        return "FITTING"
    if "pipe" in name or "sdr" in name:
        return "PIPE"
    return "FITTING"


def _specifications(section: str) -> dict[str, str | None]:
    return {
        "class_name": (match.group(0).replace("class", "Class").strip() if (match := re.search(r"\bclass\s*\d+", section, re.I)) else None),
        "sdr": (match.group(1) if (match := re.search(r"\bSDR\s*([\d.]+)", section, re.I)) else None),
        "schedule": (match.group(0).upper().replace("SCH", "Schedule").strip() if (match := re.search(r"\bSCH\s*\d+", section, re.I)) else None),
    }


def _record_base(section: str, page_num: int, row_num: int, size_cm: str, size_inch: str | None, part: str, raw: str, source_document: str) -> dict[str, Any]:
    kind = _kind(section)
    name = (_clean(section).replace("�", "°")) or "Ashirvad CPVC product"
    specs = _specifications(name)
    return {
        "product_id": f"ashirvad-{part}",
        "product_kind": kind,
        "product_category": "CPVC pipes" if kind == "PIPE" else "CPVC fittings and accessories",
        "product_name": name,
        "product_variant": None,
        "material": "CPVC",
        "system": "CPVC",
        **specs,
        "size_cm": size_cm or None,
        "size_inch": size_inch,
        "size_text": size_inch or size_cm or None,
        "compound_size": size_inch if size_inch and "x" in size_inch.lower() else None,
        "part_number": part,
        "standard_package_qty": None,
        "box_quantity": None,
        "price": None,
        "price_type": None,
        "length": None,
        "length_unit": None,
        "price_per_meter": None,
        "price_per_length": None,
        "price_length": None,
        "price_length_unit": None,
        "currency": "INR",
        "tax_inclusive": True,
        "source_document": source_document,
        "source_page": page_num,
        "source_section": name,
        "source_row": row_num,
        "original_text": raw,
        "needs_review": False,
        "review_reasons": [],
        "attributes": {},
    }


def _pipe_values(page: Any, words: list[dict[str, Any]], table: Any, row: Any, columns: dict[str, int], row_cells: list[Any]) -> dict[str, str]:
    """Recover pipe row fields by word centers; this handles split table cells."""
    centers: dict[int, float] = {}
    size_cell = row_cells[columns["cm"]] if columns["cm"] < len(row_cells) else None
    if not size_cell:
        return {}
    top, bottom = size_cell[1], size_cell[3]
    for key, column in columns.items():
        if key == "meter_price" or key == "price3" or key == "price5" or key.startswith("sku") or key in {"cm", "inch", "package"}:
            cell = row_cells[column] if column < len(row_cells) else None
            if cell:
                centers[column] = (cell[0] + cell[2]) / 2
    if not centers:
        return {}
    assigned: dict[int, list[tuple[float, str]]] = {index: [] for index in centers}
    for word in words:
        center_y = (word["top"] + word["bottom"]) / 2
        center_x = (word["x0"] + word["x1"]) / 2
        if not (top - 1 <= center_y <= bottom + 1 and table.bbox[0] - 1 <= center_x <= table.bbox[2] + 1):
            continue
        column = min(centers, key=lambda index: abs(center_x - centers[index]))
        assigned[column].append((word["x0"], word["text"]))
    return {key: " ".join(text for _, text in sorted(assigned.get(column, []))) for key, column in columns.items()}


def _make_pipe_variants(section: str, page: Any, words: list[dict[str, Any]], table: Any, row: list[Any], row_obj: Any, page_num: int, row_num: int, columns: dict[str, int], source_document: str) -> list[dict[str, Any]]:
    values = _pipe_values(page, words, table, row_obj, columns, row_obj.cells)
    size_cm = _clean(values.get("cm") or (row[columns["cm"]] if columns["cm"] < len(row) else ""))
    size_inch = _size_inches(size_cm, values.get("inch") or (row[columns["inch"]] if columns["inch"] < len(row) else ""))
    package = _integer(values.get("package") or (row[columns["package"]] if columns["package"] < len(row) else ""))
    meter_price = _number(values.get("meter_price") or (row[columns["meter_price"]] if columns["meter_price"] < len(row) else ""))
    raw = " | ".join(_clean(cell) for cell in row if _clean(cell))
    records: list[dict[str, Any]] = []
    for length_m, sku_key, price_key in ((3.0, "sku3", "price3"), (5.0, "sku5", "price5")):
        part = re.sub(r"\D", "", values.get(sku_key, ""))
        price = _number(values.get(price_key))
        if not PART_RE.fullmatch(part):
            continue
        record = _record_base(section, page_num, row_num, size_cm, size_inch, part, raw, source_document)
        record.update({
            "product_variant": f"{length_m:g} m length",
            "price": price,
            "price_type": "PER_LENGTH",
            "length": length_m,
            "length_unit": "meter",
            "price_per_meter": meter_price,
            "price_per_length": price,
            "price_length": length_m,
            "price_length_unit": "meter",
            "standard_package_qty": package,
        })
        if not size_inch:
            record["needs_review"] = True
            record["review_reasons"].append("MISSING_SIZE")
        if price is None:
            record["needs_review"] = True
            record["review_reasons"].append("MISSING_PRICE")
        records.append(record)
    return records


def _make_piece_record(section: str, page: Any, words: list[dict[str, Any]], table: Any, row: list[Any], row_obj: Any, page_num: int, row_num: int, source_document: str) -> dict[str, Any] | None:
    part_index = next((index for index, cell in enumerate(row) if PART_RE.fullmatch(re.sub(r"\s+", "", _clean(cell)))), None)
    if part_index is None:
        return None
    part = re.sub(r"\s+", "", _clean(row[part_index]))
    before = [_clean(cell) for cell in row[:part_index] if _clean(cell)]
    kind = _kind(section)
    variant = None
    if kind == "CEMENT":
        size_cm, printed_size = "", ""
        variant = before[-1] if before else None
    elif len(before) >= 2:
        size_cm, printed_size = before[-2], before[-1]
    elif before:
        if _number(before[0]) is None:
            size_cm, printed_size = "", ""
            variant = before[0]
        else:
            size_cm, printed_size = before[0], ""
    else:
        size_cm, printed_size = "", ""
    size_inch = _size_inches(size_cm, printed_size)
    part_cell = row_obj.cells[part_index] if part_index < len(row_obj.cells) else None
    trailing: list[str] = []
    if part_cell:
        row_mid = (part_cell[1] + part_cell[3]) / 2
        part_left = part_cell[0]
        for word in words:
            word_mid = (word["top"] + word["bottom"]) / 2
            if abs(word_mid - row_mid) <= 4 and word["x0"] >= part_left and word["x1"] <= table.bbox[2] + 1 and re.fullmatch(r"\d+(?:[,.]\d+)*", word["text"]):
                if re.sub(r"\D", "", word["text"]) != part:
                    trailing.append(word["text"])
    numbers = [_number(cell) for cell in trailing]
    numbers = [number for number in numbers if number is not None]
    price = numbers[-1] if numbers else None
    package = _integer(numbers[0]) if len(numbers) >= 2 else None
    box_qty = _integer(numbers[1]) if len(numbers) >= 3 else None
    raw = " | ".join(_clean(cell) for cell in row if _clean(cell))
    record = _record_base(section, page_num, row_num, size_cm, size_inch, part, raw, source_document)
    record.update({
        "product_variant": variant,
        "standard_package_qty": package,
        "box_quantity": box_qty,
        "price": price,
        "price_type": "PER_PIECE",
    })
    if not size_inch and not variant:
        record["needs_review"] = True
        record["review_reasons"].append("MISSING_SIZE")
    if price is None:
        record["needs_review"] = True
        record["review_reasons"].append("MISSING_PRICE")
    return record


def ingest_pdf(source: str | Path = CATALOG_PDF_PATH, output: str | Path | None = None) -> list[dict[str, Any]]:
    """Build one record per sellable SKU from the source PDF tables."""
    source_path = Path(source)
    target = Path(output) if output is not None else Path(PRODUCT_DATA_PATH)
    all_records: list[dict[str, Any]] = []
    active_section = ""
    active_source_heading = ""
    active_hsn_code: str | None = None
    review_counts: Counter[str] = Counter()
    effective_from: str | None = None

    with pdfplumber.open(source_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            if effective_from is None:
                page_text = page.extract_text() or ""
                date_match = re.search(r"w\.e\.f\.?\s*(\d{1,2})\s+([A-Za-z]{3,9}),?\s*(\d{4})", page_text, re.I)
                if date_match:
                    try:
                        effective_from = datetime.strptime(" ".join(date_match.groups()), "%d %b %Y").date().isoformat()
                    except ValueError:
                        try:
                            effective_from = datetime.strptime(" ".join(date_match.groups()), "%d %B %Y").date().isoformat()
                        except ValueError:
                            effective_from = None
            words = page.extract_words(x_tolerance=1, y_tolerance=3)
            for table in page.find_tables():
                rows = table.extract()
                if not rows:
                    continue
                nearby_heading = _nearby_section_heading(words, table)
                if nearby_heading:
                    active_section, active_source_heading, active_hsn_code = nearby_heading
                pipe_columns = PIPE_COLUMNS.get(len(rows[0]))
                pipe_table = any(
                    "pipe" in " ".join(_clean(cell) for cell in row if _clean(cell)).lower()
                    and any(token in " ".join(_clean(cell) for cell in row if _clean(cell)).lower() for token in ("mtr", "meter", "length"))
                    for row in rows
                )
                if not pipe_table:
                    pipe_table = any(
                        "size" in " ".join(_clean(cell) for cell in row if _clean(cell)).lower()
                        and "part" in " ".join(_clean(cell) for cell in row if _clean(cell)).lower()
                        and "mtr" in " ".join(_clean(cell) for cell in row if _clean(cell)).lower()
                        and "length" in " ".join(_clean(cell) for cell in row if _clean(cell)).lower()
                        for row in rows
                    )
                for row_index, row in enumerate(rows):
                    title = _section_title(row)
                    if title:
                        active_section = title
                        raw_heading = " ".join(_clean(cell) for cell in row if _clean(cell))
                        active_hsn_code = _hsn_code(raw_heading)
                        active_source_heading = f"{title} - HSN CODE : {active_hsn_code}" if active_hsn_code else title
                    joined = " ".join(_clean(cell) for cell in row if _clean(cell)).lower()
                    if "size" in joined and "part" in joined and "mrp" in joined:
                        continue
                    if not active_section:
                        continue
                    if pipe_table and _kind(active_section) == "PIPE" and pipe_columns:
                        made = _make_pipe_variants(active_section, page, words, table, row, table.rows[row_index], page_num, row_index + 1, pipe_columns, source_path.name)
                        made = [_attach_search_metadata(item, active_section, active_source_heading, active_hsn_code) for item in made]
                        all_records.extend(made)
                        for item in made:
                            if item["needs_review"]:
                                review_counts.update(item["review_reasons"])
                        continue
                    record = _make_piece_record(active_section, page, words, table, row, table.rows[row_index], page_num, row_index + 1, source_path.name)
                    if record:
                        _attach_search_metadata(record, active_section, active_source_heading, active_hsn_code)
                        all_records.append(record)
                        if record["needs_review"]:
                            review_counts.update(record["review_reasons"])

    # Duplicate SKUs are not silently allowed to multiply retrieval candidates.
    unique: dict[str, dict[str, Any]] = {}
    for record in all_records:
        part = record["part_number"]
        previous = unique.get(part)
        if previous is None:
            unique[part] = record
        elif (previous.get("price"), previous.get("price_type")) != (record.get("price"), record.get("price_type")):
            previous["needs_review"] = True
            previous["review_reasons"] = sorted(set(previous["review_reasons"] + ["CONFLICTING_EXTRACTION"]))
    result = list(unique.values())
    for record in result:
        record["effective_from"] = effective_from
        record["price_list_version"] = f"effective {effective_from}" if effective_from else None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Extracted {len(result)} sellable SKUs from {source_path.name}; review flags: {dict(review_counts)}")
    return result


if __name__ == "__main__":
    ingest_pdf()
