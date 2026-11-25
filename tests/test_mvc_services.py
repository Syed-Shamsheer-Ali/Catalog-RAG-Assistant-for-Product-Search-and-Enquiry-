from __future__ import annotations

import sqlalchemy
from sqlalchemy import select

from app.database.session import create_session_factory, initialize_database
from app.models.entities import AuditRecord, Product, Submission
from app.repositories.product_repository import ProductRepository
from app.repositories.submission_repository import AuditRepository, SubmissionRepository
from app.services.requirement_service import RequirementService, validate_requirement_fields
from app.services.line_item_service import LineItemService


def test_requirement_service_reports_validation_and_confidence():
    result = RequirementService().extract("Need 5 CPVC pipe 1/2 inch, SCH 40")
    assert result["product_kind"] == "PIPE"
    assert result["confidence"]["product_kind"] > 0
    assert "validation_errors" in result
    assert result["input_source"] == "text"


def test_validation_rejects_invalid_quantity_and_price():
    errors = validate_requirement_fields({"product_kind": "PIPE", "quantity": "-2", "unit_price": "not-a-price"})
    assert any("Quantity" in error for error in errors)
    assert any("Unit price" in error for error in errors)


def test_multilingual_parser_handles_hindi_and_telugu_and_does_not_guess_price():
    from app.catalog.form_parser import parse_requirement_text

    hindi = parse_requirement_text("मुझे 5 सीपीवीसी पाइप 1/2 इंच चाहिए")
    telugu = parse_requirement_text("నాకు 5 సిపివిసి పైపు 1/2 అంగుళం కావాలి")
    assert hindi["product_kind"] == "PIPE"
    assert telugu["product_kind"] == "PIPE"
    assert hindi["quantity"] == "5"
    assert "unit_price" not in hindi


def test_spreadsheet_rows_are_converted_to_review_forms():
    rows = RequirementService().extract_spreadsheet(b"Product,Size,Quantity,Unit,Part Number\nCPVC pipe,1/2,5,m,ABC-1\nCPVC elbow,3/4,2,piece,ABC-2\n", "requirements.csv")
    assert len(rows) == 2
    assert rows[0]["product_kind"] == "PIPE"
    assert rows[0]["quantity"] == "5"
    assert rows[1]["part_number"] == "ABC-2"
    assert rows[0]["input_source"] == "excel"


def test_text_can_extract_several_products_from_one_request():
    rows = RequirementService().extract_many(text="Need 2 CPVC pipe 1/2 inch; Need 3 CPVC elbow 3/4 inch")
    assert len(rows) == 2
    assert [row["quantity"] for row in rows] == ["2", "3"]
    assert rows[0]["product_kind"] == "PIPE"
    assert rows[1]["product_kind"] == "FITTING"


def test_multi_input_extraction_appends_voice_and_images(monkeypatch):
    monkeypatch.setattr("app.services.requirement_service.transcribe_audio_bytes", lambda *args, **kwargs: "Need 3 CPVC elbow 3/4 inch")
    monkeypatch.setattr("app.services.requirement_service.extract_product_rows_from_image", lambda path: ([], "Need 4 CPVC tee 1 inch"))
    rows = RequirementService().extract_many(text="Need 2 CPVC pipe 1/2 inch", image_paths=["local-image"], audio=b"local-audio")
    assert len(rows) == 3
    assert [row["input_source"] for row in rows] == ["text", "image", "voice"]
    assert [row["quantity"] for row in rows] == ["2", "4", "3"]


def test_line_items_calculate_individual_and_grand_totals_deterministically():
    class CatalogStub:
        def resolve_product(self, item):
            unit = item["unit"]
            product_id = item.get("product_id", "pipe-1")
            price_type = "PER_METER" if unit in {"m", "meter"} else "PER_PIECE"
            price = 2.55 if price_type == "PER_METER" else 4.25
            return {**item, "product_id": product_id, "unit_price": price, "price_source": "local_catalog", "price_match_details": {"product_id": product_id, "part_number": product_id, "price_type": price_type}, "part_number": product_id, "match_ambiguous": False, "validation_errors": []}

    result = LineItemService(CatalogStub()).prepare([
        {"product_name": "CPVC pipe", "quantity": "2", "unit": "m"},
        {"product_name": "CPVC elbow", "quantity": "3", "unit": "piece", "product_id": "elbow-1"},
    ])
    assert [item["line_total"] for item in result["line_items"]] == [5.1, 12.75]
    assert result["grand_total"] == 17.85
    assert result["is_complete"] is True


