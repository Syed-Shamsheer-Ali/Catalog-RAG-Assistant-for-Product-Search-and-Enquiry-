from __future__ import annotations

from app.catalog.form_parser import parse_invoice_ocr_rows, parse_requirement_text
from app.services.requirement_service import RequirementService


def _word(x: float, y: float, text: str, confidence: float = 0.96):
    return ([[x, y], [x + max(8, len(text) * 4), y], [x + max(8, len(text) * 4), y + 8], [x, y + 8]], text, confidence)


def _bill_ocr(product_names: list[str]):
    words = [
        _word(20, 20, "S.No"), _word(170, 20, "Item Name"), _word(400, 20, "Qty"),
        _word(500, 20, "Rate"), _word(600, 20, "Amount"), _word(700, 20, "Disc%"), _word(770, 20, "NetValue"),
    ]
    for index, product_name in enumerate(product_names, start=1):
        y = 50 + (index - 1) * 20
        words.extend([
            _word(20, y, str(index)), _word(90, y, product_name), _word(400, y, f"{index * 2}.00"),
            _word(500, y, "125.00"), _word(600, y, "250.00"), _word(700, y, "10.00"), _word(770, y, "225.00"),
        ])
    return words


def test_positioned_bill_extraction_returns_all_rows_and_source_rates():
    names = [f"CPVC elbow {index}/2 inch" for index in range(1, 11)]
    products = parse_invoice_ocr_rows(_bill_ocr(names))

    assert len(products) == 10
    assert products[0]["product_name"] == names[0]
    assert products[0]["quantity"] == "2.00"
    assert products[0]["source_unit_price"] == "125.00"
    assert products[-1]["product_kind"] == "FITTING"


def test_compound_size_is_preserved_in_free_text():
    parsed = parse_requirement_text("Need 2 CPVC elbow size 3/4 x 1/2 inch")
    assert parsed["size_inch"] == "3/4 × 1/2 inch"
    assert parsed["product_name"]


def test_missing_catalog_match_does_not_drop_extracted_product(monkeypatch):
    raw_row = {
        "product_name": "Special imported coupling 3/4 x 1/2",
        "product_kind": "FITTING", "size_inch": "3/4 × 1/2", "quantity": "4",
        "source_unit_price": "99.00", "source_text": "4 Special imported coupling 3/4 x 1/2 99.00",
        "confidence": {"product_name": 0.93}, "input_source": "image",
    }
    monkeypatch.setattr(
        "app.services.requirement_service.extract_product_rows_from_image",
        lambda _path: ([raw_row], raw_row["source_text"]),
    )
    rows = RequirementService().extract_many(image_paths=["bill.png"])

    assert len(rows) == 1
    assert rows[0]["product_name"] == raw_row["product_name"]
    assert rows[0]["size_inch"] == "3/4 × 1/2"
    assert rows[0]["source_text"] == raw_row["source_text"]
    assert rows[0]["source_unit_price"] == "99.00"


def test_unreadable_image_returns_editable_review_row(monkeypatch):
    monkeypatch.setattr("app.services.requirement_service.extract_product_rows_from_image", lambda _path: ([], ""))
    rows = RequirementService().extract_many(image_paths=["unreadable.png"])

    assert len(rows) == 1
    assert rows[0]["product_name"] == ""
    assert "OCR could not read" in rows[0]["extraction_status"]


def test_image_form_population_keeps_ten_detected_rows(monkeypatch):
    ocr_rows = parse_invoice_ocr_rows(_bill_ocr([f"Bill item {index} elbow" for index in range(10)]))
    monkeypatch.setattr("app.services.requirement_service.extract_product_rows_from_image", lambda _path: (ocr_rows, "source bill text"))

    form_rows = RequirementService().extract_many(image_paths=["bill.jpeg"])

    assert len(form_rows) == 10
    assert all(row.get("product_name") and row.get("quantity") for row in form_rows)


def test_text_pdf_table_is_extracted_into_product_rows(tmp_path):
    from reportlab.pdfgen import canvas

    from app.catalog.form_parser import extract_product_rows_from_pdf

    path = tmp_path / "bill.pdf"
    page = canvas.Canvas(str(path))
    for x, value in ((20, "S.No"), (140, "Item Name"), (390, "Qty"), (490, "Rate"), (570, "Amount")):
        page.drawString(x, 790, value)
    page.drawString(20, 755, "1")
    page.drawString(85, 755, "Reducing elbow 3/4 x 1/2 inch")
    page.drawString(390, 755, "4")
    page.drawString(490, 755, "125.00")
    page.drawString(570, 755, "500.00")
    page.save()

    rows = extract_product_rows_from_pdf(path)

    assert len(rows) == 1
    assert rows[0]["product_name"] == "Reducing elbow 3/4 x 1/2 inch"
    assert rows[0]["quantity"] == "4"
    assert rows[0]["source_unit_price"] == "125.00"
