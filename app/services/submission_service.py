from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.database.session import create_session_factory, initialize_database
from app.invoice import InvoiceReport
from app.invoice_export import export_report
from app.repositories.submission_repository import AuditRepository, SubmissionRepository
from app.services.line_item_service import LineItemService
from app.services.requirement_service import RequirementService, validate_requirement_fields


class SubmissionService:
    def __init__(self, session: Session | None = None, *, persist: bool = True):
        self._session = session
        self._persist = persist

    def submit(self, form_data: dict[str, Any], *, confirmed: bool = True) -> dict[str, Any]:
        cleaned = {str(key): value for key, value in (form_data or {}).items()}
        if isinstance(cleaned.get("line_items"), list):
            return self._submit_lines(cleaned, confirmed=confirmed)
        enriched = RequirementService().resolve_product(cleaned)
        issues = validate_requirement_fields(enriched, require_product=True)
        if enriched.get("review_status") != "ready_for_review":
            issues.append("Resolve the product match and price review before finalization.")
        if enriched.get("price_source") != "local_catalog" or not enriched.get("unit_price"):
            issues.append("A verified price from the local product price list is required before finalization.")
        if issues:
            self._record_rejection(issues, cleaned)
            return {"success": False, "message": "Review the requirement before submitting.", "validation_errors": issues, "form": enriched}
        if not confirmed:
            return {"success": False, "message": "User confirmation is required before finalization.", "form": enriched}

        report = InvoiceReport(enriched).generate()
        export = export_report(report)
        if self._persist:
            self._persist_submission(enriched, report)
        return {"success": True, "message": "Requirement submitted successfully", "report": report, "export": export, "price_source": enriched.get("price_source", "manual"), "review_status": enriched.get("review_status", "ready_for_review")}

    def _submit_lines(self, form: dict[str, Any], *, confirmed: bool) -> dict[str, Any]:
        prepared = LineItemService().prepare(form["line_items"])
        errors = list(prepared["validation_errors"])
        if not prepared["line_items"]:
            errors.append("Add at least one product line before finalization.")
        if errors:
            self._record_rejection(errors, {"customer_name": form.get("customer_name", ""), "line_count": len(prepared["line_items"])})
            return {"success": False, "message": "Review the product lines before submitting.", "validation_errors": errors, **prepared}
        if not confirmed:
            return {"success": False, "message": "User confirmation is required before finalization.", **prepared}

        report = InvoiceReport({"customer_name": form.get("customer_name", ""), "notes": form.get("notes", "")}).generate_many(prepared["line_items"], prepared["grand_total"])
        export = export_report(report)
        if self._persist:
            self._persist_submission({"customer_name": form.get("customer_name", ""), "line_items": prepared["line_items"]}, report)
        return {"success": True, "message": "Requirements submitted successfully", "report": report, "export": export, "line_items": prepared["line_items"], "grand_total": prepared["grand_total"], "review_status": "confirmed"}

    def _persist_submission(self, form: dict[str, Any], report: dict[str, Any]) -> None:
        session = self._session
        close = False
        if session is None:
            engine = initialize_database()
            session = create_session_factory(engine)()
            close = True
        try:
            SubmissionRepository(session).save(form, report)
            AuditRepository(session).record("submission.finalized", report.get("invoice_id"), details={"price_source": form.get("price_source", "manual"), "review_status": form.get("review_status", "")})
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            if close:
                session.close()

    def _record_rejection(self, issues: list[str], form: dict[str, Any]) -> None:
        if not self._persist:
            return
        session = self._session
        close = False
        if session is None:
            engine = initialize_database()
            session = create_session_factory(engine)()
            close = True
        try:
            AuditRepository(session).record("submission.needs_review", status="review_required", details={"errors": issues, "provided_fields": sorted(form.keys())})
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            if close:
                session.close()
