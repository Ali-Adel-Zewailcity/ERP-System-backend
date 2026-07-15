import re
from pydantic import BaseModel, ConfigDict, EmailStr, SecretStr, field_validator, Field, model_validator
from typing import Annotated, Literal, Optional
from datetime import date, datetime
from app.utils.phone import mobile_registry
from email_validator import validate_email, EmailUndeliverableError, EmailNotValidError


RoleLiteral = Literal["owner", "admin", "hr_manager", "inventory_manager", "sales_manager", "employee"]
DepartmentLiteral = Literal["hr", "inventory", "sales"]


class UserRegisterRequest(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    username: Annotated[str, Field(min_length=3, max_length=20)]
    first_name: Annotated[str | None, Field(max_length=80)] = None
    last_name: Annotated[str | None, Field(max_length=80)] = None
    email: Annotated[EmailStr, Field(json_schema_extra={"check_deliverability": True})]
    phone: Annotated[str, Field(min_length=10, max_length=20)]
    password: Annotated[SecretStr, Field(min_length=8)]
    confirm_password: SecretStr

    @field_validator("username", mode="before")
    @classmethod
    def username_validation(cls, value):
        if not re.match(r"^\w+$", value):
            raise ValueError("Username must contain only letters, digits, or underscores (_). No spaces or special characters allowed.")
        return value

    @field_validator("email")
    @classmethod
    def check_email_deliverability(cls, value: str):
        try:
            email_info = validate_email(value, check_deliverability=True)
            return email_info.normalized
        except EmailUndeliverableError:
            raise ValueError("The domain for this email address does not exist or cannot receive mail.")
        except EmailNotValidError:
            raise ValueError("Please provide a valid email address.")

    @field_validator("phone", mode="before")
    @classmethod
    def validate_and_normalize_phone(cls, value: str):
        return mobile_registry.parse_and_normalize(value)

    @field_validator("password", mode="after")
    @classmethod
    def password_complexity(cls, value: SecretStr):
        password_str = value.get_secret_value()
        pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).+$"
        if not re.match(pattern, password_str):
            raise ValueError(
                "Password must contain at least one uppercase letter, "
                "one lowercase letter, one number, and one special character."
            )
        return value

    @model_validator(mode="after")
    def password_match(self):
        if self.password.get_secret_value() != self.confirm_password.get_secret_value():
            raise ValueError("Passwords do not match.")
        return self


# class UserResponse(BaseModel):
#     """Response model for a user account."""
#     model_config = ConfigDict(from_attributes=True)

#     id: int
#     org_id: int | None = None
#     role: RoleLiteral | None = None
#     department: DepartmentLiteral | None = None

#     username: str = Field(max_length=20)
#     email: EmailStr
#     phone: str = Field(max_length=30)
#     first_name: str | None = Field(default=None, max_length=80)
#     last_name: str | None = Field(default=None, max_length=80)

#     is_active: bool = True
#     last_login: Optional[date] = None
#     created_at: datetime
#     updated_at: datetime

from pydantic import BaseModel, EmailStr
from datetime import datetime, date
from typing import Optional

class UserResponse(BaseModel):
    id: int
    org_id: Optional[int] = None
    role: Optional[str] = None
    department: Optional[str] = None
    username: str
    email: EmailStr
    phone: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: bool
    created_at: datetime                     # 👈 متطابق مع TIMESTAMP WITH TIME ZONE
    updated_at: datetime                     # 👈 متطابق مع TIMESTAMP WITH TIME ZONE
    last_login: Optional[date] = None        # 👈 متطابق مع DATE (تاريخ فقط بدون وقت)

    class Config:
        from_attributes = True  # للتوافق مع SQLAlchemy في Pydantic v2


class Token(BaseModel):
    access_token: str
    token_type: str