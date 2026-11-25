#!/usr/bin/env python3
"""Inspect the local product catalog PDF and generate catalog analysis output."""

from __future__ import annotations

from app.catalog.ingest import write_catalog_analysis


def main() -> None:
    analysis = write_catalog_analysis()
    print(f"Catalog analysis generated: {len(analysis['product_sections'])} detected sections")
    print(f"Detected price types: {analysis['price_types']}")
    print(f"Detected effective dates: {analysis['effective_dates']}")


if __name__ == "__main__":
    main()
