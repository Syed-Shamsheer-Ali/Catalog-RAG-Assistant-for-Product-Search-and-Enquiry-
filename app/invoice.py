from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any


class InvoiceReport:
    def __init__(self, form_data: dict[str, Any]):
        self.form_data = form_data or {}

    def generate(self) -> dict[str, Any]:
        quantity_value = str(self.form_data.get("quantity") or "0")
        price_value = str(self.form_data.get("unit_price") or "0")

        try:
            quantity = int(float(quantity_value))
        except ValueError:
            quantity = 0

        try:
            unit_price = float(price_value.replace("₹", "").replace(",", "").replace(" ", ""))
        except ValueError:
            unit_price = 0.0

        total = quantity * unit_price
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        std_pkg = self.form_data.get("std_pkg")
        box_quantity = self.form_data.get("box_quantity")
        boxes_required = self.form_data.get("boxes_required") or 0

        if box_quantity in (None, "", "N/A"):
            box_quantity = std_pkg

        if boxes_required == 0 and quantity and (box_quantity or std_pkg):
            effective_box = int(float(str(box_quantity or std_pkg).replace(",", ""))) if (box_quantity or std_pkg) else 0
            if effective_box:
                boxes_required = (quantity + effective_box - 1) // effective_box

        return {
            "invoice_id": f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "issued_at": now,
            "customer_name": self.form_data.get("customer_name") or "Customer",
            "product_kind": self.form_data.get("product_kind") or "Not specified",
            "product_category": self.form_data.get("product_category") or "Not specified",
            "product_code": self.form_data.get("product_code") or "",
            "part_number": self.form_data.get("part_number") or "",
            "size_inch": self.form_data.get("size_inch") or "N/A",
            "material": self.form_data.get("material") or "N/A",
            "system": self.form_data.get("system") or "N/A",
            "quantity": quantity,
            "std_pkg": std_pkg,
            "box_quantity": box_quantity,
            "boxes_required": boxes_required,
            "unit_price": unit_price,
            "total_amount": round(total, 2),
            "notes": self.form_data.get("notes") or "",
            "status": "submitted",
        }

    def generate_many(self, line_items: list[dict[str, Any]], grand_total: float) -> dict[str, Any]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = []
        for index, item in enumerate(line_items, start=1):
            lines.append({
                "line_number": index,
                "product_name": item.get("product_name") or item.get("product_kind") or "",
                "product_kind": item.get("product_kind") or "",
                "product_category": item.get("product_category") or "",
                "size_inch": item.get("size_inch") or "",
                "specifications": item.get("specifications") or "",
                "part_number": item.get("part_number") or "",
                "quantity": float(item["quantity"]),
                "unit": item["unit"],
                "unit_price": float(item["unit_price"]),
                "line_total": float(item["line_total"]),
                "price_source": "local_catalog",
            })
        return {
            "invoice_id": f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "issued_at": now,
            "customer_name": self.form_data.get("customer_name") or "Customer",
            "product_kind": "Multiple products",
            "product_category": "Multiple line items",
            "line_items": lines,
            "total_amount": round(float(grand_total), 2),
            "notes": self.form_data.get("notes") or "",
            "status": "submitted",
        }

    def generate_many(self, line_items: list[dict[str, Any]], grand_total: float) -> dict[str, Any]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = []
        for index, item in enumerate(line_items, start=1):
            lines.append({
                "line_number": index,
                "product_name": item.get("product_name") or item.get("product_kind") or "",
                "product_kind": item.get("product_kind") or "",
                "product_category": item.get("product_category") or "",
                "size_inch": item.get("size_inch") or "",
                "specifications": item.get("specifications") or "",
                "part_number": item.get("part_number") or "",
                "quantity": float(item["quantity"]),
                "unit": item["unit"],
                "unit_price": float(item["unit_price"]),
                "line_total": float(item["line_total"]),
                "price_source": "local_catalog",
            })
        return {
            "invoice_id": f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "issued_at": now,
            "customer_name": self.form_data.get("customer_name") or "Customer",
            "product_kind": "Multiple products",
            "product_category": "Multiple line items",
            "line_items": lines,
            "total_amount": round(float(grand_total), 2),
            "notes": self.form_data.get("notes") or "",
            "status": "submitted",
        }


