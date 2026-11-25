#!/usr/bin/env python3
"""Prepare the searchable sellable-SKU catalog from the local price-list PDF."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app.catalog.pdf_table_ingest import ingest_pdf
from app.config import PRODUCT_DATA_PATH


def main() -> None:
    records = ingest_pdf()
    report = {
        "source_document": records[0]["source_document"] if records else "",
        "source_pages": sorted({record["source_page"] for record in records}),
        "total_sellable_skus": len(records),
        "product_kinds": dict(Counter(record["product_kind"] for record in records)),
        "section_headings": dict(Counter(record.get("section_title") or "MISSING" for record in records)),
        "records_missing_section_heading": sum(not record.get("section_title") for record in records),
        "records_missing_hsn_code": sum(not record.get("hsn_code") for record in records),
        "price_types": dict(Counter(record["price_type"] for record in records)),
        "records_needing_review": sum(bool(record["needs_review"]) for record in records),
        "missing_prices": sum(record["price"] is None for record in records),
        "missing_part_numbers": sum(not record["part_number"] for record in records),
        "manual_review_part_numbers": [record["part_number"] for record in records if record["needs_review"]],
    }
    report_path = Path(PRODUCT_DATA_PATH).with_name("catalog_quality_report.json")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Prepared {len(records)} sellable SKUs at {PRODUCT_DATA_PATH}")
    print(f"Catalog quality report: {report_path}")


if __name__ == "__main__":
    main()
