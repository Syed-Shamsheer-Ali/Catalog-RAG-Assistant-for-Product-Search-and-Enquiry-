#!/usr/bin/env python3
"""Match a local requirement against the canonical product catalog."""

from __future__ import annotations

import json
import sys

from app.catalog.matcher import build_requirement_summary, match_products


def main() -> None:
    if len(sys.argv) > 1:
        payload = json.loads(sys.argv[1])
    else:
        payload = {
            "kind": "PIPE",
            "category": "CPVC pipes",
            "size": "1/2",
            "max_results": 5,
        }

    matches = match_products(payload)
    print(build_requirement_summary(payload))
    print(f"Matched {len(matches)} records")
    for item in matches[:5]:
        print(f"{item['part_number']} | {item['product_kind']} | {item['size_inch']} | score={item['match_score']}")


if __name__ == "__main__":
    main()
