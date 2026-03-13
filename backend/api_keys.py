from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from auth_utils import get_current_user_id_jwt_only, get_current_user_id
from database import create_api_key, list_api_keys, revoke_api_key

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


class CreateKeyRequest(BaseModel):
    name: str


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_key(request: CreateKeyRequest, user_id: int = Depends(get_current_user_id_jwt_only)):
    """Create a new API key. Returns the full key ONCE."""
    if not request.name or not request.name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Key name is required"
        )

    # Limit number of active keys per user
    existing = list_api_keys(user_id)
    active_count = sum(1 for k in existing if k.get("is_active"))
    if active_count >= 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 10 active API keys per user"
        )

    result = create_api_key(user_id, request.name.strip())
    return result


@router.get("")
async def list_keys(user_id: int = Depends(get_current_user_id)):
    """List all API keys for the current user (never returns full key)."""
    keys = list_api_keys(user_id)
    return keys


@router.delete("/{key_id}")
async def revoke_key(key_id: int, user_id: int = Depends(get_current_user_id)):
    """Revoke an API key."""
    success = revoke_api_key(user_id, key_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    return {"success": True, "message": "API key revoked"}
