import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app, limiter
from app.database import Database
from app.auth import get_password_hash, verify_password, create_access_token, decode_access_token
from app.synthesis import SynthesisResult
from pathlib import Path
import tempfile
import os


@pytest.fixture
def test_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        yield db


@pytest.fixture
def test_client(test_db):
    """Create a test client with test database."""
    limiter._storage.reset()
    import app.main as main
    from app.dependencies import set_database
    main.database = test_db
    set_database(test_db)
    
    with TestClient(app) as client:
        yield client


def test_password_hashing():
    """Test password hashing and verification."""
    password = "test_password_123"
    hashed = get_password_hash(password)
    
    # Verify hash is different from original
    assert hashed != password
    
    # Verify correct password validates
    assert verify_password(password, hashed) is True
    
    # Verify incorrect password fails
    assert verify_password("wrong_password", hashed) is False


def test_jwt_token_creation_and_decoding():
    """Test JWT token creation and decoding."""
    username = "testuser"
    token = create_access_token(data={"sub": username})
    
    # Verify token is a string
    assert isinstance(token, str)
    
    # Verify token can be decoded
    token_data = decode_access_token(token)
    assert token_data is not None
    assert token_data.username == username


def test_jwt_token_decoding_invalid():
    """Test JWT token decoding with invalid token."""
    invalid_token = "invalid.token.here"
    token_data = decode_access_token(invalid_token)
    assert token_data is None


def test_user_registration(test_client):
    """Test user registration endpoint."""
    response = test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpass123",
            "role": "user"
        }
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "testuser"
    assert "message" in data


def test_public_registration_cannot_create_admin(test_client):
    """Public registration must never grant administrative privileges."""
    response = test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "attacker",
            "email": "attacker@example.com",
            "password": "testpass123",
            "role": "admin",
        },
    )

    assert response.status_code == 201
    login_response = test_client.post(
        "/api/v1/auth/login",
        json={"username": "attacker", "password": "testpass123"},
    )
    token = login_response.json()["access_token"]
    me_response = test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert me_response.json()["role"] == "user"


def test_user_registration_duplicate_username(test_client):
    """Test user registration with duplicate username."""
    # Register first user
    test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test1@example.com",
            "password": "testpass123",
            "role": "user"
        }
    )
    
    # Try to register with same username
    response = test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test2@example.com",
            "password": "testpass123",
            "role": "user"
        }
    )
    
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]


def test_user_registration_duplicate_email(test_client):
    """Test user registration with duplicate email."""
    # Register first user
    test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser1",
            "email": "test@example.com",
            "password": "testpass123",
            "role": "user"
        }
    )
    
    # Try to register with same email
    response = test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser2",
            "email": "test@example.com",
            "password": "testpass123",
            "role": "user"
        }
    )
    
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]


def test_user_login_success(test_client):
    """Test successful user login."""
    # Register user first
    test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpass123",
            "role": "user"
        }
    )
    
    # Login
    response = test_client.post(
        "/api/v1/auth/login",
        json={
            "username": "testuser",
            "password": "testpass123"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == "testuser"


def test_user_login_invalid_credentials(test_client):
    """Test login with invalid credentials."""
    # Register user first
    test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpass123",
            "role": "user"
        }
    )
    
    # Login with wrong password
    response = test_client.post(
        "/api/v1/auth/login",
        json={
            "username": "testuser",
            "password": "wrongpassword"
        }
    )
    
    assert response.status_code == 401
    assert "Invalid username or password" in response.json()["detail"]


def test_user_login_nonexistent_user(test_client):
    """Test login with non-existent user."""
    response = test_client.post(
        "/api/v1/auth/login",
        json={
            "username": "nonexistent",
            "password": "testpass123"
        }
    )
    
    assert response.status_code == 401
    assert "Invalid username or password" in response.json()["detail"]


def test_protected_endpoint_without_token(test_client):
    """Test accessing protected endpoint without authentication."""
    response = test_client.get("/api/v1/auth/me")
    
    assert response.status_code == 401


