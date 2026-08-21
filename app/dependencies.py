from typing import Annotated, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.auth import decode_access_token, TokenData
from app.database import Database


# Global database instance (will be set in main.py)
_database: Optional[Database] = None


def set_database(database: Database) -> None:
    """Set the global database instance."""
    global _database
    _database = database


def get_database() -> Database:
    """Get the global database instance."""
    global _database
    if _database is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database not initialized"
        )
    return _database


security = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    database: Database = Depends(get_database)
) -> dict:
    """Dependency to get the current authenticated user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = credentials.credentials
    token_data = decode_access_token(token)
    
    if token_data is None:
        raise credentials_exception
    
    user = database.get_user(token_data.username)
    if user is None:
        raise credentials_exception
    
    if user.get("disabled"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )
    
    return user


async def get_current_active_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Dependency to get the current active user."""
    if current_user.get("disabled"):
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def require_admin(
    current_user: dict = Depends(get_current_active_user)
) -> dict:
    """Dependency to require admin role."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user


async def require_user_or_admin(
    current_user: dict = Depends(get_current_active_user)
) -> dict:
    """Dependency to require user or admin role (excludes viewers)."""
    if current_user.get("role") not in ["admin", "user"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User privileges required"
        )
    return current_user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    database: Database = Depends(get_database)
) -> Optional[dict]:
    """Optional dependency to get current user if token is provided."""
    if credentials is None:
        return None
    
    token = credentials.credentials
    token_data = decode_access_token(token)
    
    if token_data is None:
        return None
    
    user = database.get_user(token_data.username)
    if user is None or user.get("disabled"):
        return None
    
    return user
