from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from app.controllers.requirement_controller import RequirementController
from app.controllers.submission_controller import SubmissionController
from app.schemas.line_item import MultipleRequirementSubmission
from app.submission import handle_submission

app = FastAPI(title="Pipe Product Requirement Auto-Fill", version="0.3.0")


class RequirementSubmission(BaseModel):
    customer_name: str = ""
    product_kind: str = ""
    product_category: str = ""
    size_inch: str = ""
    material: str = ""
    system: str = ""
    quantity: str = ""
    unit_price: str = ""
    notes: str = ""


class MultipleTextInput(BaseModel):
    text: str = ""


@app.post("/api/auto-fill")
def auto_fill_from_text(payload: dict[str, str]):
    text = payload.get("text") or payload.get("requirement") or ""
    return RequirementController().extract(text=text)


@app.post("/api/auto-fill/multiple")
def auto_fill_multiple_from_text(payload: MultipleTextInput):
    controller = RequirementController()
    extracted = controller.extract_many(text=payload.text)
    return controller.prepare_line_items(extracted)


@app.post("/api/auto-fill-image")
def auto_fill_from_image(payload: dict[str, str]):
    image_path = payload.get("image_path") or ""
    if not image_path:
        return {"error": "image_path is required"}
    from pathlib import Path
    allowed_root = (Path(__file__).resolve().parents[1] / "data" / "temp").resolve()
    candidate = Path(image_path).resolve()
    if allowed_root not in candidate.parents:
        return {"error": "image_path must point inside the data/temp directory"}
    return RequirementController().extract(image_path=str(candidate))


@app.post("/api/submit")
def submit_requirement(payload: RequirementSubmission):
    result = handle_submission(payload.model_dump())
    return result


@app.post("/api/submit/multiple")
def submit_multiple_requirements(payload: MultipleRequirementSubmission):
    return SubmissionController().submit(payload.model_dump(exclude={"confirmed"}), confirmed=payload.confirmed)
