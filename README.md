# DocuTrust AI

DocuTrust AI is a citation-grounded, multimodal Retrieval-Augmented Generation (RAG) service for internal policies, SOPs, contracts, and compliance documents. It prioritizes **verifiable answers over fluent guesses**: every answer includes evidence chunks with document, page, section, and quoted passage.

## Placement-level differentiators

- **Grounded answer contract:** a query is answered only from retrieved evidence; otherwise the API returns `insufficient_evidence`.
- **Traceable citations:** citations retain source document, page, section, chunk ID, relevance score, and supporting quote.
- **Multimodal ingestion:** PDF, DOCX, TXT, and image ingestion. Image OCR uses the local Tesseract binary; native PDF/DOCX text always works.
- **Persistent audit trail:** SQLite stores documents, chunks, query events, answer status, confidence, and citations.
- **No paid service required:** the baseline uses transparent lexical retrieval. An OpenAI-compatible LLM can be enabled for synthesis through environment variables.
- **Security-first defaults:** filename sanitization, upload-size limits, no source document content exposed in logs, and explicit low-confidence fallback.

## Architecture

```text
Upload -> Extract (PDF/DOCX/TXT/OCR) -> Chunk + metadata -> SQLite
Question -> Hybrid lexical retrieval -> evidence threshold -> LLM synthesis (optional)
         -> citation validation -> answer + audit event
```

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for an interactive API console.

For image uploads, install Tesseract locally and set `TESSERACT_CMD` when it is not on your PATH. For scanned PDFs, add a PDF-to-image OCR stage as the next iteration; the API already returns a clear error instead of indexing blank scans.

Quick single-command start
------------------------

A convenience launcher is provided to create the venv, install dependencies, copy `.env.example` → `.env` and start the dev server in one step:

```bash
./start.sh
```

Or using `make`:

```bash
make start
```

## API workflow

1. `POST /api/v1/documents` with multipart field `file`.
2. `GET /api/v1/documents` to view indexed source documents.
3. `POST /api/v1/query` with `{ "question": "What is the approval period?" }`.
4. Inspect `answer_status`, `confidence`, and `citations`. Treat only citations as evidence.

## Suggested evaluation for the final-year report

Create a 75–100 question benchmark from 10–20 policy documents and measure:

| Metric | Definition | Target |
|---|---|---|
| Citation precision | cited passages that truly support the answer / all cited passages | >= 0.90 |
| Retrieval recall@5 | questions where correct passage appears in top 5 | >= 0.85 |
| Faithfulness | answers fully entailed by retrieved evidence | >= 0.85 |
| Abstention accuracy | unsupported questions correctly marked insufficient | >= 0.90 |
| P95 latency | 95th percentile API response time | report locally and after deployment |

## Team split (four members)

1. Document intelligence: parsers, OCR, chunking, dataset curation.
2. Retrieval and evaluation: ranking, benchmarks, citation/faithfulness scoring.
3. Backend and security: API, database, audit logs, authentication upgrade.
4. Product and deployment: dashboard, Docker/cloud deployment, usability study, report/paper.

## High-value next upgrades

- Add RBAC and per-document ACLs.
- Replace lexical retrieval with embeddings + a cross-encoder reranker, then compare metrics.
- Add table extraction and layout-aware OCR.
- Add a React dashboard and visual evidence viewer.
- Deploy Dockerized API and perform a small end-user study with an industry mentor.
