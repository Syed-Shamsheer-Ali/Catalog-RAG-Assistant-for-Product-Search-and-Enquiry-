from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]

OFFLINE_MODE = str(os.getenv("OFFLINE_MODE", "true")).strip().lower() == "true"
LLM_MODEL_PATH = os.getenv("LLM_MODEL_PATH", "").strip() or str(ROOT / "models" / "llm" / "assistant.gguf")
EMBEDDING_MODEL_PATH = os.getenv("EMBEDDING_MODEL_PATH", "").strip() or str(ROOT / "models" / "embeddings" / "all-MiniLM-L6-v2")
WHISPER_MODEL_PATH = os.getenv("WHISPER_MODEL_PATH", "").strip() or str(ROOT / "models" / "whisper" / "whisper-small")
VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH", str(ROOT / "data" / "vector_db")).strip()
PRODUCT_DATA_PATH = os.getenv("PRODUCT_DATA_PATH", str(ROOT / "data" / "processed" / "ashirvad_products.json")).strip()
CATALOG_PDF_PATH = os.getenv("CATALOG_PDF_PATH", str(ROOT / "data" / "raw" / "Product_Price_List.pdf")).strip()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/product_agent.db").strip()
TOP_K = int(os.getenv("TOP_K", "5"))
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.75"))
MATCH_AUTO_THRESHOLD = float(os.getenv("MATCH_AUTO_THRESHOLD", "0.82"))
MATCH_MARGIN_THRESHOLD = float(os.getenv("MATCH_MARGIN_THRESHOLD", "0.08"))


def get_model_path(name: str, fallback: str = "") -> str:
    value = os.getenv(name, fallback).strip()
    return value or fallback
