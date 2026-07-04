"""
Auth router — registration, login, token refresh, and logout endpoints.
"""

from fastapi import Depends, HTTPException, status, APIRouter, Form
from fastapi.security import OAuth2PasswordRequestForm
import sqlalchemy as sa
from typing import Annotated

from app.db.database import database
from app.models.auth import UserRegisterRequest, UserResponse, Token
from app.schema.auth import users
from app.utils.security import get_password_hash, authenticate_user, create_jwt_token
from app.utils.user import update_user_last_login


router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def register(user: Annotated[UserRegisterRequest, Form()]):
    """
    Register a brand-new user account.

    The account is created without an organisation or a role (both are ``NULL``).
    """

    # Check for existing username
    existing_username = await database.fetch_one(sa.select(users.c.id).where((users.c.username == user.username)))
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already taken.",
        )

    # Check for existing email
    existing_email = await database.fetch_one(sa.select(users.c.id).where((users.c.email == user.email)))
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    # Check for existing phone number
    existing_phone = await database.fetch_one(sa.select(users.c.id).where((users.c.phone == user.phone)))
    if existing_phone:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this phone number already exists.",
        )

    password_hash = get_password_hash(user.password.get_secret_value())

    insert_values = {
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "password_hash": password_hash,
    }
    if user.first_name is not None:
        insert_values["first_name"] = user.first_name
    if user.last_name is not None:
        insert_values["last_name"] = user.last_name

    insert_query = (
        users.insert()
        .values(**insert_values)
        .returning(*users.c)
    )

    new_user = await database.fetch_one(insert_query)

    return UserResponse.model_validate(new_user)


@router.post("/login", status_code=status.HTTP_202_ACCEPTED, response_model=Token)
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_jwt_token(user)
    
    await update_user_last_login(user.id)
    
    return Token(access_token=access_token, token_type="bearer")