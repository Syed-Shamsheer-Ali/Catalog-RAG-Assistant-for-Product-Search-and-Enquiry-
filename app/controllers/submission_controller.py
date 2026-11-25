from __future__ import annotations

from typing import Any

from app.services.submission_service import SubmissionService


class SubmissionController:
    def __init__(self, service: SubmissionService | None = None):
        self.service = service or SubmissionService()

    def submit(self, form_data: dict[str, Any], *, confirmed: bool = True) -> dict[str, Any]:
        return self.service.submit(form_data, confirmed=confirmed)
