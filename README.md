# Pipe Product Agent

A local-first pipe and fittings requirements application. Streamlit is the primary user interface; FastAPI is available as an optional API. Product records and prices come only from the local Ashirvad catalog. Local extraction and retrieval help identify products, while Python validates requirements and calculates totals.

## Start here

1. Install Python dependencies in a virtual environment.
2. Put the catalog PDF at `data/raw/Product_Price_List.pdf` or set `CATALOG_PDF_PATH` to its location.
3. Build the searchable product catalog:

   ```powershell
   .\.venv\Scripts\python.exe scripts\prepare_catalog.py
   ```

4. Start the UI:

   ```powershell
   .\.venv\Scripts\python.exe -m streamlit run app\streamlit_app.py
   ```

The catalog builder writes sellable SKU records to `data/processed/ashirvad_products.json` and a quality summary to `data/processed/catalog_quality_report.json`. Rebuild after replacing the source PDF, then restart Streamlit.

## User input guide

The UI supports text, images, voice, and CSV/Excel. Text entry recognizes common reordered phrasing such as `1.5 size of 10 Ball Valve - Handle`, extracting the size, quantity, and product name for catalog matching. A clear part number is the fastest and most reliable way to identify an item. For a pipe, include its size, SDR or schedule when known, and the requested stick length (3 m or 5 m). See [docs/INPUT_GUIDE.md](docs/INPUT_GUIDE.md) for examples, accepted spreadsheet headers, and review behavior.

Users can edit rows before submission. The app displays the local catalog match, rate basis, line total, validation state, and estimate total. Missing catalog data, unsupported units, duplicate rows, or close competing matches remain flagged for review. It does not estimate a missing price.

## Architecture and orchestration

The application follows MVC with services and repositories separated from the UI. A floating chat button opens a read-only catalog assistant for product enquiries and details, including as a fallback when form autofill misses an item. Rows marked `Not Found` or `Needs Review` include an **Ask assistant for details** action that opens chat with that row's product, size, and part number prefilled; the user sends the enquiry and reviews the catalog references. Chat retrieves matching SKUs, passes those records to a local Ollama or GGUF model for a grounded response, and displays source page, part number, size, and catalog price as references. Exact part numbers found in the catalog bypass LLM extraction and semantic ranking, so exact SKU questions retrieve their records directly. Conversation history is included only for clear follow-ups; standalone product questions are searched independently to prevent stale product names or SKUs from contaminating new answers. If the model runtime is unavailable, it returns a deterministic match summary.

- **View:** `app/streamlit_app.py` presents the customer form, input methods, editable item rows, match review, and estimate.
- **Controller:** `app/controllers/` coordinates extraction and submission requests.
- **Model and schemas:** `app/models/`, `app/schemas/`, and `app/database/` define SQLAlchemy records, Pydantic contracts, and SQLite setup.
- **Services:** `app/services/` handles parsing, local enrichment, matching coordination, validation, and deterministic totals.
- **Catalog and retrieval:** `app/catalog/` parses and matches product data; `app/rag_price.py` obtains candidates and prices from the local processed catalog. Exact part-number and structured-attribute checks run before optional Chroma vector reranking. The persistent vector index is reused across restarts; only new or changed catalog records are re-embedded.
- **Persistence:** `app/repositories/` isolates database operations. LLMs do not write to the database or set prices.
- **API:** `app/routes.py` and `app/api.py` keep FastAPI endpoints available independently of Streamlit.
- **LangGraph:** `app/graph.py` provides the requirement workflow (parse, normalize, load-local-catalog, rank-match) and catalog chat workflow (exact-SKU lookup first; otherwise parse and rank; then generate a grounded response). The regular Streamlit quote path calls the same local services directly.

For the full data flow and module responsibilities, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Catalog and pricing rules

The catalog PDF is the source of truth. `app/catalog/pdf_table_ingest.py` reads the PDF tables and nearby section headings, including headings printed just outside a table grid, and creates one record per sellable SKU. Each record stores its normalized section title, source heading, HSN code, and combined search text alongside part number, dimensions, price, unit basis, pack values, variant, page, and source text. The quality report lists heading coverage and captured section names. Pipe SKUs are represented separately for 3 m and 5 m lengths; fittings and accessories use their per-piece price basis. The list price is tax inclusive where the PDF labels it that way. Chat answers to exact part-number questions use the exact retrieved catalog record directly, so the LLM cannot substitute a different product name.

The catalog supplied with this project is effective **1 March 2025**. Replace it with the applicable local price-list version when prices change and rebuild the JSON. The application never calls a cloud pricing service. Exact SKU matches take priority. Product-name, size, compound dimensions, and specification signals rank likely matches. A match is automatic only above the configured score and separation thresholds; otherwise the product card shows a searchable list of suggestions with product names, part numbers, sizes, and prices.

Bill images are locally preprocessed and OCR'd with positioned table rows mapped into item name, quantity, and source-document rate. Text PDFs are parsed from embedded text and table coordinates. Source rates are traceability data and never override local catalog prices. Original OCR text and confidence are available during review. See [the input guide](docs/INPUT_GUIDE.md) for supported formats and field guidance.

The requirements editor uses one readable card per product, with product details, quantity inputs, price, and match status grouped together. For ambiguous matches, choose the correct catalog item from the searchable suggestions. Local package sizes appear in **Quantity per Box**. Enter a box count to calculate pieces from that capacity, or leave it blank and enter loose pieces, meters, or fixed pipe lengths in **Total Quantity**. The calculation service follows each catalog SKU's price basis and keeps per-box, per-piece, per-meter, and fixed-length pricing distinct.

