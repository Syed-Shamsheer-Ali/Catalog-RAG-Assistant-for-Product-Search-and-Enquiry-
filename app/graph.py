from __future__ import annotations

import re
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.catalog.matcher import build_requirement_summary, load_catalog_records, match_products
from app.schemas.requirement import RequirementRequest
from app.services.local_llm import answer_with_catalog_context
from app.services.requirement_service import RequirementService


class RequirementState(TypedDict):
    raw_requirement: str
    requirement: dict[str, Any]
    summary: str
    catalog: list[dict[str, Any]]
    matches: list[dict[str, Any]]


class CatalogChatState(TypedDict):
    question: str
    retrieval_query: str
    conversation: list[dict[str, Any]]
    exact_part_number: str
    matches: list[dict[str, Any]]
    answer: str


def _parse_requirement_text(raw_requirement: str) -> dict[str, Any]:
    text = (raw_requirement or "").strip()
    if not text:
        return {"max_results": 10}
    extracted = RequirementService().extract(text=text)
    requirement: dict[str, Any] = {"max_results": 10}
    for source, target in (("product_kind", "kind"), ("product_name", "product_name"), ("product_category", "category"), ("size_inch", "size"), ("material", "material"), ("system", "system"), ("class_name", "class_name"), ("sdr", "sdr"), ("schedule", "schedule"), ("specifications", "specifications"), ("product_variant", "product_variant"), ("part_number", "part_number"), ("hsn_code", "hsn_code")):
        if extracted.get(source):
            requirement[target] = extracted[source]
    system = str(extracted.get("system") or "").upper()
    if system.startswith(("SCH", "SDR")):
        requirement["class_name"] = system

    limit_match = re.search(r"(\d+)\s*(?:result|matches|items)", text.lower())
    if limit_match:
        requirement["max_results"] = int(limit_match.group(1))

    return requirement


def parse_requirement_text(state: RequirementState) -> RequirementState:
    state["requirement"] = _parse_requirement_text(state.get("raw_requirement", ""))
    return state


def normalize_requirement(state: RequirementState) -> RequirementState:
    request = RequirementRequest.model_validate(state["requirement"])
    state["summary"] = build_requirement_summary(request)
    state["requirement"] = request.model_dump()
    return state


def load_catalog_for_requirement(state: RequirementState) -> RequirementState:
    state["catalog"] = load_catalog_records()
    return state


def rank_catalog_matches(state: RequirementState) -> RequirementState:
    request = RequirementRequest.model_validate(state["requirement"])
    state["matches"] = match_products(request)
    return state


def build_requirement_graph() -> StateGraph:
    workflow = StateGraph(RequirementState)
    workflow.add_node("parse_requirement_text", parse_requirement_text)
    workflow.add_node("normalize_requirement", normalize_requirement)
    workflow.add_node("load_catalog_for_requirement", load_catalog_for_requirement)
    workflow.add_node("rank_catalog_matches", rank_catalog_matches)

    workflow.set_entry_point("parse_requirement_text")
    workflow.add_edge("parse_requirement_text", "normalize_requirement")
    workflow.add_edge("normalize_requirement", "load_catalog_for_requirement")
    workflow.add_edge("load_catalog_for_requirement", "rank_catalog_matches")
    workflow.add_edge("rank_catalog_matches", END)
    return workflow.compile()


def run_requirement_graph(requirement: RequirementRequest | dict[str, Any] | str) -> dict[str, Any]:
    graph = build_requirement_graph()
    if isinstance(requirement, str):
        payload = {"raw_requirement": requirement, "requirement": {}, "summary": "", "catalog": [], "matches": []}
        result = graph.invoke(payload)
    else:
        payload = requirement.model_dump() if isinstance(requirement, RequirementRequest) else requirement
        result = graph.invoke({"raw_requirement": "", "requirement": payload, "summary": "", "catalog": [], "matches": []})
    return {
        "summary": result.get("summary", ""),
        "count": len(result.get("matches", [])),
        "matches": result.get("matches", []),
    }


def run_requirement_agent(raw_requirement: str) -> dict[str, Any]:
    return run_requirement_graph(raw_requirement)


def retrieve_chat_context(state: CatalogChatState) -> CatalogChatState:
    query = state["retrieval_query"]
    # Resolve numeric SKU-like tokens against the canonical catalog first. This
    # bypasses LLM extraction and semantic ranking for exact identifier lookups.
    tokens = re.findall(r"(?<!\d)\d{6,14}(?!\d)", query)
    catalog_parts = {
        str(record.get("part_number", "")).strip(): record
        for record in load_catalog_records()
        if str(record.get("part_number", "")).strip()
    }
    exact_part = next((token for token in tokens if token in catalog_parts), None)
    if exact_part:
        matches = match_products({"part_number": exact_part, "max_results": 5})
        state["exact_part_number"] = exact_part
        state["matches"] = matches[:5]
        return state

    result = run_requirement_graph(query)
    state["matches"] = list(result.get("matches") or [])[:5]
    return state


def generate_catalog_chat_answer(state: CatalogChatState) -> CatalogChatState:
    matches = state.get("matches") or []
    exact_part = state.get("exact_part_number")
    if exact_part and matches:
        product_name = str(matches[0].get("product_name") or "name not listed")
        answer = f"The catalog product name for part number {exact_part} is {product_name}."
    else:
        answer = answer_with_catalog_context(
            state["question"], matches, state.get("conversation") or []
        ) if matches else None
    if not answer and matches:
        best = matches[0]
        name = str(best.get("product_name") or "the closest catalog item")
        part_number = str(best.get("part_number") or "part number not listed")
        answer = (
            f"I found {len(matches)} relevant catalog match{'es' if len(matches) != 1 else ''}. "
            f"The closest is {name} (part {part_number}). Check the catalog references below, "
            "or add a size/specification to narrow the result."
        )
    elif not answer:
        answer = (
            "I couldn't find a confident catalog match for that question. Try a product name, "
            "exact part number, size, or specification (such as SDR, schedule, or class)."
        )
    state["answer"] = answer
    return state


def build_catalog_chat_graph() -> Any:
    workflow = StateGraph(CatalogChatState)
    workflow.add_node("retrieve_catalog_context", retrieve_chat_context)
    workflow.add_node("generate_catalog_chat_answer", generate_catalog_chat_answer)
    workflow.set_entry_point("retrieve_catalog_context")
    workflow.add_edge("retrieve_catalog_context", "generate_catalog_chat_answer")
    workflow.add_edge("generate_catalog_chat_answer", END)
    return workflow.compile()


def run_catalog_chat_graph(
    question: str,
    retrieval_query: str | None = None,
    conversation: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    graph = build_catalog_chat_graph()
    result = graph.invoke({
        "question": question,
        "retrieval_query": retrieval_query or question,
        "conversation": conversation or [],
        "exact_part_number": "",
        "matches": [],
        "answer": "",
    })
    return {"answer": result.get("answer", ""), "matches": result.get("matches", [])}
