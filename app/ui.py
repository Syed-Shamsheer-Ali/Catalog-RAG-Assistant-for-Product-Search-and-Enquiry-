from __future__ import annotations

from typing import Any

from app.controllers.requirement_controller import RequirementController
from app.controllers.submission_controller import SubmissionController


class RequirementFormUI:
    def __init__(self, raw_text: str = ""):
        self.raw_text = raw_text
        self.controller = RequirementController()
        self.form_data = self.controller.extract(text=raw_text)

    def edit(self, updates: dict[str, Any]) -> dict[str, Any]:
        self.form_data = self.controller.update(self.form_data, updates)
        return self.form_data

    def match(self) -> dict[str, Any]:
        self.form_data = self.controller.match(self.form_data)
        return self.form_data

    def submit(self) -> dict[str, Any]:
        return SubmissionController().submit(self.form_data, confirmed=True)

    def render(self) -> dict[str, Any]:
        return {
            "fields": self.form_data,
            "editable": True,
            "submit_button": True,
            "auto_filled": bool(self.form_data),
        }
