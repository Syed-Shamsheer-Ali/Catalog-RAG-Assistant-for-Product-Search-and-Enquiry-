from __future__ import annotations

import json
from pathlib import Path

from app.catalog.pdf_table_ingest import ingest_pdf
from app.services.line_item_service import LineItemService
from app.services.requirement_service import RequirementService

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PDF = ROOT / "data" / "raw" / "Product_Price_List.pdf"


def test_pdf_catalog_rows_and_sample_requirements_resolve_safely(tmp_path, monkeypatch):
    catalog_path = tmp_path / "catalog.json"
    records = ingest_pdf(CATALOG_PDF, catalog_path)
    assert len(records) == len({row["part_number"] for row in records})
    by_part = {row["part_number"]: row for row in records}

    pipe_3m = by_part["70000247"]
    pipe_5m = by_part["70000253"]
    assert (pipe_3m["price"], pipe_3m["price_type"], pipe_3m["length"]) == (360.0, "PER_LENGTH", 3.0)
    assert (pipe_5m["price"], pipe_5m["price_type"], pipe_5m["length"]) == (600.0, "PER_LENGTH", 5.0)
    assert pipe_3m["price_per_meter"] == 120.0
    assert by_part["70000560"]["price_type"] == "PER_PIECE"
    assert by_part["70000560"]["price"] == 30.0
    assert by_part["70000587"]["box_quantity"] == 400
    assert by_part["70000462"]["price"] == 77.0
    assert by_part["70002470"]["product_variant"] == "15 ml Tube"
    assert by_part["70000247"]["effective_from"] == "2025-03-01"
    assert json.loads(catalog_path.read_text(encoding="utf-8"))[0]["source_document"] == "Product_Price_List.pdf"

    monkeypatch.setattr("app.rag_price.CATALOG_PATH", catalog_path)
    service = LineItemService(RequirementService())

    clear_match = service.prepare([{
        "product_name": "Elbow 45 degree", "product_kind": "FITTING", "size_inch": "1/2", "quantity": "10",
    }])
    elbow = clear_match["line_items"][0]
    assert elbow["part_number"] == "70000560"
    assert elbow["match_ambiguous"] is False
    assert elbow["line_total"] == 300.0

    specified_pipe = service.prepare([{
        "product_name": "Pipe SDR 11", "product_kind": "PIPE", "size_inch": "1/2",
        "specifications": "3 m", "quantity": "2",
    }])
    pipe = specified_pipe["line_items"][0]
    assert pipe["part_number"] == "70000247"
    assert pipe["unit"] == "length"
    assert pipe["line_total"] == 720.0

    underspecified_pipe = service.prepare([{
        "product_name": "CPVC pipe", "product_kind": "PIPE", "size_inch": "1/2", "quantity": "2",
    }])
    assert underspecified_pipe["grand_total"] is None
    assert underspecified_pipe["line_items"][0]["match_ambiguous"] is True


def test_compound_size_matching_requires_all_dimensions(tmp_path):
    from app.catalog.matcher import match_products

    catalog_path = tmp_path / "compound.json"
    catalog_path.write_text(json.dumps([
        {"product_id": "a", "part_number": "70000001", "product_kind": "FITTING", "product_name": "Reducer Tee", "size_inch": "1/2 x 1/2 x 3/4", "price": 77},
        {"product_id": "b", "part_number": "70000002", "product_kind": "FITTING", "product_name": "Reducer Coupler", "size_inch": "1/2 x 3/4", "price": 38},
    ]), encoding="utf-8")
    matches = match_products({"kind": "FITTING", "size": "1/2 × 3/4 inch"}, catalog_path)
    assert matches
    assert matches[0]["product_id"] == "b"
    assert all(row["part_number"] != "70000001" for row in matches)
