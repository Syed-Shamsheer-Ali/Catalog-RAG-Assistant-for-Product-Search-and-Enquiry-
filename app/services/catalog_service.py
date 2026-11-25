from __future__ import annotations

from sqlalchemy.orm import Session

from app.catalog.matcher import load_catalog_records
from app.repositories.product_repository import ProductRepository


class CatalogService:
    def __init__(self, repository: ProductRepository):
        self.repository = repository

    def synchronize_local_catalog(self) -> int:
        """Mirror validated local catalog data into SQLite without changing its source."""
        return self.repository.upsert_records(load_catalog_records())
