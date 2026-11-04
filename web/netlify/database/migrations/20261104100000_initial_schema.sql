-- DocuTrust AI schema (ported from app/database.py).
-- Timestamps stay ISO-8601 text so ordering and API output match the
-- original backend exactly.

CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    disabled INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    media_type TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    extraction_method TEXT NOT NULL,
    owner_username TEXT NOT NULL DEFAULT 'admin',
    is_public INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    page_number INTEGER NOT NULL,
    section TEXT,
    text TEXT NOT NULL,
    -- Preserves insertion order (SQLite rowid in the original) for stable ranking.
    seq BIGSERIAL
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);

CREATE TABLE IF NOT EXISTS document_permissions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    username TEXT NOT NULL REFERENCES users(username),
    permission_level TEXT NOT NULL,
    granted_at TEXT NOT NULL,
    UNIQUE (document_id, username)
);

CREATE TABLE IF NOT EXISTS query_events (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    question TEXT NOT NULL,
    answer_status TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    citation_ids TEXT NOT NULL,
    username TEXT REFERENCES users(username)
);

-- Server-side settings. Holds the JWT signing secret, generated on first use,
-- unless JWT_SECRET_KEY is set as an environment variable.
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
