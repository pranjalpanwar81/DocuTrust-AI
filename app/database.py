import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    media_type TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    extraction_method TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    page_number INTEGER NOT NULL,
    section TEXT,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE TABLE IF NOT EXISTS query_events (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    question TEXT NOT NULL,
    answer_status TEXT NOT NULL,
    confidence REAL NOT NULL,
    citation_ids TEXT NOT NULL
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
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def add_document(self, record: dict, chunks: list[dict]) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO documents VALUES (:id, :filename, :media_type, :uploaded_at, :page_count, :extraction_method)",
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
