"""
Top Performance Router — Placeholder endpoint (scaffolding only).

Endpoint
--------
  GET /top-performance   - Placeholder returning an empty response
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.models.auth import UserResponse
from app.utils.dependency import require_organization_member


router = APIRouter(prefix="/top-performance", tags=["Top Performance"])


@router.get(
    "/",
    summary="Top Performance (placeholder)",
)
async def list_top_performance(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict:
    """Placeholder endpoint — returns empty result set."""
    return {"items": [], "message": "Not implemented yet"}