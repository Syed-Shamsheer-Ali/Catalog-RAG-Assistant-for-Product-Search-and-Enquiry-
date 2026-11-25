from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.entities import AuditRecord, Submission


class SubmissionRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(self, form: dict[str, Any], report: dict[str, Any]) -> Submission:
        row = Submission(
            submission_id=str(uuid4()), invoice_id=str(report["invoice_id"]),
            customer_name=str(report.get("customer_name") or ""),
            status=str(report.get("status") or "submitted"),
            total_amount=float(report.get("total_amount") or 0), form_json=form, report_json=report,
        )
        self.session.add(row)
        self.session.flush()
        return row


class AuditRepository:
    def __init__(self, session: Session):
        self.session = session

    def record(self, event_type: str, entity_id: str | None = None, *, status: str = "ok", details: dict[str, Any] | None = None, error: str | None = None) -> AuditRecord:
        row = AuditRecord(event_type=event_type, entity_id=entity_id, status=status, details_json=details or {}, error_message=error)
        self.session.add(row)
        self.session.flush()
        return row
