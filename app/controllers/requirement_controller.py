from __future__ import annotations

from typing import Any

from app.services.requirement_service import RequirementService
from app.schemas.requirement import RequirementRequest
from app.graph import run_requirement_graph
from app.services.line_item_service import LineItemService


class RequirementController:
    def __init__(self, service: RequirementService | None = None):
        self.service = service or RequirementService()

    def extract(self, *, text: str = "", image_path: str | None = None, audio: Any = None, language: str | None = None) -> dict[str, Any]:
        return self.service.extract(text, image_path=image_path, audio=audio, language=language)

    def extract_many(self, *, text: str = "", image_paths: list[str] | None = None, audio: Any = None, language: str | None = None) -> list[dict[str, Any]]:
        return self.service.extract_many(text=text, image_paths=image_paths, audio=audio, language=language)

    def update(self, values: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
        merged = {**values, **updates}
        merged["manual_edits"] = sorted(set(merged.get("manual_edits", [])) | set(updates))
        confidence = dict(merged.get("confidence") or {})
        confidence.update({field: 1.0 for field in updates})
        merged["confidence"] = confidence
        return self.service.enrich(merged, source="manual")

    def match(self, values: dict[str, Any]) -> dict[str, Any]:
        return self.service.resolve_product(values)

    def prepare_line_items(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return LineItemService(self.service).prepare(items)

    def match_catalog(self, requirement: RequirementRequest | dict[str, Any] | str) -> dict[str, Any]:
        return run_requirement_graph(requirement)
