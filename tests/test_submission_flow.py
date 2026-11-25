from __future__ import annotations

from app.ui import RequirementFormUI
from app.invoice import InvoiceReport
from app.services.requirement_service import RequirementService


def test_auto_fill_and_submit_invoice_flow():
    form = RequirementFormUI("Need 5 CPVC pipe 1/2 inch, SDR 11, 3 m length")
    assert form.form_data
    assert not form.form_data.get("unit")
    matched = form.match()
    assert matched["part_number"] == "70000247"
    assert matched["unit_price"] == 360.0
    assert matched["price_source"] == "local_catalog"
    result = form.submit()
    assert result["success"] is True
    assert "report" in result
    assert result["report"]["total_amount"] == 1800.0


def test_selected_catalog_name_is_used_on_final_invoice():
    resolved = RequirementService().resolve_product({
        "product_name": "FITTING",
        "product_kind": "FITTING",
        "size_inch": "1/2",
        "quantity": "1",
        "unit": "piece",
        "selected_product_id": "ashirvad-70000560",
    })
    assert resolved["product_name"].startswith("Elbow 45")

    report = InvoiceReport({"customer_name": "Test"}).generate_many(
        [{**resolved, "line_total": resolved["unit_price"]}],
        resolved["unit_price"],
    )
    assert report["line_items"][0]["product_name"].startswith("Elbow 45")
