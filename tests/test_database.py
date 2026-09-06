from pathlib import Path

from app.database import Database


def make_database(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db")


def document_record() -> dict:
    return {
        "id": "doc-1",
        "filename": "policy.txt",
        "media_type": "text/plain",
        "uploaded_at": "2026-09-06T00:00:00+00:00",
        "page_count": 1,
        "extraction_method": "plain_text",
        "owner_username": "owner",
        "is_public": 0,
    }


def test_add_document_inserts_chunks_and_returns_rows(tmp_path):
    database = make_database(tmp_path)
    database.add_document(
        document_record(),
        [{"id": "chunk-1", "document_id": "doc-1", "page_number": 1, "section": None, "text": "Policy text"}],
    )

    documents = database.list_documents()
    chunks = database.all_chunks()

    assert documents[0]["id"] == "doc-1"
    assert documents[0]["chunk_count"] == 1
    assert chunks[0]["text"] == "Policy text"


def test_delete_document_removes_dependent_permissions(tmp_path):
    database = make_database(tmp_path)
    database.create_user("owner", "owner@example.com", "hash")
    database.create_user("reader", "reader@example.com", "hash")
    database.add_document(document_record(), [])
    assert database.grant_document_permission("doc-1", "reader") is True

    assert database.delete_document("doc-1") is True
    assert database.list_documents() == []
