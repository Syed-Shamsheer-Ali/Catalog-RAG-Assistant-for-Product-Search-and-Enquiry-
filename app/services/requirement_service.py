from __future__ import annotations

import csv
import io
import re
from typing import Any

from app import config as app_config
from app.catalog.form_parser import (
    extract_fields_from_image, extract_product_rows_from_image, extract_product_rows_from_pdf,
    extract_text_from_pdf, parse_requirement_text,
)
from app.rag_price import local_rag_price_lookup
from app.requirements_plan import calculate_boxes_for_quantity
from app.services.local_llm import extract_with_local_llm
from app.voice import transcribe_audio_bytes


MATCH_AUTO_THRESHOLD = getattr(app_config, "MATCH_AUTO_THRESHOLD", 0.82)
MATCH_MARGIN_THRESHOLD = getattr(app_config, "MATCH_MARGIN_THRESHOLD", 0.08)


def _split_product_text(text: str) -> list[str]:
    chunks: list[str] = []
    for line in text.replace("\r", "\n").split("\n"):
        for clause in re.split(r"\s*;\s*", line):
            clauses = re.split(r"\s+\b(?:and|then)\b\s+(?=(?:(?:also\s+)?need\s+\d+\b|\d+\s+(?:(?:cpvc\s+)?(?:pipe|pipes|elbow|elbows|tee|tees|valve|valves|fitting|fittings|coupler))))", clause, flags=re.IGNORECASE)
            chunks.extend(part.strip(" \t,.-") for part in clauses if part.strip(" \t,.-"))
    return chunks