def test_protected_endpoint_with_valid_token(test_client):
    """Test accessing protected endpoint with valid token."""
    # Register and login
    test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpass123",
            "role": "user"
        }
    )
    
    login_response = test_client.post(
        "/api/v1/auth/login",
        json={
            "username": "testuser",
            "password": "testpass123"
        }
    )
    token = login_response.json()["access_token"]
    
    # Access protected endpoint
    response = test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"


def test_admin_endpoint_without_admin_role(test_client):
    """Test accessing admin endpoint without admin role."""
    # Register regular user
    test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpass123",
            "role": "user"
        }
    )
    
    login_response = test_client.post(
        "/api/v1/auth/login",
        json={
            "username": "testuser",
            "password": "testpass123"
        }
    )
    token = login_response.json()["access_token"]
    
    # Try to access admin endpoint
    response = test_client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 403
    assert "Admin privileges required" in response.json()["detail"]


def test_admin_endpoint_with_admin_role(test_client):
    """Test accessing admin endpoint with admin role."""
    from app.dependencies import get_database
    get_database().create_user(
        username="adminuser",
        email="admin@example.com",
        hashed_password=get_password_hash("adminpass123"),
        role="admin",
    )
    
    login_response = test_client.post(
        "/api/v1/auth/login",
        json={
            "username": "adminuser",
            "password": "adminpass123"
        }
    )
    token = login_response.json()["access_token"]
    
    # Access admin endpoint
    response = test_client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_rate_limiting(test_client):
    """Test rate limiting on login endpoint."""
    # Make multiple login attempts to trigger rate limiting
    for i in range(15):  # Exceed the 10/minute limit
        response = test_client.post(
            "/api/v1/auth/login",
            json={
                "username": "testuser",
                "password": "wrongpassword"
            }
        )
        
        # After exceeding limit, should get rate limited
        if i >= 10:
            assert response.status_code == 429


def test_document_upload_requires_auth(test_client):
    """Test that document upload requires authentication."""
    # Try to upload without authentication
    response = test_client.post(
        "/api/v1/documents",
        files={"file": ("test.txt", b"test content", "text/plain")}
    )
    
    assert response.status_code == 401


def test_document_upload_with_auth(test_client):
    """Test document upload with authentication."""
    # Register and login
    test_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpass123",
            "role": "user"
        }
    )
    
    login_response = test_client.post(
        "/api/v1/auth/login",
        json={
            "username": "testuser",
            "password": "testpass123"
        }
    )
    token = login_response.json()["access_token"]
    
    # Upload document with authentication
    response = test_client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("test.txt", b"test content", "text/plain")}
    )
    
    assert response.status_code == 201


def test_query_endpoint_returns_grounded_answer(test_client):
    """The rate-limited query endpoint must receive and handle the request object."""
    from app.dependencies import get_database

    test_client.post(
        "/api/v1/auth/register",
        json={"username": "queryuser", "email": "query@example.com", "password": "testpass123"},
    )
    login_response = test_client.post(
        "/api/v1/auth/login",
        json={"username": "queryuser", "password": "testpass123"},
    )
    token = login_response.json()["access_token"]
    get_database().add_document(
        {
            "id": "query-doc",
            "filename": "resume.txt",
            "media_type": "text/plain",
            "uploaded_at": "2026-09-06T00:00:00+00:00",
            "page_count": 1,
            "extraction_method": "plain_text",
            "owner_username": "queryuser",
            "is_public": 0,
        },
        [{"id": "query-chunk", "document_id": "query-doc", "page_number": 1, "section": None, "text": "Student Name: Priya Sharma"}],
    )

    with patch("app.main.synthesize", return_value=SynthesisResult(None, "fallback", "api_key_missing")):
        response = test_client.post(
            "/api/v1/query",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "What is the student name?"},
        )

    assert response.status_code == 200
    assert response.json()["answer_status"] == "grounded"
    assert "Priya Sharma" in response.json()["answer"]
