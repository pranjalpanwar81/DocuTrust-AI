import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, Response, UploadFile, Depends, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .config import settings
from .database import Database
from .extraction import ExtractionError, extract_pages, sanitize_filename
from .retrieval import chunk_pages, concise_answer, confidence, corrected_question, focused_excerpt, is_identity_question, retrieve
from .synthesis import SynthesisResult, synthesize
from .auth import (
    Token, UserCreate, UserLogin, get_password_hash, verify_password,
    create_access_token, authenticate_user, ACCESS_TOKEN_EXPIRE_MINUTES
)
from .dependencies import (
    get_database, get_current_user, get_current_active_user,
    require_admin, require_user_or_admin, get_optional_user, set_database
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="DocuTrust AI", version="0.1.0", description="Citation-grounded multimodal policy intelligence")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Initialize database and set global reference
database = Database(settings.data_dir / "docutrust.db")
set_database(database)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


class QueryRequest(BaseModel):
    question: str = Field(min_length=5, max_length=1000)
    document_ids: Optional[List[str]] = None


@app.get("/health")
@limiter.limit("60/minute")
def health(request: Request):
    return {"status": "ok", "llm_enabled": bool(settings.openai_api_key), "documents": len(database.list_documents())}


# Authentication endpoints
@app.post("/api/v1/auth/register", status_code=201)
@limiter.limit("5/minute")
async def register(request: Request, user_data: UserCreate):
    """Register a new user account."""
    # Check if user already exists
    if database.get_user(user_data.username):
        raise HTTPException(status_code=400, detail="Username already registered")
    
    # Hash password and create user
    hashed_password = get_password_hash(user_data.password)
    success = database.create_user(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password,
        role="user"
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    return {"message": "User registered successfully", "username": user_data.username}


@app.post("/api/v1/auth/login")
@limiter.limit("10/minute")
async def login(request: Request, user_data: UserLogin):
    """Authenticate user and return JWT token."""
    user_db = database.get_user(user_data.username)
    if not user_db:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    authenticated_user = authenticate_user(user_data.username, user_data.password, user_db)
    if not authenticated_user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": authenticated_user.username}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "username": authenticated_user.username,
            "email": authenticated_user.email,
            "role": authenticated_user.role
        }
    }


@app.get("/api/v1/auth/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information."""
    return {
        "username": current_user["username"],
        "email": current_user["email"],
        "role": current_user["role"],
        "disabled": current_user["disabled"]
    }


# User management endpoints (admin only)
@app.get("/api/v1/users")
async def list_users(current_user: dict = Depends(require_admin)):
    """List all users (admin only)."""
    return database.get_all_users()


@app.put("/api/v1/users/{username}/role")
async def update_user_role(username: str, new_role: str, current_user: dict = Depends(require_admin)):
    """Update user role (admin only)."""
    if new_role not in ["admin", "user", "viewer"]:
        raise HTTPException(status_code=400, detail="Invalid role. Must be admin, user, or viewer")
    
    success = database.update_user_role(username, new_role)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"message": f"User role updated to {new_role}"}


@app.put("/api/v1/users/{username}/disable")
async def disable_user_account(username: str, disabled: bool = True, current_user: dict = Depends(require_admin)):
    """Enable or disable user account (admin only)."""
    success = database.disable_user(username, disabled)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"message": f"User account {'disabled' if disabled else 'enabled'}"}


@app.post("/api/v1/documents", status_code=201)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(require_user_or_admin)
):
    """Upload and index a document (requires user or admin role)."""
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
    record = {
        "id": document_id,
        "filename": filename,
        "media_type": file.content_type or "application/octet-stream",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "page_count": len(pages),
        "extraction_method": extraction_method,
        "owner_username": current_user["username"],
        "is_public": 0
    }
    database.add_document(record, chunks)
    return {**record, "chunk_count": len(chunks)}


@app.get("/api/v1/documents")
async def list_documents(current_user: dict = Depends(get_current_user)):
    """List documents accessible to the current user."""
    return database.get_user_accessible_documents(current_user["username"], current_user["role"])


@app.delete("/api/v1/documents/{document_id}", status_code=204)
async def delete_document(document_id: str, current_user: dict = Depends(require_user_or_admin)):
    """Delete a document (requires user or admin role and document access)."""
    # Check if user has access to the document
    if not database.check_document_access(document_id, current_user["username"], current_user["role"]):
        raise HTTPException(403, "You do not have permission to delete this document.")
    
    if not database.delete_document(document_id):
        raise HTTPException(404, "Document not found.")
    return Response(status_code=204)


@app.delete("/api/v1/documents")
async def delete_all_documents(current_user: dict = Depends(require_admin)):
    """Delete all documents (admin only)."""
    return {"deleted_count": database.delete_all_documents()}


@app.get("/api/v1/analytics")
async def analytics(current_user: dict = Depends(get_current_user)):
    """Get analytics (requires authentication)."""
    return database.analytics()


