"""
Admin API endpoints for Vibecaster.
Only accessible to users with is_admin=1 in the database.
"""

import re
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, field_validator
from auth_utils import get_current_user_id
from database import (
    is_user_admin,
    get_all_users,
    get_all_campaigns,
    get_all_posts,
    get_admin_stats,
    get_connection_status,
    create_linkedin_mention,
    update_linkedin_mention,
    delete_linkedin_mention,
    get_linkedin_mention,
    get_all_linkedin_mentions
)


# Pydantic models for LinkedIn mentions
class LinkedInMentionCreate(BaseModel):
    company_name: str
    organization_urn: str
    aliases: Optional[List[str]] = None

    @field_validator('organization_urn')
    @classmethod
    def validate_urn(cls, v):
        if not re.match(r'^urn:li:organization:\d+$', v):
            raise ValueError('URN must be in format: urn:li:organization:XXXXX')
        return v

    @field_validator('company_name')
    @classmethod
    def validate_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Company name cannot be empty')
        return v.strip()


class LinkedInMentionUpdate(BaseModel):
    company_name: Optional[str] = None
    organization_urn: Optional[str] = None
    aliases: Optional[List[str]] = None
    is_active: Optional[bool] = None

    @field_validator('organization_urn')
    @classmethod
    def validate_urn(cls, v):
        if v is not None and not re.match(r'^urn:li:organization:\d+$', v):
            raise ValueError('URN must be in format: urn:li:organization:XXXXX')
        return v

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
async def admin_users(page: int = 1, per_page: int = 20, user_id: int = Depends(require_admin)):
    """Get paginated users."""
    result = get_all_users(page, per_page)
    # Add connection status for each user
    for user in result["items"]:
        user["connections"] = get_connection_status(user["id"])
    return result


@router.get("/campaigns")
async def admin_campaigns(page: int = 1, per_page: int = 20, user_id: int = Depends(require_admin)):
    """Get paginated campaigns."""
    return get_all_campaigns(page, per_page)


@router.get("/posts")
async def admin_posts(page: int = 1, per_page: int = 20, user_id: int = Depends(require_admin)):
    """Get paginated posts across all users."""
    return get_all_posts(page, per_page)


# ===== LINKEDIN MENTIONS ENDPOINTS =====

@router.get("/mentions")
async def get_mentions(include_inactive: bool = False, user_id: int = Depends(require_admin)):
    """Get all LinkedIn company mentions."""
    return get_all_linkedin_mentions(include_inactive=include_inactive)


@router.post("/mentions")
async def create_mention(request: LinkedInMentionCreate, user_id: int = Depends(require_admin)):
    """Create a new LinkedIn mention mapping."""
    try:
        mention_id = create_linkedin_mention(
            company_name=request.company_name,
            organization_urn=request.organization_urn,
            aliases=request.aliases
        )
        return {"id": mention_id, "message": "Mention created successfully"}
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A mention with this URN already exists"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put("/mentions/{mention_id}")
async def update_mention_endpoint(mention_id: int, request: LinkedInMentionUpdate, user_id: int = Depends(require_admin)):
    """Update an existing mention."""
    existing = get_linkedin_mention(mention_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mention not found"
        )

    try:
        update_linkedin_mention(
            mention_id=mention_id,
            company_name=request.company_name,
            organization_urn=request.organization_urn,
            aliases=request.aliases,
            is_active=request.is_active
        )
        return {"message": "Mention updated successfully"}
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A mention with this URN already exists"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/mentions/{mention_id}")
async def delete_mention_endpoint(mention_id: int, user_id: int = Depends(require_admin)):
    """Delete a mention."""
    existing = get_linkedin_mention(mention_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mention not found"
        )

    delete_linkedin_mention(mention_id)
    return {"message": "Mention deleted successfully"}