def render_invoice_html(report: dict[str, Any]) -> str:
    safe = lambda value: escape(str(value or ""))
    if report.get("line_items"):
        lines = ["PIPE SUPPLY", "BILL / INVOICE", f"Invoice #: {safe(report.get('invoice_id'))}", f"Customer: {safe(report.get('customer_name'))}", ""]
        for item in report["line_items"]:
            lines.append(f"{item['line_number']}. {safe(item.get('product_name'))} {safe(item.get('size_inch'))} {safe(item.get('specifications'))} · {safe(item.get('quantity'))} {safe(item.get('unit'))} × {safe(item.get('unit_price'))} = {safe(item.get('line_total'))} · part {safe(item.get('part_number'))}")
        lines.extend(["", f"GRAND TOTAL: {float(report.get('total_amount') or 0):.2f}"])
        return "\n".join(lines)
    if report.get("line_items"):
        lines = ["PIPE SUPPLY", "BILL / INVOICE", f"Invoice #: {safe(report.get('invoice_id'))}", f"Customer: {safe(report.get('customer_name'))}", ""]
        for item in report["line_items"]:
            lines.append(f"{item['line_number']}. {safe(item.get('product_name'))} {safe(item.get('size_inch'))} {safe(item.get('specifications'))} · {safe(item.get('quantity'))} {safe(item.get('unit'))} × {safe(item.get('unit_price'))} = {safe(item.get('line_total'))} · part {safe(item.get('part_number'))}")
        lines.extend(["", f"GRAND TOTAL: {float(report.get('total_amount') or 0):.2f}"])
        return "\n".join(lines)
    customer = safe(report.get("customer_name") or "Customer")
    product = safe(report.get("product_kind") or "Not specified")
    category = safe(report.get("product_category") or "Not specified")
    product_code = safe(report.get("product_code") or "")
    part_number = safe(report.get("part_number") or "")
    size = safe(report.get("size_inch") or "")
    material = safe(report.get("material") or "N/A")
    system = safe(report.get("system") or "N/A")
    qty = report.get("quantity") or 0
    std_pkg = report.get("std_pkg") or "N/A"
    box_quantity = report.get("box_quantity") or "N/A"
    boxes_required = report.get("boxes_required") or 0
    unit_price = float(report.get("unit_price") or 0)
    total_amount = float(report.get("total_amount") or 0)
    invoice_id = report.get("invoice_id") or "INV-0000"
    issued_at = report.get("issued_at") or ""
    invoice_date = issued_at.split(" ")[0] if issued_at else "N/A"

    lines = [
        "PIPE SUPPLY",
        "BILL / INVOICE",
        f"Invoice #: {invoice_id}",
        f"Date: {invoice_date}",
        f"Customer ID: {customer}",
        "",
        "Bill To",
        customer,
        product,
        category,
        size,
        "",
        "Product Details",
        f"Product: {product}",
        f"Category: {category}",
        f"Size: {size}",
        f"Material: {material}",
        f"System: {system}",
        f"Std. Package: {std_pkg}",
        f"Box Quantity: {box_quantity}",
        f"Boxes Required: {boxes_required}",
        f"Part Number: {part_number or 'N/A'}",
        f"Product Code: {product_code or 'N/A'}",
        f"Qty: {qty}",
        f"Unit Price: {unit_price:.2f}",
        "",
        "Description                        Qty   Std Pack   Box Qty   Boxes   Unit Price   Amount",
        f"{product} {category} {size}      {qty}      {std_pkg}      {box_quantity}      {boxes_required}      {unit_price:.2f}      {total_amount:.2f}",
        "",
        f"TOTAL: {total_amount:.2f}",
        "Thank you for your business!",
    ]
    return "\n".join(lines)
