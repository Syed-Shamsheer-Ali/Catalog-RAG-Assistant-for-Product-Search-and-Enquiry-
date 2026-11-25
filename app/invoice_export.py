from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except Exception:  # pragma: no cover - fallback for limited environments
    colors = None
    TA_RIGHT = None
    A4 = None
    ParagraphStyle = None
    getSampleStyleSheet = None
    mm = 1
    Paragraph = None
    SimpleDocTemplate = None
    Spacer = None
    Table = None
    TableStyle = None
    REPORTLAB_AVAILABLE = False


def export_report(report: dict[str, Any], output_dir: str | Path | None = None) -> dict[str, Any]:
    target_dir = Path(output_dir) if output_dir is not None else Path(__file__).resolve().parents[1] / "data" / "processed"
    target_dir.mkdir(parents=True, exist_ok=True)

    file_stem = report.get("invoice_id", "invoice")
    pdf_path = target_dir / f"{file_stem}.pdf"
    json_path = target_dir / f"{file_stem}.json"
    csv_path = target_dir / f"{file_stem}.csv"

    _generate_pdf_invoice(report, pdf_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        if report.get("line_items"):
            columns = ["invoice_id", "customer_name", "line_number", "product_name", "product_kind", "product_category", "size_inch", "specifications", "part_number", "quantity", "unit", "unit_price", "price_source", "line_total", "grand_total"]
            # Reports may carry internal matching/validation metadata. Keep the
            # CSV schema stable and ignore fields that are not intended for export.
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for item in report["line_items"]:
                writer.writerow({**item, "invoice_id": report.get("invoice_id"), "customer_name": report.get("customer_name"), "grand_total": report.get("total_amount")})
        else:
            writer = csv.DictWriter(handle, fieldnames=list(report.keys()))
            writer.writeheader()
            writer.writerow(report)

    return {
        "pdf_path": str(pdf_path),
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "invoice_id": report.get("invoice_id"),
    }


def _generate_pdf_invoice(report: dict[str, Any], pdf_path: Path) -> None:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    if REPORTLAB_AVAILABLE:
        try:
            _generate_pdf_invoice_reportlab(report, pdf_path)
        except Exception as e:
            print(f"ReportLab PDF generation failed: {e}. Falling back to minimal PDF.")
            _generate_pdf_invoice_minimal(report, pdf_path)
        return

    _generate_pdf_invoice_minimal(report, pdf_path)


def _generate_pdf_invoice_reportlab(report: dict[str, Any], pdf_path: Path) -> None:
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=1,
        textColor=colors.HexColor("#1b1b1b"),
    )
    header_style = ParagraphStyle(
        "HeaderText",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#1f1f1f"),
    )
    table_header_style = ParagraphStyle(
        "TableHeaderStyle",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )
    cell_style = ParagraphStyle(
        "CellStyle",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1c1c1c"),
    )
    total_style = ParagraphStyle(
        "TotalStyle",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
        textColor=colors.HexColor("#1c1c1c"),
    )

    def safe(value: Any) -> str:
        from xml.sax.saxutils import escape
        return escape(str(value if value not in (None, "") else "N/A"))

    customer = safe(report.get("customer_name") or "Customer")
    invoice_no = safe(report.get("invoice_id") or "INV-0000")
    issued_date = str(report.get("issued_at") or "N/A").split(" ")[0]
    product_name = safe(report.get("product_kind") or "N/A")
    category = safe(report.get("product_category") or "N/A")
    size = safe(report.get("size_inch") or "N/A")
    material = safe(report.get("material") or "N/A")
    system = safe(report.get("system") or "N/A")
    quantity = int(report.get("quantity") or 0)
    unit_price = float(report.get("unit_price") or 0)
    total_amount = float(report.get("total_amount") or (quantity * unit_price))

    product_info = f"{product_name} {category} {size}"

    story = [
        Paragraph("PIPE SUPPLY", title_style),
        Paragraph("ESTIMATION / BILL", header_style),
        Spacer(1, 5 * mm),
        Table(
            [
                [Paragraph(f"<b>Customer</b><br/>{customer}", header_style), Paragraph(f"<b>Estimation No.</b><br/>{invoice_no}", header_style)],
                [Paragraph(f"<b>Cell</b><br/>+91 90000 00000", header_style), Paragraph(f"<b>Estimation Date</b><br/>{issued_date}", header_style)],
            ],
            colWidths=[doc.width * 0.55, doc.width * 0.45],
        ),
        Spacer(1, 6 * mm),
    ]

    rows = [[Paragraph("S.No.", table_header_style), Paragraph("Item Name", table_header_style), Paragraph("Qty / Unit", table_header_style), Paragraph("Rate", table_header_style), Paragraph("Amount", table_header_style), Paragraph("Part Number", table_header_style)]]
    if report.get("line_items"):
        for item in report["line_items"]:
            name = f"{safe(item.get('product_name'))} {safe(item.get('size_inch'))} {safe(item.get('specifications'))}"
            rows.append([Paragraph(str(item["line_number"]), cell_style), Paragraph(name, cell_style), Paragraph(f"{item['quantity']:g} {safe(item['unit'])}", cell_style), Paragraph(f"{item['unit_price']:,.2f}", cell_style), Paragraph(f"{item['line_total']:,.2f}", cell_style), Paragraph(safe(item.get("part_number")), cell_style)])
    else:
        rows.append([Paragraph("1", cell_style), Paragraph(product_info, cell_style), Paragraph(str(quantity), cell_style), Paragraph(f"{unit_price:,.2f}", cell_style), Paragraph(f"{total_amount:,.2f}", cell_style), Paragraph(safe(report.get("part_number")), cell_style)])
    item_table = Table(rows, colWidths=[25, 150, 40, 55, 60, 70], repeatRows=1)
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d4d8f")),
        ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#c2c2c2")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f8")]),
    ]))
    story.append(item_table)
    story.append(Spacer(1, 6 * mm))

    total_table = Table(
        [[Paragraph("TOTAL", total_style), Paragraph(f"{total_amount:,.2f}", total_style)]],
        colWidths=[doc.width * 0.7, doc.width * 0.3],
    )
    total_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#c2c2c2")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ebf0f4")),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(total_table)
    story.append(Spacer(1, 6 * mm))

    details = Table(
        [
            [Paragraph("Product", header_style), Paragraph(product_info, header_style), Paragraph("Material", header_style), Paragraph(f"{material} / {system}", header_style)],
            [Paragraph("Qty", header_style), Paragraph(str(quantity), header_style), Paragraph("Rate", header_style), Paragraph(f"{unit_price:,.2f}", header_style)],
        ],
        colWidths=[doc.width * 0.18, doc.width * 0.32, doc.width * 0.18, doc.width * 0.32],
    )
    details.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#d8d8d8")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f5f7f9")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f5f7f9")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    if not report.get("line_items"):
        story.append(details)
    if report.get("notes"):
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(f"<b>Notes:</b> {safe(report.get('notes'))}", header_style))

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Thank you for your business.", header_style))

    doc.build(story)


