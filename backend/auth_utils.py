import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": int(expire.timestamp())})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT access token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def _extract_user_id_from_jwt(token: str) -> Optional[int]:
    """Extract user_id from a JWT token. Returns None if invalid."""
    payload = decode_access_token(token)
    if payload is None:
        return None
    user_id_str = payload.get("sub")
    if user_id_str is None:
        return None
    try:
        return int(user_id_str)
    except (ValueError, TypeError):
        return None


async def get_current_user_id(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> int:
    """
    Dependency to get the current authenticated user ID.
    Tries Bearer JWT first, then falls back to X-API-Key header.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Try Bearer JWT token
    if credentials and credentials.credentials:
        user_id = _extract_user_id_from_jwt(credentials.credentials)
        if user_id is not None:
            return user_id

    # 2. Try X-API-Key header
    api_key = request.headers.get("X-API-Key")
    if api_key:
        from database import validate_api_key
        user_id = validate_api_key(api_key)
        if user_id is not None:
            return user_id

    raise credentials_exception


async def get_current_user_id_jwt_only(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
) -> int:
    """
    Dependency that ONLY accepts JWT Bearer tokens.
    Used for endpoints that should not accept API keys (e.g., creating API keys).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials
    user_id = _extract_user_id_from_jwt(token)
    if user_id is None:
        raise credentials_exception
    return user_id


async def get_optional_user_id(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[int]:
    """
    Dependency to optionally get the current authenticated user ID.
    Returns None if no valid token is provided.
    Checks Bearer JWT first, then X-API-Key header.
    """
    # 1. Try Bearer JWT token
    if credentials and credentials.credentials:
        user_id = _extract_user_id_from_jwt(credentials.credentials)
        if user_id is not None:
            return user_id

    # 2. Try X-API-Key header
    api_key = request.headers.get("X-API-Key")
    if api_key:
        from database import validate_api_key
        user_id = validate_api_key(api_key)
        if user_id is not None:
            return user_id

    return None
