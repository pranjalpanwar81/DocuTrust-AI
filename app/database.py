import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
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
    document_id TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    section TEXT,
    text TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE TABLE IF NOT EXISTS document_permissions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    username TEXT NOT NULL,
    permission_level TEXT NOT NULL,
    granted_at TEXT NOT NULL,
    UNIQUE(document_id, username),
    FOREIGN KEY (document_id) REFERENCES documents(id),
    FOREIGN KEY (username) REFERENCES users(username)
);
CREATE TABLE IF NOT EXISTS query_events (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    question TEXT NOT NULL,
    answer_status TEXT NOT NULL,
    confidence REAL NOT NULL,
    citation_ids TEXT NOT NULL,
    username TEXT,
    FOREIGN KEY (username) REFERENCES users(username)
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def add_document(self, record: dict, chunks: list[dict]) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO documents (id, filename, media_type, uploaded_at, page_count, extraction_method, owner_username, is_public) VALUES (:id, :filename, :media_type, :uploaded_at, :page_count, :extraction_method, :owner_username, :is_public)",
                record,
            )
            connection.executemany(
                "INSERT INTO chunks VALUES (:id, :document_id, :page_number, :section, :text)", chunks,
            )

    def list_documents(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT d.*, COUNT(c.id) AS chunk_count FROM documents d "
                "LEFT JOIN chunks c ON c.document_id = d.id "
                "GROUP BY d.id ORDER BY d.uploaded_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def all_chunks(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT c.*, d.filename FROM chunks c JOIN documents d ON c.document_id = d.id"
            ).fetchall()
        return [dict(row) for row in rows]

    def add_query_event(self, record: dict) -> None:
        record["citation_ids"] = json.dumps(record["citation_ids"])
        with self.connect() as connection:
            connection.execute("INSERT INTO query_events VALUES (:id, :created_at, :question, :answer_status, :confidence, :citation_ids)", record)

    def delete_document(self, document_id: str) -> bool:
        """Delete one source document and every searchable chunk derived from it."""
        with self.connect() as connection:
            if not connection.execute("SELECT 1 FROM documents WHERE id = ?", (document_id,)).fetchone():
                return False
            connection.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        return True

    def delete_all_documents(self) -> int:
        with self.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            connection.execute("DELETE FROM chunks")
            connection.execute("DELETE FROM documents")
        return count

    def recent_query_events(self, limit: int = 8) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM query_events ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        events = [dict(row) for row in rows]
        for event in events:
            event["citation_ids"] = json.loads(event["citation_ids"])
        return events

    def delete_query_event(self, event_id: str) -> bool:
        with self.connect() as connection:
            result = connection.execute("DELETE FROM query_events WHERE id = ?", (event_id,))
        return result.rowcount > 0

    def analytics(self) -> dict:
        with self.connect() as connection:
            document_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunk_count = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            query_count, average_confidence, grounded_count = connection.execute(
                "SELECT COUNT(*), AVG(confidence), COALESCE(SUM(answer_status = 'grounded'), 0) FROM query_events"
            ).fetchone()
        return {
            "document_count": document_count,
            "chunk_count": chunk_count,
            "query_count": query_count,
            "average_confidence": round(average_confidence or 0, 2),
            "grounded_rate": round((grounded_count / query_count) if query_count else 0, 2),
        }

    def create_user(self, username: str, email: str, hashed_password: str, role: str = "user") -> bool:
        """Create a new user account."""
        try:
            with self.connect() as connection:
                connection.execute(
                    "INSERT INTO users (username, email, hashed_password, role, created_at) VALUES (?, ?, ?, ?, ?)",
                    (username, email, hashed_password, role, datetime.now(timezone.utc).isoformat())
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def get_user(self, username: str) -> dict:
        """Get user by username."""
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None

    def get_all_users(self) -> list[dict]:
        """Get all users."""
        with self.connect() as connection:
            rows = connection.execute("SELECT username, email, role, disabled, created_at FROM users").fetchall()
        return [dict(row) for row in rows]

    def update_user_role(self, username: str, new_role: str) -> bool:
        """Update user role."""
        with self.connect() as connection:
            result = connection.execute("UPDATE users SET role = ? WHERE username = ?", (new_role, username))
        return result.rowcount > 0

    def disable_user(self, username: str, disabled: bool = True) -> bool:
        """Enable or disable a user account."""
        with self.connect() as connection:
            result = connection.execute("UPDATE users SET disabled = ? WHERE username = ?", (1 if disabled else 0, username))
        return result.rowcount > 0

    def grant_document_permission(self, document_id: str, username: str, permission_level: str = "read") -> bool:
        """Grant permission to a user for a specific document."""
        from uuid import uuid4
        try:
            with self.connect() as connection:
                connection.execute(
                    "INSERT INTO document_permissions (id, document_id, username, permission_level, granted_at) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid4()), document_id, username, permission_level, datetime.now(timezone.utc).isoformat())
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def revoke_document_permission(self, document_id: str, username: str) -> bool:
        """Revoke permission from a user for a specific document."""
        with self.connect() as connection:
            result = connection.execute(
                "DELETE FROM document_permissions WHERE document_id = ? AND username = ?",
                (document_id, username)
            )
        return result.rowcount > 0

    def get_user_accessible_documents(self, username: str, user_role: str) -> list[dict]:
        """Get documents accessible to a user based on role and permissions."""
        with self.connect() as connection:
            if user_role == "admin":
                # Admins can see all documents
                rows = connection.execute("SELECT d.*, COUNT(c.id) AS chunk_count FROM documents d LEFT JOIN chunks c ON c.document_id = d.id GROUP BY d.id ORDER BY d.uploaded_at DESC").fetchall()
            else:
                # Regular users can see their own documents, public documents, and documents they have permission for
                rows = connection.execute(
                    """SELECT d.*, COUNT(c.id) AS chunk_count FROM documents d 
                    LEFT JOIN chunks c ON c.document_id = d.id
                    WHERE d.owner_username = ? OR d.is_public = 1 OR d.id IN (
                        SELECT document_id FROM document_permissions WHERE username = ?
                    ) GROUP BY d.id ORDER BY d.uploaded_at DESC""",
                    (username, username)
                ).fetchall()
        return [dict(row) for row in rows]

    def check_document_access(self, document_id: str, username: str, user_role: str) -> bool:
        """Check if a user has access to a specific document."""
        if user_role == "admin":
            return True
        with self.connect() as connection:
            row = connection.execute(
                """SELECT 1 FROM documents d 
                WHERE d.id = ? AND (d.owner_username = ? OR d.is_public = 1 OR d.id IN (
                    SELECT document_id FROM document_permissions WHERE username = ?
                ))""",
                (document_id, username, username)
            ).fetchone()
        return row is not None
