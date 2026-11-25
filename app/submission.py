from __future__ import annotations

from typing import Any

from app.controllers.submission_controller import SubmissionController


def handle_submission(form_data: dict[str, Any]) -> dict[str, Any]:
    # Compatibility facade for the existing API and UI callers.
    return SubmissionController().submit(form_data, confirmed=True)