def test_box_count_expands_piece_quantity_using_catalog_pack_capacity():
    class PackCatalog:
        def resolve_product(self, item):
            candidate = {"product_id": "elbow-1", "part_number": "70000537", "price_type": "PER_PIECE", "box_quantity": 100, "price": 26.0}
            return {**item, "unit_price": 26.0, "price_source": "local_catalog", "price_match_details": candidate, "part_number": "70000537", "quantity_per_box": 100, "validation_errors": []}

    result = LineItemService(PackCatalog()).prepare([{"product_name": "90 degree elbow", "number_of_boxes": 3}])
    item = result["line_items"][0]
    assert item["quantity_per_box"] == 100
    assert item["number_of_boxes"] == 3
    assert item["total_quantity"] == 300
    assert item["quantity"] == "300"
    assert item["unit"] == "piece"
    assert item["line_total"] == 7800.0
    assert result["grand_total"] == 7800.0


def test_package_capacity_does_not_force_loose_piece_quantity_into_boxes():
    class PackCatalog:
        def resolve_product(self, item):
            candidate = {"product_id": "elbow-1", "part_number": "70000537", "price_type": "PER_PIECE", "box_quantity": 100, "price": 26.0}
            return {**item, "unit_price": 26.0, "price_source": "local_catalog", "price_match_details": candidate, "part_number": "70000537", "quantity_per_box": 100, "validation_errors": []}

    result = LineItemService(PackCatalog()).prepare([{"product_name": "90 degree elbow", "quantity": "7", "unit": "piece"}])
    item = result["line_items"][0]
    assert item["quantity_per_box"] == 100
    assert item["number_of_boxes"] == ""
    assert item["total_quantity"] == 7
    assert item["line_total"] == 182.0


def test_box_priced_items_charge_per_box_and_report_content_quantity():
    class BoxCatalog:
        def resolve_product(self, item):
            candidate = {"product_id": "fastener-kit", "part_number": "BOX-1", "price_type": "PER_BOX", "box_quantity": 50, "price": 420.0}
            return {**item, "unit_price": 420.0, "price_source": "local_catalog", "price_match_details": candidate, "part_number": "BOX-1", "quantity_per_box": 50, "validation_errors": []}

    result = LineItemService(BoxCatalog()).prepare([{"product_name": "Fastener kit", "number_of_boxes": 2}])
    item = result["line_items"][0]
    assert item["unit"] == "box"
    assert item["quantity"] == "2"
    assert item["total_quantity"] == 100
    assert item["price_basis"] == "box"
    assert item["line_total"] == 840.0


def test_line_items_flag_unsupported_units_and_duplicates():
    class CatalogStub:
        def resolve_product(self, item):
            return {**item, "product_id": "same-sku", "unit_price": 5, "price_source": "local_catalog", "price_match_details": {"product_id": "same-sku", "part_number": "same-sku", "price_type": "PER_PIECE"}, "part_number": "same-sku", "match_ambiguous": False, "validation_errors": []}

    result = LineItemService(CatalogStub()).prepare([
        {"product_name": "Elbow", "quantity": "1", "unit": "piece"},
        {"product_name": "Elbow", "quantity": "2", "unit": "pieces"},
        {"product_name": "Elbow", "quantity": "1", "unit": "carton"},
    ])
    assert result["grand_total"] is None
    assert any("Duplicate" in issue for issue in result["line_items"][1]["validation_errors"])
    assert any("Unsupported unit" in issue for issue in result["line_items"][2]["validation_errors"])


def test_unknown_catalog_unit_requires_user_entry_and_confirmation():
    class CatalogStub:
        def resolve_product(self, item):
            return {**item, "product_id": "catalog-item", "unit_price": 8, "price_source": "local_catalog", "price_match_details": {"product_id": "catalog-item", "part_number": "catalog-item", "price_type": "OTHER"}, "part_number": "catalog-item", "match_ambiguous": False, "validation_errors": []}

    service = LineItemService(CatalogStub())
    missing = service.prepare([{"product_name": "Fitting", "quantity": "2"}])
    specified = service.prepare([{"product_name": "Fitting", "quantity": "2", "unit": "piece"}])
    assert missing["grand_total"] is None
    assert specified["grand_total"] == 16.0
    assert "unit" in specified["line_items"][0]["confirmation_required_fields"]