@app.get("/api/v1/query-history")
async def query_history(limit: int = 8, current_user: dict = Depends(get_current_user)):
    """Get query history (requires authentication)."""
    return database.recent_query_events(max(1, min(limit, 50)))


@app.delete("/api/v1/query-history/{event_id}", status_code=204)
async def delete_query_history_event(event_id: str, current_user: dict = Depends(get_current_user)):
    """Delete query history event (requires authentication)."""
    if not database.delete_query_event(event_id):
        raise HTTPException(404, "Audit event not found.")
    return Response(status_code=204)


@app.post("/api/v1/query")
@limiter.limit("30/minute")
async def ask(request: Request, query_request: QueryRequest, current_user: dict = Depends(get_current_user)):
    """Ask a question with document access control (requires authentication)."""
    rows = database.all_chunks()
    
    # Filter chunks based on document access permissions
    if query_request.document_ids:
        # Check if user has access to all requested documents
        for doc_id in query_request.document_ids:
            if not database.check_document_access(doc_id, current_user["username"], current_user["role"]):
                raise HTTPException(403, f"You do not have access to document {doc_id}")
        rows = [row for row in rows if row["document_id"] in query_request.document_ids]
    else:
        # Filter to only accessible documents
        accessible_docs = database.get_user_accessible_documents(current_user["username"], current_user["role"])
        accessible_doc_ids = {doc["id"] for doc in accessible_docs}
        rows = [row for row in rows if row["document_id"] in accessible_doc_ids]
    
    interpreted_question, corrections = corrected_question(query_request.question, rows)
    evidence = retrieve(interpreted_question, rows)
    score = confidence(evidence)
    status = "grounded" if score >= settings.retrieval_threshold and evidence else "insufficient_evidence"
    # Identity fields are copied deterministically from the retrieved resume;
    # an LLM adds no value and can introduce avoidable provider failures.
    synthesis: SynthesisResult = (
        synthesize(interpreted_question, evidence)
        if status == "grounded" and not is_identity_question(interpreted_question, interpreted_question.split())
        else SynthesisResult(None, "fallback", None)
    )
    generated = synthesis.text
    answer = generated or (concise_answer(interpreted_question, evidence) if status == "grounded" else "I do not have enough supporting evidence in the indexed documents to answer this reliably.")
    if status == "grounded":
        answer_source = "llm" if synthesis.source == "llm" and generated else "deterministic"
    else:
        answer_source = "abstained"
    if synthesis.error and synthesis.source == "fallback" and status == "grounded":
        logger.info("Query used deterministic fallback after synthesis issue: %s", synthesis.error)
    event = {
        "id": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "question": query_request.question,
        "answer_status": status,
        "confidence": score,
        "citation_ids": [item.chunk_id for item in evidence],
        "username": current_user["username"]
    }
    database.add_query_event(event)
    return {
        "answer": answer,
        "answer_status": status,
        "answer_source": answer_source,
        "synthesis_error": synthesis.error,
        "confidence": score,
        "interpreted_question": interpreted_question,
        "corrections": corrections,
        "citations": [
            {
                "chunk_id": item.chunk_id,
                "document_id": item.document_id,
                "document_name": item.document_name,
                "page": item.page,
                "section": item.section,
                "relevance_score": round(item.score, 4),
                "supporting_quote": focused_excerpt(interpreted_question, item.text),
            }
            for item in evidence
        ],
        "audit_event_id": event["id"],
    }


@app.get("/", include_in_schema=False)
async def frontend(current_user: Optional[dict] = Depends(get_optional_user)):
    """Serve the frontend with optional authentication."""
    return FileResponse("app/static/index.html")


# Document permission endpoints
@app.post("/api/v1/documents/{document_id}/permissions", status_code=201)
async def grant_document_permission(
    document_id: str,
    username: str,
    permission_level: str = "read",
    current_user: dict = Depends(require_user_or_admin)
):
    """Grant permission to a user for a document (requires user or admin role)."""
    # Check if user has access to the document
    if not database.check_document_access(document_id, current_user["username"], current_user["role"]):
        raise HTTPException(403, "You do not have permission to grant access to this document.")
    
    if permission_level not in ["read", "write", "admin"]:
        raise HTTPException(400, "Invalid permission level. Must be read, write, or admin")
    
    success = database.grant_document_permission(document_id, username, permission_level)
    if not success:
        raise HTTPException(400, "Permission already exists or user not found")
    
    return {"message": f"Permission granted to {username} with level {permission_level}"}


@app.delete("/api/v1/documents/{document_id}/permissions/{username}")
async def revoke_document_permission(
    document_id: str,
    username: str,
    current_user: dict = Depends(require_user_or_admin)
):
    """Revoke permission from a user for a document (requires user or admin role)."""
    # Check if user has access to the document
    if not database.check_document_access(document_id, current_user["username"], current_user["role"]):
        raise HTTPException(403, "You do not have permission to revoke access to this document.")
    
    success = database.revoke_document_permission(document_id, username)
    if not success:
        raise HTTPException(404, "Permission not found")
    
    return {"message": f"Permission revoked from {username}"}
