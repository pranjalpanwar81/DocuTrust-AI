import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import settings
from .database import Database
from .extraction import ExtractionError, extract_pages, sanitize_filename
from .retrieval import chunk_pages, concise_answer, confidence, focused_excerpt, retrieve
from .synthesis import synthesize

database = Database(settings.data_dir / "docutrust.db")
app = FastAPI(title="DocuTrust AI", version="0.1.0", description="Citation-grounded multimodal policy intelligence")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


class QueryRequest(BaseModel):
    question: str = Field(min_length=5, max_length=1000)
    document_ids: Optional[List[str]] = None


@app.get("/health")
def health():
    return {"status": "ok", "llm_enabled": bool(settings.openai_api_key), "documents": len(database.list_documents())}


@app.post("/api/v1/documents", status_code=201)
async def upload_document(file: UploadFile = File(...)):
    filename = sanitize_filename(file.filename or "upload")
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "File exceeds the configured upload-size limit.")
    try:
        pages, extraction_method = extract_pages(filename, data)
    except ExtractionError as error:
        raise HTTPException(422, str(error)) from error
    document_id = str(uuid4())
    chunks = chunk_pages(document_id, pages)
    if not chunks:
        raise HTTPException(422, "The document did not produce usable chunks.")
    record = {"id": document_id, "filename": filename, "media_type": file.content_type or "application/octet-stream", "uploaded_at": datetime.now(timezone.utc).isoformat(), "page_count": len(pages), "extraction_method": extraction_method}
    database.add_document(record, chunks)
    return {**record, "chunk_count": len(chunks)}


@app.get("/api/v1/documents")
def list_documents():
    return database.list_documents()


@app.delete("/api/v1/documents/{document_id}", status_code=204)
def delete_document(document_id: str):
    if not database.delete_document(document_id):
        raise HTTPException(404, "Document not found.")
    return Response(status_code=204)


@app.delete("/api/v1/documents")
def delete_all_documents():
    return {"deleted_count": database.delete_all_documents()}


@app.get("/api/v1/analytics")
def analytics():
    return database.analytics()


@app.get("/api/v1/query-history")
def query_history(limit: int = 8):
    return database.recent_query_events(max(1, min(limit, 50)))


@app.delete("/api/v1/query-history/{event_id}", status_code=204)
def delete_query_history_event(event_id: str):
    if not database.delete_query_event(event_id):
        raise HTTPException(404, "Audit event not found.")
    return Response(status_code=204)


@app.post("/api/v1/query")
def ask(request: QueryRequest):
    rows = database.all_chunks()
    if request.document_ids:
        rows = [row for row in rows if row["document_id"] in request.document_ids]
    evidence = retrieve(request.question, rows)
    score = confidence(evidence)
    status = "grounded" if score >= settings.retrieval_threshold and evidence else "insufficient_evidence"
    generated = synthesize(request.question, evidence) if status == "grounded" else None
    answer = generated or (concise_answer(request.question, evidence) if status == "grounded" else "I do not have enough supporting evidence in the indexed documents to answer this reliably.")
    event = {"id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat(), "question": request.question, "answer_status": status, "confidence": score, "citation_ids": [item.chunk_id for item in evidence]}
    database.add_query_event(event)
    return {"answer": answer, "answer_status": status, "confidence": score, "citations": [{"chunk_id": item.chunk_id, "document_id": item.document_id, "document_name": item.document_name, "page": item.page, "section": item.section, "relevance_score": round(item.score, 4), "supporting_quote": focused_excerpt(request.question, item.text)} for item in evidence], "audit_event_id": event["id"]}


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse("app/static/index.html")
