"""Size and compound-size parsing for catalog rows."""

from __future__ import annotations

import re
from typing import Optional

# Documented cm → inch pairs from the catalog tables. Used only when the
# inch glyph is present but unreadable, or to cross-check extracted inches.
CM_TO_INCH: dict[str, str] = {
    "1.5": "1/2",
    "2.0": "3/4",
    "2.5": "1",
    "3.2": "1 1/4",
    "4.0": "1 1/2",
    "5.0": "2",
    "6.5": "2 1/2",
    "8.0": "3",
    "10.0": "4",
    "15.0": "6",
}

FRACTION_CHARS = {
    "\u00bd": "1/2",
    "\u00be": "3/4",
    "\u00bc": "1/4",
    "\u215b": "1/8",
    "\u00b9\u2044\u2082": "1/2",
}

COMPOUND_SPLIT_RE = re.compile(r"\s*[xX×]\s*")
CM_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?")
INCH_TOKEN_RE = re.compile(
    r"(?:\d+\s+)?(?:\d+/\d+)|(?:\d+\s*)?(?:[\u00bc\u00bd\u00be\u215b])|\d+(?:\.\d+)?"
)


def normalize_fraction_text(value: str) -> str:
    text = (value or "").strip()
    text = text.replace("\xa0", " ")
    for raw, mapped in FRACTION_CHARS.items():
        text = text.replace(raw, mapped)
    text = re.sub(r"(\d+)\s+(\d+/\d+)", r"\1 \2", text)
    text = re.sub(r"(\d+)(\d/\d)", r"\1 \2", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_inch_token(token: str) -> Optional[str]:
    token = normalize_fraction_text(token)
    if not token or token == "-":
        return None
    if token in {"1/2", "3/4", "1/4", "1/8"}:
        return token
    if re.fullmatch(r"\d+ \d+/\d+", token):
        return token
    if re.fullmatch(r"\d+(?:\.\d+)?", token):
        if token.endswith(".0"):
            token = token[:-2]
        return token
    mapped = FRACTION_CHARS.get(token)
    return mapped or token or None


def inch_from_cm(cm: str) -> Optional[str]:
    key = cm.strip()
    if key in CM_TO_INCH:
        return CM_TO_INCH[key]
    if key.endswith(".0") is False and f"{key}.0" in CM_TO_INCH:
        return CM_TO_INCH[f"{key}.0"]
    return None


def parse_compound_size(raw: str) -> list[str]:
    text = normalize_fraction_text(raw)
    if not text:
        return []
    parts = [p.strip() for p in COMPOUND_SPLIT_RE.split(text) if p.strip()]
    return parts


def is_compound_size(raw: Optional[str]) -> bool:
    if not raw:
        return False
    return len(parse_compound_size(raw)) >= 2


def format_compound(parts: list[str]) -> Optional[str]:
    cleaned = [p for p in (normalize_inch_token(p) or p.strip() for p in parts) if p]
    if not cleaned:
        return None
    return " x ".join(cleaned)


def parse_size_fields(
    size_cm_raw: Optional[str],
    size_inch_raw: Optional[str],
) -> dict[str, Optional[str]]:
    cm_raw = normalize_fraction_text(size_cm_raw or "")
    inch_raw = normalize_fraction_text(size_inch_raw or "")
    cm_parts = parse_compound_size(cm_raw) if cm_raw else []
    inch_parts = parse_compound_size(inch_raw) if inch_raw else []

    normalized_cm_parts: list[str] = []
    for part in cm_parts or ([cm_raw] if cm_raw else []):
        token = CM_TOKEN_RE.search(part)
        if token:
            normalized_cm_parts.append(token.group(0))
        elif part:
            normalized_cm_parts.append(part)

    normalized_inch_parts: list[str] = []
    used_cm_fallback = False
    source_inch_parts = inch_parts or ([inch_raw] if inch_raw else [])
    if source_inch_parts:
        for idx, part in enumerate(source_inch_parts):
            normalized = normalize_inch_token(part)
            if normalized is None or normalized in {"�", "?"}:
                if idx < len(normalized_cm_parts):
                    fallback = inch_from_cm(normalized_cm_parts[idx])
                    if fallback:
                        normalized_inch_parts.append(fallback)
                        used_cm_fallback = True
            else:
                # Unicode fractions sometimes lose the leading whole number.
                if idx < len(normalized_cm_parts):
                    expected = inch_from_cm(normalized_cm_parts[idx])
                    if expected and normalized in {"1/4", "1/2"} and expected.startswith("1 "):
                        normalized = expected
                normalized_inch_parts.append(normalized)
    elif normalized_cm_parts:
        for part in normalized_cm_parts:
            fallback = inch_from_cm(part)
            if fallback:
                normalized_inch_parts.append(fallback)
                used_cm_fallback = True

    size_cm = format_compound(normalized_cm_parts) if normalized_cm_parts else None
    size_inch = format_compound(normalized_inch_parts) if normalized_inch_parts else None
    compound = None
    if (size_cm and " x " in size_cm) or (size_inch and " x " in size_inch):
        compound = size_inch or size_cm

    size_text_bits = []
    if size_cm:
        size_text_bits.append(f"{size_cm} cm")
    if size_inch:
        size_text_bits.append(f"{size_inch} inch")
    size_text = " / ".join(size_text_bits) if size_text_bits else (cm_raw or inch_raw or None)

    return {
        "size_cm": size_cm,
        "size_inch": size_inch,
        "size_text": size_text,
        "compound_size": compound,
        "inch_from_cm_fallback": used_cm_fallback,
    }
