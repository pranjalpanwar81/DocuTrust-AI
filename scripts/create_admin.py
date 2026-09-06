import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import get_password_hash
from app.config import settings
from app.database import Database


def main() -> None:
    username = os.environ.get("ADMIN_USERNAME")
    email = os.environ.get("ADMIN_EMAIL")
    password = os.environ.get("ADMIN_PASSWORD")
    if not all((username, email, password)):
        raise SystemExit("Set ADMIN_USERNAME, ADMIN_EMAIL, and ADMIN_PASSWORD before running this script.")

    database = Database(settings.data_dir / "docutrust.db")
    if database.get_user(username):
        raise SystemExit(f"User already exists: {username}")
    if not database.create_user(username, email, get_password_hash(password), role="admin"):
        raise SystemExit("Could not create the admin user; username or email may already exist.")
    print(f"Created admin user: {username}")


if __name__ == "__main__":
    main()