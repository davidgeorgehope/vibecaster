"""
Admin API endpoints for Vibecaster.
Only accessible to users with is_admin=1 in the database.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from auth_utils import get_current_user_id
from database import (
    is_user_admin,
    get_all_users,
    get_all_campaigns,
    get_all_posts,
    get_admin_stats,
    get_connection_status
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def require_admin(user_id: int = Depends(get_current_user_id)) -> int:
    """Dependency that checks if the current user is an admin."""
    if not is_user_admin(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user_id


@router.get("/stats")
async def admin_stats(user_id: int = Depends(require_admin)):
    """Get admin dashboard statistics."""
    return get_admin_stats()


@router.get("/users")
async def admin_users(user_id: int = Depends(require_admin)):
    """Get all users."""
    users = get_all_users()
    # Add connection status for each user
    for user in users:
        user["connections"] = get_connection_status(user["id"])
    return {"users": users}


@router.get("/campaigns")
async def admin_campaigns(user_id: int = Depends(require_admin)):
    """Get all campaigns."""
    return {"campaigns": get_all_campaigns()}


@router.get("/posts")
async def admin_posts(limit: int = 50, user_id: int = Depends(require_admin)):
    """Get recent posts across all users."""
    return {"posts": get_all_posts(limit)}
