from __future__ import annotations

from fastapi import FastAPI

from app.controllers.requirement_controller import RequirementController
from app.schemas.requirement import RequirementRequest

app = FastAPI(title="Pipe Product Agent", version="0.2.0")


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "pipe-product-agent",
        "phase": "catalog-matching",
    }


@app.post("/requirements/match")
def match_requirement(requirement: RequirementRequest) -> dict[str, object]:
    return RequirementController().match_catalog(requirement)


@app.post("/requirements/match/natural")
def match_requirement_natural(payload: dict[str, str]) -> dict[str, object]:
    raw_text = payload.get("requirement") or payload.get("text") or payload.get("query") or ""
    return RequirementController().match_catalog(raw_text)
