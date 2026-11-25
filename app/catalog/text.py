"""Text cleanup helpers for PDF extraction."""

from __future__ import annotations

import re
from typing import Iterable, Optional

HSN_RE = re.compile(r"HSN\s*CODE\s*[:\-]?\s*(\d{4,10})", re.IGNORECASE)
PART_RE = re.compile(r"\b([3-9]\d{7})\b")
EFFECTIVE_RE = re.compile(
    r"w\.e\.f\.?\s*(\d{1,2}\s+[A-Za-z]{3,9},?\s*\d{4})",
    re.IGNORECASE,
)
SECTION_TITLE_RE = re.compile(
    r"^(?P<title>.+?)(?:\s*[-–]\s*)?(?:HSN\s*CODE\s*[:\-]?\s*(?P<hsn>\d{4,10}))?$",
    re.IGNORECASE,
)
HEADER_HINTS = (
    "size",
    "part",
    "mrp",
    "std",
    "box",
    "qty",
    "inch",
    "cm",
    "pkg",
    "taxes",
)
MARKETING_HINTS = (
    "warranty applicable",
    "manufactured from",
    "ideal for hot",
    "plumbing system",
    "price list w.e.f",
    "inspection of",
    "certified",
)


def clean_cell(value: Optional[str]) -> str:
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ")
    text = text.replace("`", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = text.replace("\n", " ").strip()
    return text


def join_cells(cells: Iterable[Optional[str]]) -> str:
    parts = [clean_cell(c) for c in cells]
    return " ".join(p for p in parts if p)


def merge_split_numeric_tokens(text: str) -> str:
    """Repair common PDF table splits without inventing new digits."""
    previous = None
    current = text
    while previous != current:
        previous = current
        current = re.sub(r"(\d+)\s+0\b", r"\g<1>0", current)
        current = re.sub(r"\b([3-9]\d{5})\s+(\d{2})\b", r"\1\2", current)
    return current


def extract_hsn(text: str) -> Optional[str]:
    match = HSN_RE.search(text or "")
    return match.group(1) if match else None


def extract_part_numbers(text: str) -> list[str]:
    return PART_RE.findall(merge_split_numeric_tokens(text or ""))


def extract_effective_date(text: str) -> Optional[str]:
    match = EFFECTIVE_RE.search(text or "")
    if not match:
        return None
    raw = re.sub(r"\s+", " ", match.group(1)).replace(",", "")
    months = {
        "jan": "01",
        "feb": "02",
        "mar": "03",
        "apr": "04",
        "may": "05",
        "jun": "06",
        "jul": "07",
        "aug": "08",
        "sep": "09",
        "oct": "10",
        "nov": "11",
        "dec": "12",
    }
    bits = raw.split()
    if len(bits) != 3:
        return raw
    day, month, year = bits
    month_num = months.get(month[:3].lower())
    if not month_num:
        return raw
    return f"{year}-{month_num}-{int(day):02d}"


def looks_like_header_row(text: str) -> bool:
    lowered = (text or "").lower()
    hits = sum(1 for hint in HEADER_HINTS if hint in lowered)
    return hits >= 2 and not extract_part_numbers(text)


def looks_like_marketing(text: str) -> bool:
    lowered = (text or "").lower()
    if any(hint in lowered for hint in MARKETING_HINTS) and not extract_part_numbers(text):
        if "hsn" not in lowered:
            return True
    return False


def looks_like_reversed_noise(text: str) -> bool:
    tokens = [t for t in (text or "").split() if t]
    if len(tokens) >= 8:
        singles = sum(1 for t in tokens if len(t) == 1)
        if singles / len(tokens) >= 0.4:
            return True
    compact = re.sub(r"\s+", "", text or "")
    if "derutcafunaM" in compact or "DESUERA" in compact:
        return True
    return False


def looks_like_section_title(text: str) -> bool:
    cleaned = clean_cell(text)
    if not cleaned or looks_like_header_row(cleaned):
        return False
    if looks_like_marketing(cleaned) or looks_like_reversed_noise(cleaned):
        return False
    if extract_hsn(cleaned):
        return True
    if extract_part_numbers(cleaned):
        return False
    if len(cleaned) < 4:
        return False
    letters = sum(ch.isalpha() for ch in cleaned)
    return letters >= 8 and not cleaned[:1].isdigit()


def section_name(text: str) -> str:
    cleaned = clean_cell(text)
    cleaned = HSN_RE.sub("", cleaned)
    cleaned = re.sub(r"[-–:]+$", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def parse_int(token: Optional[str]) -> Optional[int]:
    if token is None:
        return None
    text = str(token).strip().replace(",", "")
    if text in {"", "-", "—"}:
        return None
    if re.fullmatch(r"\d+", text):
        return int(text)
    return None


def parse_float(token: Optional[str]) -> Optional[float]:
    if token is None:
        return None
    text = str(token).strip().replace(",", "")
    if text in {"", "-", "—"}:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    return None