def test_multi_line_invoice_export_has_one_csv_row_per_product(tmp_path):
    import csv

    from app.invoice_export import export_report

    report = {"invoice_id": "INV-MULTI-TEST", "customer_name": "Test", "total_amount": 8.5, "line_items": [
        {"line_number": 1, "product_name": "Pipe", "product_kind": "PIPE", "product_category": "CPVC pipes", "size_inch": "1/2", "specifications": "SCH 40", "part_number": "P1", "quantity": 2, "unit": "m", "unit_price": 3.0, "price_source": "local_catalog", "line_total": 6.0, "validation_errors": []},
        {"line_number": 2, "product_name": "Elbow", "product_category": "CPVC fittings", "size_inch": "1/2", "specifications": "", "part_number": "E1", "quantity": 1, "unit": "piece", "unit_price": 2.5, "line_total": 2.5},
    ]}
    paths = export_report(report, tmp_path)
    with open(paths["csv_path"], newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert rows[0]["product_kind"] == "PIPE"
    assert rows[0]["price_source"] == "local_catalog"
    assert rows[1]["part_number"] == "E1"
    assert rows[1]["grand_total"] == "8.5"


def test_multi_submission_requires_confirmation_and_creates_multi_line_report(monkeypatch):
    from app.services.submission_service import SubmissionService

    candidate = {"product_id": "SKU-1", "part_number": "SKU-1", "product_name": "CPVC pipe", "product_kind": "PIPE", "product_category": "CPVC pipes", "size_inch": "1/2", "price": 5.0, "price_type": "PER_METER", "match_score": 0.99}
    monkeypatch.setattr("app.services.requirement_service.local_rag_price_lookup", lambda **kwargs: {"price": 5.0, "matches": [candidate], "best_match": candidate})
    monkeypatch.setattr("app.services.submission_service.export_report", lambda report: {"pdf_path": "local.pdf", "report": report})
    service = SubmissionService(persist=False)
    request = {"customer_name": "Test", "line_items": [{"product_name": "Pipe", "product_kind": "PIPE", "product_category": "CPVC pipes", "size_inch": "1/2", "quantity": "2", "unit": "m"}]}

    unconfirmed = service.submit(request, confirmed=False)
    finalized = service.submit(request, confirmed=True)

    assert unconfirmed["success"] is False
    assert finalized["success"] is True
    assert finalized["report"]["line_items"][0]["line_total"] == 10.0
    assert finalized["grand_total"] == 10.0
















def test_ambiguous_catalog_matches_need_selection_and_use_selected_price(monkeypatch):
    first = {"product_id": "p1", "part_number": "part-1", "product_kind": "PIPE", "product_name": "CPVC Pipe", "size_inch": "1/2", "price": 10.0, "match_score": 0.91}
    second = {"product_id": "p2", "part_number": "part-2", "product_kind": "PIPE", "product_name": "CPVC Pipe", "size_inch": "1/2", "price": 20.0, "match_score": 0.90}
    monkeypatch.setattr("app.services.requirement_service.local_rag_price_lookup", lambda **kwargs: {"price": 10.0, "matches": [first, second], "best_match": first})
    values = {"product_kind": "PIPE", "product_category": "CPVC pipes", "size_inch": "1/2", "quantity": "2"}

    service = RequirementService()
    unresolved = service.resolve_product(values)
    selected = service.resolve_product({**values, "selected_product_id": "p2"})

    assert unresolved["match_ambiguous"] is True
    assert unresolved["review_status"] == "needs_review"
    assert selected["review_status"] == "ready_for_review"
    assert selected["unit_price"] == 20.0
    assert selected["part_number"] == "part-2"


def test_repositories_persist_catalog_submission_and_audit(tmp_path):
    engine = initialize_database(sqlalchemy.create_engine(f"sqlite:///{tmp_path / 'mvc.db'}"))
    session = create_session_factory(engine)()
    try:
        ProductRepository(session).upsert_records([{"product_id": "sku-1", "part_number": "123", "product_kind": "PIPE", "product_name": "CPVC pipe", "price": 12.5, "source_document": "local.csv", "source_page": 1}])
        SubmissionRepository(session).save({"quantity": "2"}, {"invoice_id": "INV-1", "customer_name": "Test", "total_amount": 25, "status": "submitted"})
        AuditRepository(session).record("submission.finalized", "INV-1", details={"price_source": "local_catalog"})
        session.commit()
        assert session.get(Product, "sku-1").price == 12.5
        assert len(list(session.scalars(select(Submission)).all())) == 1
        audit = session.scalar(select(AuditRecord))
        assert audit.event_type == "submission.finalized"
    finally:
        session.close()
        engine.dispose()