def _generate_pdf_invoice_minimal(report: dict[str, Any], pdf_path: Path) -> None:
    invoice_id = str(report.get("invoice_id") or "INV-0000")
    customer = str(report.get("customer_name") or "Customer")
    product = str(report.get("product_kind") or "Not specified")
    category = str(report.get("product_category") or "Not specified")
    size = str(report.get("size_inch") or "N/A")
    quantity = str(report.get("quantity") or 0)
    unit_price = float(report.get("unit_price") or 0)
    total_amount = float(report.get("total_amount") or (quantity * unit_price))
    issued = str(report.get("issued_at") or "N/A")

    lines = [
        "PIPE SUPPLY",
        "BILL / INVOICE",
        f"Invoice #: {invoice_id}",
        f"Date: {issued.split(' ')[0] if ' ' in issued else issued}",
        f"Customer: {customer}",
    ]
    if report.get("line_items"):
        lines.extend(f"{item['line_number']}. {item['product_name']} {item.get('size_inch', '')} {item.get('specifications', '')} | {item['quantity']} {item['unit']} x {item['unit_price']:.2f} = {item['line_total']:.2f} | Part {item.get('part_number', '')}" for item in report["line_items"])
        lines.append(f"Grand total: {total_amount:.2f}")
    else:
        lines.extend([f"Product: {product}", f"Category: {category}", f"Size: {size}", f"Quantity: {quantity}", f"Unit Price: {unit_price:.2f}", f"Total: {total_amount:.2f}"])

    content = []
    content.append("BT")
    content.append("/F1 12 Tf")
    content.append("50 790 Td")
    for idx, line in enumerate(lines):
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        y_pos = 760 - (idx * 18)
        content.append(f"50 {y_pos} Td")
        content.append(f"({escaped}) Tj")
    content.append("ET")
    content_bytes = "\n".join(content).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(content_bytes) + content_bytes + b"\nendstream",
    ]

    pdf = b"%PDF-1.4\n"
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{index} 0 obj\n".encode("latin-1") + obj + b"\nendobj\n"

    xref_pos = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    pdf += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n".encode("latin-1")
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("latin-1")
    pdf_path.write_bytes(pdf)
