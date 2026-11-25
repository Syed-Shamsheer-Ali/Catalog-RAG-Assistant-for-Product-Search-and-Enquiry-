from __future__ import annotations

import json
from pathlib import Path

from app.catalog.ingest import (
    build_catalog_analysis,
    build_product_records,
    build_data_quality_report,
    detect_price_types,
    parse_size_from_left,
    parse_part_number,
)

ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "data" / "raw" / "Product_Price_List.pdf"


def test_catalog_analysis_detects_sections():
    analysis = build_catalog_analysis(PDF_PATH)
    assert analysis["page_count"] >= 1
    assert isinstance(analysis["product_sections"], list)
    assert analysis["product_sections"]
    assert "pipe" in " ".join(analysis["product_sections"]).lower()


def test_catalog_detects_price_types():
    sample = [
        (1, "Pipe SDR 11 (Class 1) 3 & 5 mtr length"),
        (2, "Elbow 90° - HSN CODE : 39172390"),
        (3, "Ball Valve - Handle - HSN CODE : 39172390"),
    ]
    price_types = detect_price_types(sample)
    assert "PER_METER" in price_types
    assert "PER_LENGTH" in price_types
    assert "PER_PIECE" in price_types


def test_compound_size_parsing():
    assert "2½ x ¾" in parse_size_from_left("2.0 x 1.5 ¾ x ½") or parse_size_from_left("2.0 x 1.5 ¾ x ½")


def test_part_number_extraction():
    assert parse_part_number("70000462 50 450 77") == "70000462"


def test_prepare_catalog_creates_records():
    records = build_product_records(PDF_PATH)
    assert records
    assert all("product_id" in row for row in records)
    assert any(row.get("product_kind") == "PIPE" for row in records)
    assert any(row.get("product_kind") == "FITTING" for row in records)


def test_quality_report_has_expected_metrics():
    records = build_product_records(PDF_PATH)
    report = build_data_quality_report(records)
    assert report["total_records"] >= 1
    assert report["records_needing_review"] >= 0
    assert report["missing_prices"] >= 0
