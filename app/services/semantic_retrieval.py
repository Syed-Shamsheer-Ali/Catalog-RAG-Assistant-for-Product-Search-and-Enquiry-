from __future__ import annotations

import json
import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import EMBEDDING_MODEL_PATH, PRODUCT_DATA_PATH, VECTOR_DB_PATH

_TEXT_FIELDS = (
    "product_kind", "product_category", "product_name", "product_variant",
    "section_title", "source_heading", "hsn_code", "search_text",
    "size_inch", "size_cm", "compound_size", "material", "system",
    "class_name", "sdr", "schedule", "part_number", "price_type",
)


@lru_cache(maxsize=1)
def _load_encoder(model_path: str) -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_path, local_files_only=True)


def _collection_name(dataset_path: str) -> str:
    resolved_path = str(Path(dataset_path).resolve())
    default_path = str(Path(PRODUCT_DATA_PATH).resolve())
    if resolved_path == default_path:
        return "product_catalog"
    namespace = hashlib.sha1(resolved_path.encode("utf-8")).hexdigest()[:12]
    return f"product_catalog_{namespace}"


@lru_cache(maxsize=8)
def _get_collection(path: str, collection_name: str) -> Any:
    import chromadb

    client = chromadb.PersistentClient(path=path)
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def _document(record: dict[str, Any]) -> str:
    return " ".join(str(record.get(key) or "") for key in _TEXT_FIELDS).strip()


@lru_cache(maxsize=4)
def _index_catalog(model_path: str, database_path: str, collection_name: str, serialized_records: str) -> None:
    records = json.loads(serialized_records)
    ids = [str(record.get("product_id") or "") for record in records]
    documents = [_document(record) for record in records]
    collection = _get_collection(database_path, collection_name)

    # Reuse persisted vectors across app restarts. Re-embedding the entire
    # catalog on the first query made every new process pay the full indexing
    # cost even when the catalog had not changed.
    indexed = collection.get(include=["documents"])
    indexed_documents = dict(zip(indexed.get("ids") or [], indexed.get("documents") or []))
    desired_documents = dict(zip(ids, documents))

    removed_ids = sorted(set(indexed_documents) - set(desired_documents))
    if removed_ids:
        collection.delete(ids=removed_ids)

    changed = [
        (product_id, document)
        for product_id, document in desired_documents.items()
        if indexed_documents.get(product_id) != document
    ]
    if not changed:
        return

    changed_ids = [product_id for product_id, _ in changed]
    changed_documents = [document for _, document in changed]
    vectors = _load_encoder(model_path).encode(
        changed_documents, convert_to_numpy=True, normalize_embeddings=True
    ).astype("float32")
    collection.upsert(
        ids=changed_ids,
        documents=changed_documents,
        embeddings=vectors.tolist(),
    )


def semantic_scores(
    records: list[dict[str, Any]],
    query: str,
    dataset_path: str | Path = PRODUCT_DATA_PATH,
) -> dict[str, float]:
    """Index catalog vectors in Chroma and return local cosine similarity scores."""
    model_path = Path(EMBEDDING_MODEL_PATH)
    if not EMBEDDING_MODEL_PATH or not model_path.exists() or not records or not query.strip():
        return {}

    try:
        database_path = str(Path(VECTOR_DB_PATH).resolve())
        collection_name = _collection_name(str(dataset_path))
        serialized_records = json.dumps(records, ensure_ascii=False, sort_keys=True)
        _index_catalog(str(model_path), database_path, collection_name, serialized_records)
        encoder = _load_encoder(str(model_path))
        collection = _get_collection(database_path, collection_name)
        query_vector = encoder.encode([query], convert_to_numpy=True, normalize_embeddings=True)
        result = collection.query(
            query_embeddings=query_vector.tolist(),
            n_results=collection.count(),
            include=["distances"],
        )
        result_ids = (result.get("ids") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        valid_ids = {str(record.get("product_id") or "") for record in records}
        return {
            product_id: max(0.0, min(1.0, 1.0 - float(distance)))
            for product_id, distance in zip(result_ids, distances)
            if product_id in valid_ids
        }
    except Exception:
        # Structured matching remains available if the optional local model or
        # vector database is unavailable.
        return {}