class RequirementService:
    """Coordinate reusable requirement parsing, enrichment, and validation."""

    def extract(self, text: str = "", *, image_path: str | None = None, audio: Any = None, language: str | None = None) -> dict[str, Any]:
        if image_path:
            values = extract_fields_from_image(image_path)
            values["confidence"] = {key: 0.5 for key in values if key not in {"confidence", "notes"}}
            return self.enrich(values, source="image")
        if audio is not None:
            transcript = transcribe_audio_bytes(audio, language=language)
            values = self._parse_text(transcript)
            values["source_text"] = transcript
            return self.enrich(values, source="voice")
        values = self._parse_text(text)
        values["source_text"] = text
        return self.enrich(values, source="text")

    def extract_many(self, *, text: str = "", image_paths: list[str] | None = None, audio: Any = None, language: str | None = None) -> list[dict[str, Any]]:
        """Extract every identifiable product from any combination of local inputs."""
        sources: list[tuple[str, str]] = []
        extracted_rows: list[dict[str, Any]] = []
        if text.strip():
            sources.append((text, "text"))
        for image_path in image_paths or []:
            suffix = str(image_path).lower().rsplit(".", 1)[-1]
            if suffix == "pdf":
                rows = extract_product_rows_from_pdf(image_path)
                image_text = extract_text_from_pdf(image_path)
                source = "pdf"
            else:
                rows, image_text = extract_product_rows_from_image(image_path)
                source = "image"
            extracted_rows.extend(rows)
            if image_text and not rows:
                sources.append((image_text, source))
            elif not rows:
                extracted_rows.append({
                    "product_name": "", "product_kind": "", "quantity": "", "unit": "",
                    "source_text": "", "input_source": source, "extraction_status": "OCR could not read this document",
                    "confidence": {},
                })
        if audio is not None:
            transcript = transcribe_audio_bytes(audio, language=language)
            if transcript:
                sources.append((transcript, "voice"))
        output: list[dict[str, Any]] = [self.enrich(row, source=row.get("input_source", "image")) for row in extracted_rows]
        for source_text, source in sources:
            for chunk in _split_product_text(source_text):
                values = self._parse_text(chunk)
                if not any(values.get(key) for key in ("product_name", "product_kind", "product_category", "size_inch", "quantity", "part_number")):
                    continue
                values["source_text"] = chunk
                values.setdefault("product_name", "")
                output.append(self.enrich(values, source=source))
        return output

    @staticmethod
    def _parse_text(text: str) -> dict[str, Any]:
        deterministic = parse_requirement_text(text)
        assisted = extract_with_local_llm(text)
        # Deterministic extraction preserves literal OCR/input values; local model
        # suggestions fill only fields the parser could not read.
        values = {**assisted, **deterministic}
        values["confidence"] = {key: 0.55 if key in assisted else 0.7 for key in values if key not in {"confidence", "notes"}}
        return values

    def extract_spreadsheet(self, content: bytes, filename: str) -> list[dict[str, Any]]:
        """Read CSV/XLSX rows locally and turn each row into editable form data."""
        suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        if suffix == "csv":
            rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
        elif suffix in {"xlsx", "xlsm"}:
            from openpyxl import load_workbook
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            sheet = workbook.active
            values = sheet.iter_rows(values_only=True)
            headers = [str(item or "").strip() for item in next(values, ())]
            rows = [dict(zip(headers, row)) for row in values]
            workbook.close()
        else:
            raise ValueError("Upload a .csv, .xlsx, or .xlsm file.")

        aliases = {
            "customer_name": {"customer", "customer name", "client", "client name"},
            "product_name": {"product", "product name", "item", "item name", "description"},
            "product_kind": {"product kind", "kind", "type"},
            "product_category": {"category", "product category"},
            "size_inch": {"size", "size inch", "diameter"},
            "material": {"material"}, "system": {"system", "class", "schedule"},
            "quantity": {"quantity", "qty", "required quantity", "total quantity"},
            "quantity_per_box": {"quantity per box", "qty per box", "pack size"},
            "number_of_boxes": {"number of boxes", "boxes", "box count"},
            "unit": {"unit", "uom", "unit of measure"},
            "part_number": {"part number", "part no", "sku", "product code"},
            "source_unit_price": {"rate", "price", "unit price", "quoted rate"},
            "specifications": {"specifications", "specification", "specs"},
            "notes": {"notes", "requirement"},
        }
        output: list[dict[str, Any]] = []
        for row in rows:
            normalized = {str(k or "").strip().lower(): v for k, v in row.items()}
            direct: dict[str, Any] = {}
            for field, names in aliases.items():
                value = next((normalized[name] for name in names if normalized.get(name) not in (None, "")), None)
                if value is not None:
                    direct[field] = str(value).strip()
            combined_text = " ".join(str(v).strip() for v in row.values() if v not in (None, ""))
            parsed = parse_requirement_text(combined_text)
            values = {**parsed, **direct}
            product_label = direct.get("product_kind") or direct.get("product_name", "")
            if product_label:
                label = product_label.upper()
                if "PIPE" in label:
                    values["product_kind"] = "PIPE"
                elif "CEMENT" in label:
                    values["product_kind"] = "CEMENT"
                elif any(token in label for token in ("ELBOW", "TEE", "FITTING", "COUPLER", "ADAPTER")):
                    values["product_kind"] = "FITTING"
                elif "VALVE" in label:
                    values["product_kind"] = "VALVE"
                elif any(token in label for token in ("CLAMP", "WASHER", "GASKET", "STRAP")):
                    values["product_kind"] = "ACCESSORY"
            if direct.get("product_name"):
                values["product_name"] = direct["product_name"]
            if not values:
                continue
            values["source_text"] = combined_text
            values["confidence"] = {key: 0.95 for key in direct}
            values["input_source"] = "excel"
            enriched = self.enrich(values, source="excel")
            output.append(self.resolve_product(enriched))
        return output

    def enrich(self, values: dict[str, Any], *, source: str = "manual") -> dict[str, Any]:
        result = dict(values)
        result.setdefault("input_source", source)
        result.setdefault("confidence", {})
        errors = validate_requirement_fields(result, require_product=False)
        result["validation_errors"] = errors
        result["review_status"] = "needs_review" if errors else "ready_for_review"
        return result

    def resolve_product(self, values: dict[str, Any]) -> dict[str, Any]:
        result = dict(values)
        if not result.get("product_variant"):
            source_text = " ".join(str(value or "") for value in (result.get("source_text"), result.get("notes")))
            length_match = re.search(r"\b([35])\s*(?:m|mtr|meters?|metres?)\s*(?:length|long|stick)\b", source_text, re.I)
            if length_match:
                result["product_variant"] = f"{length_match.group(1)} m length"
        if not any(result.get(key) for key in ("product_kind", "product_name", "product_category", "size_inch", "part_number")):
            result["matches"] = []
            result["review_status"] = "needs_review"
            return result
        lookup = local_rag_price_lookup(
            product_name=result.get("product_name") or result.get("product_kind"),
            size_inch=result.get("size_inch"), quantity=result.get("quantity"),
            category=result.get("product_category"), part_number=result.get("part_number"),
            product_kind=result.get("product_kind"),
            product_variant=result.get("product_variant"),
            specifications=result.get("specifications"),
            class_name=result.get("class_name"), sdr=result.get("sdr"), schedule=result.get("schedule"),
        )
        matches = lookup.get("matches", [])
        result["matches"] = matches
        best = lookup.get("best_match") or {}
        selected_id = str(result.get("selected_product_id") or "")
        if selected_id:
            best = next((item for item in matches if str(item.get("product_id")) == selected_id), {})
            # A submitted catalog ID represents an explicit user choice.
            if best.get("product_name"):
                result["product_name"] = best["product_name"]
        best_score = float(best.get("match_score") or 0) if best else 0.0
        runner_up_score = float(matches[1].get("match_score") or 0) if len(matches) > 1 else 0.0
        score_margin = best_score - runner_up_score
        exact_part = bool(result.get("part_number")) and str(best.get("part_number") or "").casefold() == str(result.get("part_number") or "").casefold()
        confidence_threshold = MATCH_AUTO_THRESHOLD
        margin_threshold = MATCH_MARGIN_THRESHOLD
        ambiguous = bool(not selected_id and len(matches) > 1 and score_margin < margin_threshold)
        exact = bool(best) and (selected_id != "" or exact_part or (best_score >= confidence_threshold and score_margin >= margin_threshold)) and not ambiguous
        resolved_price = best.get("price")
        result["match_ambiguous"] = ambiguous
        result["match_confidence"] = float(best.get("match_score") or 0) if best else 0.0
        result["catalog_match_status"] = "Matched" if exact and resolved_price else "Needs Review" if matches else "Not Found"
        result["review_status"] = "ready_for_review" if exact and resolved_price else "needs_review"
        confirmation_fields = list(result.get("confirmation_required_fields") or [])
        if exact:
            for target, source in (("product_name", "product_name"), ("product_kind", "product_kind"), ("product_category", "product_category"), ("size_inch", "size_inch"), ("material", "material"), ("system", "system")):
                if not result.get(target) and best.get(source):
                    result[target] = best[source]
                    confirmation_fields.append(target)
        if exact and (best.get("product_id") or best.get("part_number")):
            result["product_code"] = best.get("product_id") or best.get("part_number")
        if exact and best.get("part_number"):
            result["part_number"] = best["part_number"]
        if exact and not result.get("specifications"):
            specifications = [best.get(key) for key in ("class_name", "schedule", "sdr") if best.get(key)]
            if specifications:
                result["specifications"] = ", ".join(str(value) for value in specifications)
                confirmation_fields.append("specifications")
        result["confirmation_required_fields"] = sorted(set(confirmation_fields))
        if resolved_price and exact:
            result["unit_price"] = resolved_price
            result["price_source"] = "local_catalog"
        else:
            result["unit_price"] = result.get("unit_price", "")
            result["price_source"] = "manual" if result["unit_price"] else "missing"
        if exact:
            for source_key, target_key in (("standard_package_qty", "std_pkg"), ("box_quantity", "box_quantity")):
                if best.get(source_key) is not None:
                    result[target_key] = best[source_key]
            result["quantity_per_box"] = best.get("box_quantity") or best.get("standard_package_qty")
        else:
            result["quantity_per_box"] = result.get("quantity_per_box")
        package = calculate_boxes_for_quantity(result.get("quantity"), result.get("std_pkg"), result.get("box_quantity"))
        result["boxes_required"] = package["boxes_required"]
        result["price_match_details"] = best
        result["validation_errors"] = validate_requirement_fields(result, require_product=True)
        if result["validation_errors"] or not exact or not resolved_price:
            result["review_status"] = "needs_review"
        return result


def validate_requirement_fields(values: dict[str, Any], *, require_product: bool = True) -> list[str]:
    errors: list[str] = []
    if require_product and not any(values.get(key) for key in ("product_kind", "product_category", "product_code", "part_number")):
        errors.append("Select or enter a product before confirming the requirement.")
    quantity = values.get("quantity")
    if quantity not in (None, ""):
        try:
            if float(str(quantity).replace(",", "")) <= 0:
                errors.append("Quantity must be greater than zero.")
        except (TypeError, ValueError):
            errors.append("Quantity must be a valid number.")
    price = values.get("unit_price")
    if price not in (None, ""):
        try:
            if float(str(price).replace(",", "").replace("₹", "").strip()) < 0:
                errors.append("Unit price cannot be negative.")
        except (TypeError, ValueError):
            errors.append("Unit price must be a valid number.")
    return errors
