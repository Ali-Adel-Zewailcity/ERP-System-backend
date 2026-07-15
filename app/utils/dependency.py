"""
Dependencies — FastAPI dependencies required for API Endpoints.
"""

from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
import sqlalchemy as sa

from app.core.config import settings
from app.db.database import database
from app.schema.auth import users
from app.models.auth import UserResponse
from app.models.roles import UserPermissionsResponse
from app.utils.roles import get_permissions_for_user


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> UserResponse:
    """
    Validates a JWT access token, verifies the user exists in the database,
    and ensures the account is currently active.
    """

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        id: str = payload.get("sub")
        if id is None:
            raise credentials_exception
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError:
        raise credentials_exception

    query = sa.select(users).where(users.c.id == int(user_id))
    user_record = await database.fetch_one(query)

    if user_record is None:
        raise credentials_exception

    user = UserResponse.model_validate(dict(user_record._mapping))
    # user = UserResponse.model_validate(dict(user_record._mapping))

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    return user


async def require_organization_member(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> UserResponse:
    """
    Ensures the authenticated user is associated with an organization.
    """
    if not current_user.org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with any organization.",
        )
    return current_user


async def user_permissions(
    current_user: Annotated[UserResponse, Depends(get_current_user)]
) -> UserPermissionsResponse:
    """
    Resolve and return the user's simplified permission map.
    No database lookups — derived purely from the user's role + department fields.
    """
    permissions = get_permissions_for_user(current_user)

    return UserPermissionsResponse(
        user_id=current_user.id,
        org_id=current_user.org_id,
        role=current_user.role,
        department=current_user.department,
        permissions=permissions,
    )