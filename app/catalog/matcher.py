from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from app.schemas.requirement import RequirementRequest
from app.config import PRODUCT_DATA_PATH
from app.services.semantic_retrieval import semantic_scores

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = Path(PRODUCT_DATA_PATH)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def _normalize_size(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().replace("\xa0", " ")
    text = re.sub(r"(\d+)\s*([¼½¾])", lambda match: f"{match.group(1)} {match.group(2)}", text)
    replacements = {
        "¼": "1/4",
        "½": "1/2",
        "¾": "3/4",
        "⅛": "1/8",
        "″": "\"",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    for source, target in {"¼": "1/4", "½": "1/2", "¾": "3/4", "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8"}.items():
        text = text.replace(source, target)
    text = re.sub(r"\b(?:inch(?:es)?|in)\b|[\"″]", "", text, flags=re.I)
    text = re.sub(r"\s*[x×]\s*", " x ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def _size_similarity(record_size: Any, required_size: Any) -> float:
    if required_size is None:
        return 1.0
    if record_size is None:
        return 0.0
    target = _normalize_size(required_size)
    candidate = _normalize_size(record_size)
    if not target or not candidate:
        return 0.0
    if target == candidate:
        return 1.0
    # Compound fitting dimensions are ordered and must match in full.
    if " x " in target or " x " in candidate:
        return 0.0
    return 0.0


_NAME_STOP_WORDS = {
    "a", "an", "the", "and", "or", "of", "for", "is", "what", "which", "me",
    "tell", "show", "find", "give", "get", "about", "details", "detail", "information",
    "info", "following", "name", "number", "part", "sku", "code", "hsn", "cpvc",
    "product", "item", "new", "size", "inch", "inches", "degree", "degrees",
    "pipe", "pipes", "fitting", "fittings",
}


def _name_tokens(value: Any) -> set[str]:
    text = _normalize_text(value).replace("°", " ").replace("º", " ")
    tokens = re.findall(r"[a-z]+|\d+(?:\.\d+)?(?:/\d+)?", text)
    normalized = {token.rstrip("s") if token.endswith("s") and not token.endswith("ss") and len(token) > 4 else token for token in tokens}
    return normalized - _NAME_STOP_WORDS


def _name_similarity(requirement: RequirementRequest, record: dict[str, Any]) -> float:
    query = _name_tokens(requirement.product_name)
    query -= _name_tokens(requirement.size_inch)
    query -= _name_tokens(requirement.product_variant)
    query -= _name_tokens(requirement.class_name)
    query -= _name_tokens(requirement.sdr)
    query -= _name_tokens(requirement.schedule)
    if not query:
        return 0.0
    candidate = set().union(*(
        _name_tokens(record.get(field))
        for field in ("product_name", "product_variant", "section_title", "source_heading", "search_text")
    ))
    return len(query & candidate) / len(query)


def _requested_pipe_length(requirement: RequirementRequest) -> float | None:
    text = " ".join(str(value or "") for value in (requirement.product_variant, requirement.product_name, requirement.specifications))
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:m|mtr|meter|meters|metre|metres)\b", text, re.I)
    return float(match.group(1)) if match else None


def _safe_to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _record_is_valid(record: dict[str, Any]) -> bool:
    if not isinstance(record, dict):
        return False
    part_number = str(record.get("part_number") or "").strip()
    product_kind = str(record.get("product_kind") or "").strip()
    if not part_number or not product_kind:
        return False
    if part_number.lower() in {"none", "null", "nan"}:
        return False
    return True


def _score_record(record: dict[str, Any], requirement: RequirementRequest) -> float:
    score = 0.0

    exact_part = _normalize_text(requirement.part_number)
    exact_code = _normalize_text(requirement.product_code)
    if exact_part and exact_part == _normalize_text(record.get("part_number")):
        return 1.0
    if exact_code and exact_code in {_normalize_text(record.get("product_id")), _normalize_text(record.get("product_code"))}:
        return 1.0

    record_kind = _normalize_text(record.get("product_kind"))
    required_kind = _normalize_text(requirement.product_kind)
    if required_kind and record_kind == required_kind:
        score += 0.28
    elif required_kind and record_kind.startswith(required_kind[:3]):
        score += 0.15

    required_category = _normalize_text(requirement.product_category)
    record_category = _normalize_text(record.get("product_category"))
    record_name = _normalize_text(record.get("product_name"))
    if required_category:
        if required_category in record_category:
            score += 0.15
        elif required_category in record_name:
            score += 0.15
        elif any(token in record_category for token in required_category.split() if len(token) > 3):
            score += 0.08
        elif any(token in record_name for token in required_category.split() if len(token) > 3):
            score += 0.08

    required_size = requirement.size_inch
    size_score = max(
        _size_similarity(record.get("size_inch"), required_size),
        _size_similarity(record.get("size_cm"), required_size),
    )
    # A requested size is a hard product attribute: unrelated or missing sizes
    # must not be returned as plausible matches based on category alone.
    if required_size and size_score <= 0:
        return 0.0
    if required_size:
        score += 0.32 * size_score

    required_material = _normalize_text(requirement.material)
    record_material = _normalize_text(record.get("material"))
    if required_material:
        if required_material in record_material:
            score += 0.05
        elif any(token in record_material for token in required_material.split() if len(token) > 2):
            score += 0.025

    required_system = _normalize_text(requirement.system)
    record_system = _normalize_text(record.get("system"))
    if required_system:
        if required_system in record_system:
            score += 0.05

    required_class = _normalize_text(requirement.class_name)
    record_class = _normalize_text(record.get("class_name"))
    if required_class:
        required_value = re.search(r"\d+", required_class)
        record_value = re.search(r"\d+", record_class)
        if not required_value or not record_value or required_value.group(0) != record_value.group(0):
            return 0.0
        score += 0.1

    for requested, field in ((requirement.sdr, "sdr"), (requirement.schedule, "schedule")):
        if requested:
            required_value = re.search(r"\d+(?:\.\d+)?", _normalize_text(requested))
            actual_value = re.search(r"\d+(?:\.\d+)?", _normalize_text(record.get(field)))
            if not required_value or not actual_value or required_value.group(0) != actual_value.group(0):
                return 0.0
            score += 0.1

    required_pressure = _normalize_text(requirement.pressure_class)
    if required_pressure:
        if required_pressure in record_name:
            score += 0.05

    required_hsn = re.sub(r"\D", "", str(requirement.hsn_code or ""))
    if required_hsn:
        actual_hsn = re.sub(r"\D", "", str(record.get("hsn_code") or ""))
        if not actual_hsn or required_hsn != actual_hsn:
            return 0.0
        score += 0.2

    score += 0.28 * _name_similarity(requirement, record)

    requested_length = _requested_pipe_length(requirement)
    if requested_length is not None:
        candidate_length = _safe_to_float(record.get("length"))
        if candidate_length != requested_length:
            return 0.0
        score += 0.12

    if record.get("price") is not None:
        score += 0.02

    return score


def load_catalog_records(path: str | Path = CATALOG_PATH) -> list[dict[str, Any]]:
    catalog_path = Path(path)
    if not catalog_path.exists():
        raise FileNotFoundError(f"Catalog dataset not found: {catalog_path}")
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Catalog dataset at {catalog_path} must contain a list of records")
    return [record for record in payload if _record_is_valid(record)]


def match_products(requirement: RequirementRequest | dict[str, Any], dataset_path: str | Path = CATALOG_PATH) -> list[dict[str, Any]]:
    request = requirement if isinstance(requirement, RequirementRequest) else RequirementRequest.model_validate(requirement)
    records = load_catalog_records(dataset_path)
    if request.part_number:
        target = _normalize_text(request.part_number)
        records = [record for record in records if _normalize_text(record.get("part_number")) == target]
    elif request.product_code:
        target = _normalize_text(request.product_code)
        records = [record for record in records if target in {_normalize_text(record.get("product_id")), _normalize_text(record.get("product_code"))}]
    if request.part_number or request.product_code:
        exact_matches = [dict(record, match_score=1.0) for record in records]
        limit = max(1, int(request.max_results)) if request.max_results else len(exact_matches)
        return exact_matches[:limit]
    scored: list[dict[str, Any]] = []
    query = " ".join(str(value) for value in (request.product_kind, request.product_name, request.product_variant, request.product_category, request.size_inch, request.specifications, request.material, request.system, request.class_name, request.sdr, request.schedule, request.pressure_class, request.part_number, request.hsn_code) if value)
    semantic = semantic_scores(records, query, dataset_path)
    for record in records:
        score = _score_record(record, request)
        if score <= 0:
            continue
        candidate = dict(record)
        semantic_score = semantic.get(str(record.get("product_id")))
        if semantic_score is not None:
            # Semantic similarity can improve ranking, but must not reduce a
            # strong exact/structured match below the automatic-match threshold.
            score = max(score, (0.8 * score) + (0.2 * semantic_score))
            candidate["semantic_score"] = round(semantic_score, 3)
        candidate["match_score"] = round(score, 3)
        scored.append(candidate)

    scored.sort(key=lambda item: item["match_score"], reverse=True)
    limit = max(1, int(request.max_results)) if request.max_results else len(scored)
    return scored[:limit]


def build_requirement_summary(requirement: RequirementRequest | dict[str, Any]) -> str:
    request = requirement if isinstance(requirement, RequirementRequest) else RequirementRequest.model_validate(requirement)
    pieces = []
    if request.product_kind:
        pieces.append(f"kind={request.product_kind}")
    if request.product_name:
        pieces.append(f"name={request.product_name}")
    if request.product_category:
        pieces.append(f"category={request.product_category}")
    if request.size_inch:
        pieces.append(f"size={request.size_inch}")
    if request.material:
        pieces.append(f"material={request.material}")
    if request.product_variant:
        pieces.append(f"variant={request.product_variant}")
    if request.hsn_code:
        pieces.append(f"HSN={request.hsn_code}")
    if request.specifications:
        pieces.append(f"specifications={request.specifications}")
    return ", ".join(pieces) if pieces else "generic requirement"
