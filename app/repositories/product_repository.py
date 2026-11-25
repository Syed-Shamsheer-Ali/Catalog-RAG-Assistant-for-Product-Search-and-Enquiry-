from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Product


class ProductRepository:
    """Persistence adapter for the canonical, source-traceable product catalog."""

    def __init__(self, session: Session):
        self.session = session

    def get(self, product_id: str) -> Product | None:
        return self.session.get(Product, product_id)

    def list_by_kind(self, kind: str) -> list[Product]:
        return list(self.session.scalars(select(Product).where(Product.product_kind == kind)).all())

    def upsert_records(self, records: list[dict[str, Any]]) -> int:
        for record in records:
            product_id = str(record["product_id"])
            entity = self.session.get(Product, product_id)
            values = {
                "product_id": product_id, "part_number": record.get("part_number"),
                "product_kind": str(record.get("product_kind") or "OTHER"),
                "product_category": record.get("product_category"),
                "product_name": str(record.get("product_name") or product_id),
                "size_inch": record.get("size_inch"), "material": record.get("material"),
                "system": record.get("system"), "price": record.get("price"),
                "source_document": str(record.get("source_document") or ""),
                "source_page": int(record.get("source_page") or 0),
                "needs_review": bool(record.get("needs_review")), "record_json": record,
            }
            if entity is None:
                self.session.add(Product(**values))
            else:
                for key, value in values.items():
                    setattr(entity, key, value)
        self.session.flush()
        return len(records)


class PriceRepository(ProductRepository):
    """Read-only local price-list projection over persisted product records."""

    def get_price_by_part_number(self, part_number: str) -> float | None:
        entity = self.session.scalar(select(Product).where(Product.part_number == part_number))
        return entity.price if entity else None
