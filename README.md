# DocuTrust AI

DocuTrust AI is a local-first, citation-grounded Retrieval-Augmented Generation (RAG) application for policies, standard operating procedures, contracts, invoices, and compliance documents. It ingests supported files, extracts their text, stores searchable chunks in SQLite, and answers questions only when retrieved evidence clears a configurable confidence threshold.

The project is designed as a final-year AIML project: it has a working FastAPI backend, a browser UI, persistent audit history, an offline retrieval baseline, optional OpenAI-compatible synthesis, automated tests, Docker packaging, and a project explanation document.

> **Evidence first:** the response always includes the source chunks used to answer a question. If the retrieved evidence is insufficient, the API returns `insufficient_evidence` instead of presenting a confident answer.

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Technology stack](#technology-stack)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Using the application](#using-the-application)
- [API reference](#api-reference)
- [Retrieval and answer flow](#retrieval-and-answer-flow)
- [Supported documents and OCR](#supported-documents-and-ocr)
- [Data model and persistence](#data-model-and-persistence)
- [Testing](#testing)
- [Docker](#docker)
- [Security and limitations](#security-and-limitations)
- [Project structure](#project-structure)
- [Evaluation plan](#evaluation-plan)
- [Future work](#future-work)

## Features

- Upload and index PDF, DOCX, TXT, Markdown, PNG, JPG/JPEG, TIFF, and BMP files.
- Extract native text from PDF and DOCX files; use local Tesseract OCR for supported image files.
- Split extracted pages into overlapping chunks while retaining document and page metadata.
- Retrieve the five highest-scoring chunks with a deterministic lexical ranking baseline.
- Produce a grounded answer or explicitly abstain when evidence does not meet the confidence threshold.
- Return traceable citations with document name, document ID, page, chunk ID, relevance score, and a focused supporting quote.
- Optionally use an OpenAI-compatible Chat Completions endpoint for concise, source-constrained synthesis.
- Fall back safely to a deterministic answer writer whenever no API key is configured or the optional LLM call fails.
- Persist documents, chunks, query history, citations, and analytics in SQLite.
- Provide document deletion, query-history deletion, document filtering, analytics, a health endpoint, and a lightweight web interface.
- Run locally, through the provided launcher/Makefile, or as a Docker container.

## Architecture

```text
                         ┌────────────────────────────────────┐
                         │       Browser UI / REST client      │
                         └──────────────────┬─────────────────┘
                                            │
                                  FastAPI application
                                            │
     ┌───────────────────────────────┬──────┴──────────────┬──────────────────────────────┐
     │                               │                     │                              │
Upload & validation             Query & retrieval      Analytics / audit              Static frontend
     │                               │                     │                              │
     ▼                               ▼                     ▼                              ▼
Extract text → chunk pages     Lexical ranking       SQLite query_events          HTML / CSS / JavaScript
     │                               │
     │                       confidence threshold
     │                               │
     ▼                               ▼
SQLite documents + chunks ──► grounded answer or `insufficient_evidence`
                                      │
                                      ├─ Deterministic evidence-based writer (default)
                                      └─ Optional OpenAI-compatible synthesis
```

### Ingestion flow

1. A client uploads a file to `POST /api/v1/documents`.
2. The server sanitizes the filename and rejects uploads larger than the configured limit.
3. `app/extraction.py` extracts text and identifies the extraction method.
4. `app/retrieval.py` normalizes text and creates chunks of up to 900 characters with a 150-character overlap.
5. The document record and its chunks are saved in `data/docutrust.db` by default.

### Question-answering flow

1. A client sends a question to `POST /api/v1/query`, optionally limiting the search to selected document IDs.
2. The retriever tokenizes and lightly normalizes the question and each stored chunk, removes a small stop-word list, and calculates a lexical term-frequency/IDF-style score.
3. The five highest scoring chunks become candidate evidence.
4. Confidence is derived from the top evidence score. If it is below `RETRIEVAL_THRESHOLD`, the answer is deliberately abstained.
5. For grounded queries, the app uses optional LLM synthesis when configured; otherwise it creates a concise answer from the top evidence chunk.
6. A query audit event and the cited chunk IDs are written to SQLite. The response includes citations for client-side verification.

## Technology stack

| Area | Technology |
| --- | --- |
| API and validation | FastAPI and Pydantic |
| ASGI server | Uvicorn |
| Persistence | SQLite (Python standard library) |
| PDF parsing | pypdf |
| DOCX parsing | python-docx |
| Image OCR | pytesseract + local Tesseract binary |
| Optional LLM | Any OpenAI-compatible Chat Completions API |
| Frontend | Static HTML, CSS, and JavaScript |
| Testing | pytest |
| Containerization | Docker |

## Quick start

### Prerequisites

- Python 3.10+ (the Docker image uses Python 3.12)
- `pip`
- Tesseract only if you plan to upload images or run OCR
- An OpenAI-compatible API key only if you want LLM synthesis; it is not required for the offline demo

### Option 1: one command

```bash
./start.sh
```

The launcher creates `.venv` if needed, installs dependencies, creates `.env` from `.env.example` when absent, stops a process already listening on port 8000, and starts Uvicorn in the background.

Open the application at [http://127.0.0.1:8000](http://127.0.0.1:8000). Logs are written to `server.log` and the process ID to `server.pid`.

### Option 2: manual setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Then use:

- App UI: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Interactive OpenAPI documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### Makefile shortcuts

```bash
make install  # Create the venv and install dependencies
make start    # Run ./start.sh
make test     # Run the test suite
```

## Configuration

Copy the supplied template before setting values:

```bash
cp .env.example .env
```

`.env` is intentionally ignored by Git. Never commit an API key.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | empty | Enables optional OpenAI-compatible answer synthesis. |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Base URL for the compatible Chat Completions endpoint. |
| `OPENAI_MODEL` | `gpt-4.1-mini` | Model name sent to the compatible endpoint. |
| `TESSERACT_CMD` | empty | Full path to the Tesseract executable when it is not on `PATH`. |
| `DOCUTRUST_DATA_DIR` | `data` | Directory containing the SQLite database. |
| `MAX_UPLOAD_BYTES` | `15728640` (15 MiB) | Maximum accepted upload size in bytes. |
| `RETRIEVAL_THRESHOLD` | `0.12` | Minimum derived confidence for a `grounded` result. |

Example optional LLM configuration:

```dotenv
OPENAI_API_KEY=your_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
```

When the key is empty, the application remains fully usable: it returns a source-backed deterministic answer from the best evidence chunk rather than calling an LLM.

## Using the application

1. Start the server and open the root URL in a browser.
2. Upload one or more supported documents.
3. Confirm the indexed document list and chunk count.
4. Ask a specific, document-grounded question such as “Who approves leave requests?”
5. Read `answer_status` and `confidence` before relying on the answer.
6. Open the citations and verify the supporting quote against the original document and page.

For high-confidence results, write questions using terminology that appears in the source document. A lexical baseline does not understand synonyms as well as an embedding retriever.

## API reference

All JSON response schemas are also available interactively at `/docs` while the server runs.

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/` | Serves the web interface. |
| `GET` | `/health` | Returns service status, whether optional LLM synthesis is enabled, and indexed-document count. |
| `POST` | `/api/v1/documents` | Upload and index a document (`multipart/form-data`, field name: `file`). |
| `GET` | `/api/v1/documents` | List indexed documents and their chunk counts. |
| `DELETE` | `/api/v1/documents/{document_id}` | Delete a source document and all chunks derived from it. |
| `DELETE` | `/api/v1/documents` | Delete all indexed documents and chunks. |
| `POST` | `/api/v1/query` | Ask a question and receive an answer, status, confidence, citations, and audit event ID. |
| `GET` | `/api/v1/query-history` | Return recent query audit events; `limit` is clamped between 1 and 50. |
| `DELETE` | `/api/v1/query-history/{event_id}` | Delete one query-history event. |
| `GET` | `/api/v1/analytics` | Return document, chunk, query, confidence, and grounded-rate metrics. |

### Upload a document

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents \
  -F "file=@./leave-policy.pdf"
```

Example response:

```json
{
  "id": "3c2b0d86-0b3c-4a1b-bae5-2e9ad9d6bc92",
  "filename": "leave-policy.pdf",
  "media_type": "application/pdf",
  "uploaded_at": "2026-07-23T10:00:00+00:00",
  "page_count": 8,
  "extraction_method": "native_pdf",
  "chunk_count": 14
}
```

### Ask a question

```bash
curl -X POST http://127.0.0.1:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Who approves leave requests?"}'
```

To restrict retrieval to particular documents, provide `document_ids`:

```json
{
  "question": "What is the approval period?",
  "document_ids": ["3c2b0d86-0b3c-4a1b-bae5-2e9ad9d6bc92"]
}
```

Query responses use this shape:

```json
{
  "answer": "Most relevant information: Leave requests must be approved by the reporting manager within five working days.",
  "answer_status": "grounded",
  "confidence": 0.42,
  "citations": [
    {
      "chunk_id": "3c2b0d86-0b3c-4a1b-bae5-2e9ad9d6bc92:p2:c0",
      "document_id": "3c2b0d86-0b3c-4a1b-bae5-2e9ad9d6bc92",
      "document_name": "leave-policy.pdf",
      "page": 2,
      "section": null,
      "relevance_score": 0.0467,
      "supporting_quote": "Leave requests must be approved by the reporting manager within five working days."
    }
  ],
  "audit_event_id": "f85320cf-6099-4df9-a4d6-c2c3bddbdf38"
}
```

`answer_status` is one of:

- `grounded`: evidence exists and meets the configured confidence threshold.
- `insufficient_evidence`: no evidence was found or the best evidence did not meet the threshold. The answer text explains that the application cannot answer reliably.

### Inspect service state

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/documents
curl http://127.0.0.1:8000/api/v1/analytics
curl 'http://127.0.0.1:8000/api/v1/query-history?limit=8'
```

## Retrieval and answer flow

The baseline retriever is intentionally transparent and runs without downloading an embedding model or requiring a paid service.

### Chunking

Each extracted page is whitespace-normalized and split into chunks of 900 characters with 150 characters of overlap. The chunk ID encodes its source in this form:

```text
{document_id}:p{page_number}:c{chunk_number}
```

The metadata stored alongside each chunk enables citations to name the original document and page.

### Ranking

The retriever:

1. Extracts alphanumeric tokens of two or more characters.
2. Lowercases words, drops common stop words, and applies a small suffix-based normalizer.
3. Scores chunks using term frequency multiplied by a smoothed IDF-like value.
4. Returns up to five positive-score chunks in descending order.

This is a strong explainable baseline for a small document corpus. It is not semantic vector search; refer to [Future work](#future-work) for the intended upgrade path.

### Confidence and abstention

The application calculates `min(1.0, top_evidence_score × 9)`, rounded to two decimals. A result is `grounded` only when evidence exists and the confidence is at least `RETRIEVAL_THRESHOLD`.

This is a heuristic confidence value, not a calibrated probability. It should be evaluated and tuned against a labelled benchmark before operational use.

### Answer generation

Without an API key, the deterministic writer copies only from the best evidence chunk and provides focused excerpts. It includes special formatting for common invoice fields (invoice number, billing period, due date, and total) and date-range questions.

With an API key, the app sends retrieved sources to an OpenAI-compatible endpoint with instructions to use only those sources and to return `INSUFFICIENT_EVIDENCE` when unsupported. If that call fails, the API safely falls back to the deterministic response.

## Supported documents and OCR

| Extension | Extraction method | Notes |
| --- | --- | --- |
| `.pdf` | `native_pdf` | Works for PDFs with selectable/machine-readable text. Image-only scanned PDFs are not OCRed in the current version. |
| `.docx` | `native_docx` | Extracts non-empty paragraphs into one logical page. |
| `.txt`, `.md` | `plain_text` | UTF-8 decoding with replacement for invalid characters. |
| `.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp` | `tesseract_ocr` | Requires Python OCR packages and the locally installed Tesseract executable. |

If Tesseract is not on the system path, set `TESSERACT_CMD` in `.env`, for example:

```dotenv
TESSERACT_CMD=/usr/local/bin/tesseract
```

The application rejects files that produce no usable text. For scanned PDFs, add a PDF-to-image conversion/OCR stage as a future enhancement.

## Data model and persistence

The default database is `data/docutrust.db`. The `data/` directory is ignored by Git because it can contain user-upload-derived content.

| Table | Key data | Role |
| --- | --- | --- |
| `documents` | ID, filename, media type, upload time, page count, extraction method | Indexed-document catalogue. |
| `chunks` | ID, document ID, page number, section, text | Searchable evidence corpus. |
| `query_events` | ID, time, question, answer status, confidence, citation IDs | Persistent audit history. |

Deleting a document removes its chunks. Deleting all documents clears the `documents` and `chunks` tables. Query history is retained until deleted separately.

## Testing

Run the automated tests after installing dependencies:

```bash
pytest -q
```

or:

```bash
make test
```

The existing suite validates relevant evidence retrieval, abstention when there is no term overlap, numeric relevance scores, grounded date answers, focused source excerpts, and invoice-field extraction.

## Docker

Build the container:

```bash
docker build -t docutrust-ai .
```

Run it while persisting the database on the host:

```bash
mkdir -p data
docker run --rm -p 8000:8000 \
  -v "$(pwd)/data:/service/data" \
  --env-file .env \
  docutrust-ai
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

The supplied image includes Python OCR libraries but does **not** install the operating-system Tesseract binary. Native PDF, DOCX, TXT, and Markdown extraction works in the image; add Tesseract to the Dockerfile before relying on image OCR in a container.

## Security and limitations

### Current safeguards

- `.env` and `data/` are excluded from version control.
- Uploaded filenames are reduced to a safe character set and limited to 120 characters.
- Uploads are capped at 15 MiB by default.
- The API abstains below the evidence threshold rather than inventing an answer.
- API keys stay server-side in environment variables and are never sent to the frontend.
- Optional LLM failures do not interrupt the evidence-first query path.

### Before production use

This project is a demonstration and research baseline, not a production compliance system. It currently has no authentication, authorization, tenant isolation, malware scanning, rate limiting, encryption-at-rest configuration, background-job queue, document ACLs, or formal retention policy. Do not expose it publicly with sensitive documents until those controls are implemented.

Lexical matching can miss semantic matches and may rank a keyword match that lacks the desired context. Citations make verification possible, but they do not replace human review. The retrieval threshold is heuristic and must be validated with representative evaluation data.

## Project structure

```text
.
├── app/
│   ├── main.py                 # FastAPI routes, request/response flow
│   ├── config.py               # Environment-backed settings
│   ├── database.py             # SQLite schema and data access
│   ├── extraction.py           # PDF, DOCX, text, and image extraction
│   ├── retrieval.py            # Chunking, ranking, confidence, excerpts
│   ├── synthesis.py            # Optional OpenAI-compatible synthesis
│   ├── models.py               # Evidence and extracted-page models
│   └── static/                 # Browser UI assets
├── tests/
│   └── test_retrieval.py       # Retrieval and answer-format tests
├── scripts/
│   └── generate_docutrust_project_report.py
├── output/pdf/
│   └── DocuTrust_AI_Project_Explanation.pdf
├── .env.example                # Safe configuration template
├── Dockerfile                  # Container build definition
├── Makefile                    # install, start, and test commands
├── requirements.txt            # Python dependencies
└── start.sh                    # Convenience development launcher
```

The fuller project write-up is available at [output/pdf/DocuTrust_AI_Project_Explanation.pdf](output/pdf/DocuTrust_AI_Project_Explanation.pdf).

## Evaluation plan

For a final-year evaluation, curate 10–20 representative policy or business documents and a labelled set of 75–100 questions. Each question should identify the expected supporting passage or page and whether the correct behaviour is an answer or abstention.

| Metric | Definition | Suggested target |
| --- | --- | --- |
| Citation precision | Correctly supported cited passages / all cited passages | ≥ 0.90 |
| Retrieval recall@5 | Questions whose correct passage is in the five retrieved chunks | ≥ 0.85 |
| Answer faithfulness | Answers fully entailed by retrieved evidence | ≥ 0.85 |
| Abstention accuracy | Unsupported questions correctly marked `insufficient_evidence` | ≥ 0.90 |
| P95 latency | 95th-percentile end-to-end response time | Report locally and after deployment |

Compare the current lexical baseline with an embedding retriever and reranker using the same dataset. Report accuracy, latency, cost, error types, and examples where citations exposed incorrect retrieval.

## Suggested team responsibilities

1. **Document intelligence:** parsing, OCR quality, chunking strategy, and dataset curation.
2. **Retrieval and evaluation:** ranking experiments, benchmark design, citation precision, recall, and faithfulness evaluation.
3. **Backend and security:** API, database, audit logging, authentication, authorization, and deployment controls.
4. **Product and deployment:** interface design, usability testing, Docker/cloud deployment, report, and presentation.

## Future work

- Add embeddings, vector search, and a cross-encoder reranker; evaluate against the lexical baseline.
- Introduce layout-aware OCR, table extraction, and scanned-PDF OCR.
- Preserve document sections/headings and surface them in citations.
- Add RBAC, per-document ACLs, SSO, audit export, rate limiting, and data-retention controls.
- Add asynchronous ingestion for large documents and a production database.
- Add more tests for API routes, extraction failures, persistence, and end-to-end UI flows.
- Calibrate confidence with a labelled dataset instead of relying on a score heuristic.
- Add deployment configuration, observability, backups, and health monitoring.
- Conduct a usability study with intended users and an industry mentor.

## License

No license has been specified for this repository. Add a license file before distributing or reusing the code outside the project team.
