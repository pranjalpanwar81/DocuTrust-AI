from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

# Load local secrets before Settings is created. `.env` is ignored by Git and
# must never be placed in frontend code or committed to a repository.
load_dotenv()
from typing import Optional


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("DOCUTRUST_DATA_DIR", "data"))
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", 15 * 1024 * 1024))
    retrieval_threshold: float = float(os.getenv("RETRIEVAL_THRESHOLD", "0.12"))
    openai_api_key: Optional[str] = (os.getenv("OPENAI_API_KEY") or "").strip() or None
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    # JWT Authentication settings
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-this-in-production")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    # Database settings for production
    database_url: Optional[str] = os.getenv("DATABASE_URL")  # For PostgreSQL on Render
    admin_username: Optional[str] = (os.getenv("ADMIN_USERNAME") or "").strip() or None
    admin_email: Optional[str] = (os.getenv("ADMIN_EMAIL") or "").strip() or None
    admin_password: Optional[str] = os.getenv("ADMIN_PASSWORD") or None


settings = Settings()
