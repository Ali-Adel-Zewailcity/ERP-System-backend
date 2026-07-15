"""
Security utilities — password hashing, verification, and JWT token creation.
"""

from fastapi import HTTPException
from pwdlib import PasswordHash
import sqlalchemy as sa
import jwt
from datetime import datetime, timedelta, timezone

from app.db.database import database
from app.schema.auth import users
from app.models.auth import UserResponse
from app.core.config import settings

password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummypassword")


def verify_password(plain_password, hashed_password) -> bool:
    """Check if a plain text password is equivalent to a password hash."""
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password) -> str:
    """Returns hashed value of a plain text password."""
    return password_hash.hash(password)


async def authenticate_user(username: str, password: str) -> UserResponse | bool:
    query = sa.select(users).where((users.c.username == username))
    user_record = await database.fetch_one(query)

    if not user_record:
        # Mitigate timing attacks by hashing a dummy password even if user doesn't exist
        verify_password(password, DUMMY_HASH)
        return False

    if not verify_password(password, user_record.password_hash):
        return False

    return UserResponse.model_validate(dict(user_record._mapping))


def create_jwt_token(user: UserResponse) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": str(user.id), "name": user.username, "exp": expire}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt