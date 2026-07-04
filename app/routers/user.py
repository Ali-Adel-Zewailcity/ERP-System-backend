from typing import Annotated
from fastapi import APIRouter, Depends

from app.models.auth import UserResponse
from app.utils.dependency import get_current_user

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: Annotated[UserResponse, Depends(get_current_user)]):
    """
    Returns User data. It will only execute if a valid,
    unexpired token belonging to an active user is provided in the headers.
    """
    return current_user