Catalog values with missing or uncertain source fields are retained with review flags in the quality report. Check that report after every rebuild. The former converted-CSV importer remains in `app/catalog/csv_ingest.py` for compatibility; use `scripts/prepare_catalog.py` for the PDF table importer.

## Offline models

No cloud AI API is used. Optional local model files are configured with environment variables. Text rules, catalog matching, validation, and quote calculations work without an LLM or embedding model. Image OCR and voice transcription require their local model dependencies and model files to have been installed/downloaded before offline use.

Example `.env` entries (use local absolute paths on Windows):

```dotenv
OFFLINE_MODE=true
CATALOG_PDF_PATH=C:/path/to/Ashirvad_CPVC_PriceList.pdf
PRODUCT_DATA_PATH=C:/path/to/pipe_product_agent/data/processed/ashirvad_products.json
LLM_MODEL_PATH=qwen2.5:3b
EMBEDDING_MODEL_PATH=C:/path/to/pipe_product_agent/models/embeddings/all-MiniLM-L6-v2
WHISPER_MODEL_PATH=C:/models/whisper-small
MATCH_AUTO_THRESHOLD=0.82
MATCH_MARGIN_THRESHOLD=0.08
```

`LLM_MODEL_PATH` accepts a locally running Ollama model name (for example, `qwen2.5:3b`) or a GGUF file path. When unset, it defaults to `models/llm/assistant.gguf`. The embedding model defaults to `models/embeddings/all-MiniLM-L6-v2`, and Whisper defaults to `models/whisper/whisper-small`. Keep inference local; the Ollama integration calls only the local Ollama service.

### Enable Chroma vector search on Windows

The root `models/` directory is for downloaded model files and is normally empty in a fresh checkout. Install the embedding model locally to enable semantic catalog search. The steps below use the existing project virtual environment and save the model inside the project.

1. Open PowerShell in the project root and install the two packages needed for vector search:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install chromadb sentence-transformers
   ```

2. Create a local model directory and download the embedding model into it. This step needs an internet connection; the app itself loads the saved model locally afterward.

   ```powershell
   New-Item -ItemType Directory -Force models\embeddings | Out-Null
   .\.venv\Scripts\python.exe -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2').save('models/embeddings/all-MiniLM-L6-v2')"
   ```

3. The app defaults to the model directory from step 2, so you do not need to edit `.env`. If you saved the model elsewhere, set `EMBEDDING_MODEL_PATH` to that directory. Chroma uses `data/vector_db` by default; set `VECTOR_DB_PATH` only if you want a different location.

   ```dotenv
   EMBEDDING_MODEL_PATH=C:/path/to/your/local/model
   ```

   Leave `DATABASE_URL` as configured; it continues to store submissions and audit events in SQLite.

4. Restart Streamlit and make a catalog lookup. Chroma creates or updates its persistent product collection under `data/vector_db` on the first lookup. The processed product JSON remains the source of product details and prices.

Chroma's local `PersistentClient` saves its data to the configured directory, and Sentence Transformers can load a model from a local directory. See the [Chroma persistence guide](https://docs.trychroma.com/docs/run-chroma/cloud-client?lang=python) and [Sentence Transformers model reference](https://sbert.net/docs/package_reference/base/model.html).

### Enable local voice transcription

The app looks for the faster-whisper model at `models/whisper/whisper-small` by default. To download it there, run this from the project root in PowerShell (requires an internet connection):

```powershell
New-Item -ItemType Directory -Force models\whisper | Out-Null
.\.venv\Scripts\python.exe -c "from faster_whisper.utils import download_model; print(download_model('small', output_dir='models/whisper/whisper-small'))"
```

The project loads Whisper from that local directory for CPU transcription. Set `WHISPER_MODEL_PATH` only if you store it somewhere else. The faster-whisper downloader supports saving a model to an explicit output directory ([project implementation](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/utils.py)).

## Database and outputs

Chroma is the vector database for semantic product catalog search. SQLite remains the structured transactional store for submissions and audit events. The processed catalog JSON remains the canonical source of product records and prices. Generated estimate files are written under `data/processed/` and include PDF, CSV, and JSON exports.

## Run the API (optional)

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api:app --reload
```

Existing endpoints are documented in the FastAPI application. API routes remain separate from the Streamlit view.

## Tests

Run the test suite from the project root:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
.\.venv\Scripts\python.exe -m pytest -q
```

The catalog workflow tests parse known rows from the PDF, verify pipe 3 m/5 m prices and per-piece prices, and exercise clear, specified, and ambiguous requirement examples.

## Project layout

```text
app/
├── catalog/          # PDF/CSV catalog ingestion and deterministic matching
├── controllers/      # request coordination
├── database/         # SQLAlchemy engine and session setup
├── models/           # SQLAlchemy entities
├── repositories/     # database access
├── schemas/          # Pydantic request/data contracts
├── services/         # extraction, matching, validation, pricing workflow
├── config.py         # local paths and thresholds
├── graph.py          # LangGraph orchestration
├── invoice.py        # estimate/report presentation
├── invoice_export.py # PDF, CSV, and JSON exports
├── routes.py         # FastAPI routes
└── streamlit_app.py  # Streamlit view

data/
├── raw/              # local source catalogs
└── processed/        # searchable catalog, quality report, estimate exports
models/               # optional local model files
logs/                 # local logs
scripts/              # catalog build utilities
tests/                # unit and workflow tests
docs/                 # architecture and input guides
```
