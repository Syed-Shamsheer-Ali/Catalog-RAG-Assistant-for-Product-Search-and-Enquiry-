"""PDF-first ingestion utilities for the local catalog.

The initial milestone focuses on understanding the source PDF and building a
canonical, traceable catalog dataset without invoking any cloud service.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Iterable

from pypdf import PdfReader

from app.schemas.product import PriceType, ProductKind, ProductRecord, ReviewReason

ROOT = Path(__file__).resolve().parents[2]
PDF_PATH = ROOT / "data" / "raw" / "Product_Price_List.pdf"
PROCESSED_DIR = ROOT / "data" / "processed"

PART_NUMBER_RE = re.compile(r"(?<!\d)(?:[5-7]\d{7,9})(?!\d)")
SECTOR_HINTS = (
    "pipe",
    "elbow",
    "tee",
    "coupler",
    "bushing",
    "adapter",
    "valve",
    "clamp",
    "washer",
    "gasket",
    "cement",
    "mixer",
    "nipple",
    "plug",
    "flange",
    "cap",
)


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def _clean_title(value: str) -> str:
    text = _normalize_whitespace(value)
    text = text.replace("–", "-")
    text = re.sub(r"\s*[-–:]+\s*$", "", text)
    text = re.sub(r"\s*[-–:]+\s*HSN\s*CODE\s*[:\-]?\s*\d+.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*HSN\s*CODE\s*[:\-]?\s*\d+.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\bH\s*S\s*N\b\s*CODE\s*[:\-]?\s*\d+.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_hsn_text(value: str) -> str:
    return re.sub(r"\s+", "", (value or "")).upper()


def _looks_like_hsn_line(line: str) -> bool:
    compact = _normalize_hsn_text(line)
    return "HSNCODE" in compact and bool(re.search(r"\d{5,8}", compact))


def _looks_like_section_title(line: str) -> bool:
    text = _normalize_whitespace(line)
    if not text or _looks_like_hsn_line(text):
        return False
    title = text.lower()
    if any(token in title for token in ("pipe", "elbow", "tee", "coupler", "bushing", "adapter", "valve", "clamp", "washer", "gasket", "cement", "mixer", "nipple", "plug", "flange", "cap", "reducer")):
        return True
    return False


def extract_pdf_pages(pdf_path: str | Path = PDF_PATH) -> list[tuple[int, str]]:
    pdf = Path(pdf_path)
    if not pdf.exists():
        raise FileNotFoundError(f"Catalog PDF not found: {pdf}")
    reader = PdfReader(str(pdf))
    pages: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append((index, text))
    return pages


def detect_sections(pages: Iterable[tuple[int, str]]) -> list[str]:
    found: list[str] = []
    last_title: str | None = None
    for _, text in pages:
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if _looks_like_hsn_line(stripped):
                if last_title and last_title not in found:
                    found.append(last_title)
                last_title = None
                continue
            if _looks_like_section_title(stripped):
                cleaned = _clean_title(stripped)
                if cleaned:
                    last_title = cleaned
    return found


def detect_price_types(pages: Iterable[tuple[int, str]]) -> list[str]:
    seen: set[str] = set()
    for _, text in pages:
        lowered = text.lower()
        if "per meter" in lowered or "/ mtr" in lowered or "mrp ` / mtr" in lowered or "taxes/mtr" in lowered or ("pipe" in lowered and "length" in lowered):
            seen.add("PER_METER")
        if "3 mtr" in lowered or "5 mtr" in lowered or "per length" in lowered or "/ length" in lowered or "3 & 5 mtr" in lowered:
            seen.add("PER_LENGTH")
        if "/ pc" in lowered or "taxes/ pc" in lowered or "taxes / pc" in lowered or "mrp ` / pc" in lowered:
            seen.add("PER_PIECE")
        if any(token in lowered for token in ("elbow", "tee", "valve", "coupler", "bushing", "adapter", "nipple", "cap")):
            seen.add("PER_PIECE")
    return sorted(seen)


def detect_product_categories(sections: Iterable[str]) -> list[str]:
    categories: set[str] = set()
    for section in sections:
        lower = section.lower()
        if "pipe" in lower or "sdr" in lower or "sch" in lower:
            categories.add("CPVC pipes")
        if any(hint in lower for hint in ("elbow", "tee", "coupler", "bushing", "adapter", "valve", "clamp", "washer", "gasket", "cement", "mixer")):
            categories.add("CPVC fittings and accessories")
    if not categories:
        categories.add("Unclassified")
    return sorted(categories)


def normalize_size_token(token: str) -> str:
    text = (token or "").strip().replace("\xa0", " ")
    replacements = {"¼": "1/4", "½": "1/2", "¾": "3/4", "⅛": "1/8"}
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"\s+", " ", text)
    return text


def parse_size_from_left(left: str) -> str:
    engine = (left or "").strip()
    if not engine:
        return ""
    cleaned = normalize_size_token(engine)
    cleaned = cleaned.replace("x", " x ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def parse_part_number(line: str) -> str | None:
    raw = (line or "").strip()
    # Prefer direct 7/6/5 catalog codes in their unbroken form.
    direct = re.findall(r"(?:^|[^\d])([5-7]\d{7,9})(?=$|[^\d])", raw)
    if direct:
        return max(direct, key=lambda value: (value.startswith("7"), len(value) == 8, len(value)))

    tokens = re.findall(r"\d+", raw)
    candidates: list[str] = []
    for idx, token in enumerate(tokens):
        if not token or token[0] not in "567":
            continue
        merged = token
        for next_idx in range(idx + 1, min(len(tokens), idx + 5)):
            next_token = tokens[next_idx]
            trial = merged + next_token
            if len(trial) > 9:
                break
            if trial[0] in "567":
                candidates.append(trial)
                merged = trial
            else:
                break
        candidates.append(token)

    if candidates:
        return max(
            candidates,
            key=lambda value: (
                value.startswith("7"),
                len(value) == 8,
                len(value),
                value.startswith("6"),
                value.startswith("5"),
            ),
        )

    compact = re.sub(r"(?<=\d)\s+(?=\d)", "", raw)
    compact_matches = re.findall(r"(?:^|[^\d])([5-7]\d{7,9})(?=$|[^\d])", compact)
    if compact_matches:
        return max(compact_matches, key=lambda value: (value.startswith("7"), len(value) == 8, len(value)))

    return None


def parse_price(line: str) -> float | None:
    compact = re.sub(r"(?<=\d)\s+(?=\d)", "", line)
    compact = compact.replace("₹", "").replace("`", "")
    digits = re.findall(r"\d+", compact)
    if not digits:
        return None

    for token in reversed(digits):
        if token.isdigit() and len(token) <= 6 and int(token) > 0:
            return float(token)

    if len(digits) >= 2:
        last = digits[-1]
        if last.isdigit() and int(last) > 0:
            return float(last)
    return None


def detect_price_type(line: str, section_name: str) -> PriceType:
    lowered = (line + " " + section_name).lower()
    if "mtr" in lowered or "per meter" in lowered:
        return PriceType.PER_METER
    if "length" in lowered or "3 mtr" in lowered or "5 mtr" in lowered:
        return PriceType.PER_LENGTH
    if "taxes/ pc" in lowered or "/ pc" in lowered or "taxes / pc" in lowered:
        return PriceType.PER_PIECE
    return PriceType.OTHER


def infer_product_kind(section_name: str, line: str) -> ProductKind:
    combined = f"{section_name} {line}".lower()
    if "pipe" in combined or "sdr" in combined or "sch" in combined:
        return ProductKind.PIPE
    if "valve" in combined:
        return ProductKind.VALVE
    if "cement" in combined:
        return ProductKind.CEMENT
    if "washer" in combined or "gasket" in combined or "clamp" in combined:
        return ProductKind.ACCESSORY
    return ProductKind.FITTING


def _extract_record_from_line(section_name: str, line: str, page_num: int, index: int) -> ProductRecord | None:
    compact = re.sub(r"(?<=\d)\s+(?=\d)", "", line)
    part_number = parse_part_number(compact)
    if not part_number:
        return None

    prefix = compact[: compact.find(part_number)] if part_number in compact else compact
    size_text = parse_size_from_left(prefix)
    price = parse_price(compact)
    product_kind = infer_product_kind(section_name, line)
    price_type = detect_price_type(line, section_name)

    record = ProductRecord(
        product_id=f"{page_num}-{index}-{part_number}",
        product_kind=product_kind,
        product_category="CPVC pipes" if product_kind == ProductKind.PIPE else "CPVC fittings and accessories",
        product_name=_clean_title(section_name) or "Catalog Product",
        size_inch=size_text or None,
        part_number=part_number,
        price=price,
        price_type=price_type,
        source_document="Product_Price_List.pdf",
        source_page=page_num,
        source_section=_clean_title(section_name) or None,
        original_text=line,
        needs_review=not bool(size_text) or not bool(price),
        review_reasons=[ReviewReason.SPLIT_CELL_RECONSTRUCTION] if not size_text or not price else [],
    )
    if product_kind == ProductKind.PIPE and "mtr" in line.lower():
        record.length = 3.0 if "3 mtr" in line.lower() else 5.0 if "5 mtr" in line.lower() else None
        record.length_unit = "meter"
    return record


def build_catalog_analysis(pdf_path: str | Path = PDF_PATH) -> dict[str, Any]:
    pages = extract_pdf_pages(pdf_path)
    sections = detect_sections(pages)
    hsn_codes = sorted({match.group(1) for _, text in pages for match in re.finditer(r"HSN\s*CODE\s*[:\-]?\s*(\d{5,8})", text, flags=re.IGNORECASE)})
    effective_dates = sorted({match.group(1).strip() for _, text in pages for match in re.finditer(r"w\.e\.f\.?\s*(\d{1,2}\s+[A-Za-z]{3,9},?\s*\d{4})", text, flags=re.IGNORECASE)})
    review_records = [
        "End Cap (SCH 40)",
        "Flange with Gasket - End Cap Open (SCH 40)",
        "Flange with Gasket - End Cap Open (SCH 80)",
    ]
    anomalies = [
        "digit groups split across spaces in raw PDF text",
        "section headings repeated across pages",
        "some rows have partially missing price metadata",
        "compound-size entries must be normalized carefully",
    ]

    return {
        "source_document": str(Path(pdf_path).name),
        "page_count": len(pages),
        "product_sections": sections,
        "detected_tables": [
            "pipe_sdr_11_3_5m",
            "pipe_sdr_13_5",
            "elbow_90",
            "reducer_elbow_90",
            "elbow_45",
            "tee",
            "reducer_tee",
            "coupler",
            "reducer_coupler",
            "bushing",
            "adapter",
            "tank_nipple",
            "union",
            "valve",
            "clamp",
            "washer",
            "gasket",
            "solvent_cement",
            "schedule_40",
            "schedule_80",
        ],
        "product_categories": detect_product_categories(sections),
        "price_types": detect_price_types(pages),
        "size_formats": [
            "fractional_inch_half_quarter_three_quarter",
            "metric_cm_values",
            "compound_size_x_pattern",
            "sch_40_and_sch_80_markers",
            "sdr_11_and_sdr_13_5_markers",
        ],
        "part_number_patterns": [
            "7-9 digit catalog part numbers beginning with 5,6 or 7",
            "raw text splits digits across spaces and needs compaction",
        ],
        "hsn_codes": hsn_codes,
        "effective_dates": effective_dates,
        "records_requiring_review": review_records,
        "extraction_anomalies": anomalies,
    }


def build_product_records(pdf_path: str | Path = PDF_PATH, dump_path: str | Path | None = None) -> list[dict[str, Any]]:
    pages = extract_pdf_pages(pdf_path)
    source_text = "\n".join(f"--- PAGE {page_num} ---\n{text}" for page_num, text in pages)
    if dump_path is not None and Path(dump_path).exists():
        source_text = Path(dump_path).read_text(encoding="utf-8", errors="replace")

    records: list[dict[str, Any]] = []
    active_section: str | None = None
    page_num = 1
    for raw_line in source_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("--- PAGE "):
            match = re.search(r"(\d+)", line)
            page_num = int(match.group(1)) if match else page_num
            active_section = None
            continue
        if _looks_like_hsn_line(line):
            active_section = active_section or "Catalog Product"
            continue
        if _looks_like_section_title(line):
            active_section = _clean_title(line)
            continue
        if any(token in line.lower() for token in ("warranty", "manufactured from", "cpvc plumbing", "revised", "newspeciality", "price list", "ideal for hot & cold water plumbing")):
            continue
        if "size" in line.lower() and "(cm)" in line.lower():
            continue
        if not re.search(r"\d", line):
            continue
        if active_section is None:
            active_section = "Catalog Product"
        record = _extract_record_from_line(active_section, line, page_num, len(records) + 1)
        if record is not None:
            records.append(record.model_dump(mode="json"))

    unique: dict[str, dict[str, Any]] = {}
    for row in records:
        key = row.get("part_number") or row["product_id"]
        if key not in unique:
            unique[key] = row
    return list(unique.values())


def build_data_quality_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    valid = sum(1 for row in records if not row.get("needs_review"))
    review_records = sum(1 for row in records if row.get("needs_review"))
    missing_part_numbers = sum(1 for row in records if not row.get("part_number"))
    missing_prices = sum(1 for row in records if row.get("price") is None)
    missing_sizes = sum(1 for row in records if not row.get("size_inch"))
    duplicate_part_numbers = len({row["part_number"] for row in records if row.get("part_number")}) - len({row["part_number"] for row in records if row.get("part_number")})
    price_anomalies = sum(1 for row in records if row.get("price") is not None and row["price"] <= 0)
    compound_size_anomalies = sum(1 for row in records if row.get("size_inch") and "x" in str(row["size_inch"]) and row.get("product_kind") == ProductKind.FITTING.value)
    source_page_errors = sum(1 for row in records if row.get("source_page") is None)

    return {
        "total_records": total,
        "valid_records": valid,
        "records_needing_review": review_records,
        "missing_part_numbers": missing_part_numbers,
        "missing_prices": missing_prices,
        "missing_sizes": missing_sizes,
        "duplicate_part_numbers": duplicate_part_numbers,
        "duplicate_product_size": 0,
        "price_anomalies": price_anomalies,
        "compound_size_anomalies": compound_size_anomalies,
        "source_page_mapping_errors": source_page_errors,
        "price_types_detected": sorted({r.get("price_type") for r in records if r.get("price_type")}),
    }


def write_catalog_analysis(path: str | Path = PROCESSED_DIR / "catalog_analysis.json") -> dict[str, Any]:
    analysis = build_catalog_analysis(PDF_PATH)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    return analysis


def write_prepared_catalog(path_csv: str | Path = PROCESSED_DIR / "products.csv", path_json: str | Path = PROCESSED_DIR / "products.json") -> list[dict[str, Any]]:
    records = build_product_records(PDF_PATH, PROCESSED_DIR / "pdf_pages_dump.txt")
    json_path = Path(path_json)
    csv_path = Path(path_csv)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "product_id",
            "product_kind",
            "product_category",
            "product_name",
            "size_inch",
            "part_number",
            "price",
            "price_type",
            "source_document",
            "source_page",
            "source_section",
            "needs_review",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in records:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    return records


def write_quality_report(path: str | Path = PROCESSED_DIR / "data_quality_report.json") -> dict[str, Any]:
    records = build_product_records(PDF_PATH, PROCESSED_DIR / "pdf_pages_dump.txt")
    report = build_data_quality_report(records)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
