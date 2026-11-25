from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.catalog.matcher import load_catalog_records
from app.graph import run_catalog_chat_graph


def answer_catalog_question(
    question: str,
    conversation: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Retrieve catalog records and answer with local LLM context when configured."""
    current_question = question.strip()
    if not current_question:
        return {"answer": "Ask me about a product, size, specification, or part number.", "matches": []}

    lower_question = current_question.lower()
    if re.fullmatch(r"(?:hi|hello|hey|good morning|good afternoon|good evening)[!. ]*", lower_question):
        return {
            "answer": "Hi! I can help find products in the local catalog. Ask about a pipe, fitting, valve, accessory, or cement; include a size or part number if you know it.",
            "matches": [],
        }

    history = conversation or []
    previous_user = next(
        (str(item.get("content") or "") for item in reversed(history) if item.get("role") == "user"),
        "",
    )
    # Only carry history when the new message clearly depends on it. Broad
    # matches such as "more" or "price" made standalone product questions
    # inherit stale SKUs from earlier turns.
    is_follow_up = bool(re.match(
        r"^(?:and\s+(?:its|their|that|those)\b|(?:what|how)\s+about\s+(?:it|that|those|them|its|their)\b|"
        r"(?:what|how)\s+(?:is|are)\s+(?:its|their|that|those)\b|"
        r"tell\s+me\s+more\s+about\s+(?:it|that|those|them)\b|"
        r"(?:give|show)\s+me\s+more\s+(?:details|information)\s+about\s+(?:it|that|those|them)\b|"
        r"same\s+(?:one|product|size|item)\b|which\s+one\b|compare\s+them\b)",
        lower_question,
    ))
    retrieval_query = f"{previous_user} {current_question}".strip() if previous_user and is_follow_up else current_question
    answer_history = history if is_follow_up else []

    if re.search(r"\b(categories|product types|what products|what do you sell|catalog overview)\b", lower_question):
        try:
            records = load_catalog_records()
        except Exception:
            return {
                "answer": "The local product catalog isn't available right now. Check that the processed catalog file exists, then try again.",
                "matches": [],
            }
        counts = Counter(str(record.get("product_kind") or "OTHER") for record in records)
        breakdown = ", ".join(f"{kind.title()} ({count})" for kind, count in sorted(counts.items()))
        return {
            "answer": f"The local catalog contains {len(records)} sellable products across {len(counts)} product types: {breakdown}.",
            "matches": [],
        }

    try:
        return run_catalog_chat_graph(current_question, retrieval_query, answer_history)
    except Exception:
        return {
            "answer": "I couldn't search the local catalog just now. Check that the processed catalog is available, then try again.",
            "matches": [],
        }
