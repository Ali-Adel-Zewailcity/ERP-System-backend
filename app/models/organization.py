"""
Organization Schemas — Pydantic v2 request/response models for organization management.

Models
------
  OrganizationCreateRequest  - Payload for creating a new organization.
  OrganizationResponse       - Response model representing an organization record.
  OrganizationMemberResponse - Response model for a member with their role info.
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Annotated

from app.utils.phone import mobile_registry
from app.models.auth import RoleLiteral, DepartmentLiteral


class OrganizationCreateRequest(BaseModel):
    """Request model for creating a new organization."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Acme Corp",
                "phone": "201234567894",
                "address": "123 Business Ave, Cairo, Egypt",
            }
        }
    )

    name: Annotated[str, Field(
            min_length=2, max_length=150,
            description="Legal or trade name of the organization."
        )]

    phone: Annotated[str, Field(min_length=10, max_length=20,
            description="Organization's main contact phone number."
        )]
    address: Annotated[str | None, Field(
            description="Organization's registered address."
        )] = None

    @field_validator("phone", mode="before")
    @classmethod
    def validate_and_normalize_phone(cls, value: str):
        return mobile_registry.parse_and_normalize(value)


class OrganizationResponse(BaseModel):
    """Response model representing an organization record."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "name": "Acme Corp",
                "owner_id": 42,
                "phone": "+20123456789",
                "address": "123 Business Ave, Cairo, Egypt",
                "is_active": True,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        },
    )

    id: Annotated[int, Field(description="Unique organization ID.")]
    name: Annotated[str, Field(description="Organization name.")]
    owner_id: Annotated[int, Field(description="ID of the user who owns this organization.")]
    phone: Annotated[str, Field(description="Organization contact phone.")]
    address: Annotated[str | None, Field(description="Organization address.")] = None
    is_active: Annotated[bool, Field(description="Whether the organization is currently active.")]
    created_at: Annotated[datetime, Field(description="Timestamp when the organization was created.")]
    updated_at: Annotated[datetime, Field(description="Timestamp of last update.")]


class OrganizationMemberResponse(BaseModel):
    """Response model representing a member of the organization."""
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[int, Field(description="User ID.")]
    username: Annotated[str | None, Field(description="Username.")] = None
    email: Annotated[str | None, Field(description="User email.")] = None
    phone: Annotated[str | None, Field(description="User phone.")] = None
    first_name: Annotated[str | None, Field(description="First name.")] = None
    last_name: Annotated[str | None, Field(description="Last name.")] = None
    role: Annotated[RoleLiteral | None, Field(description="Assigned fixed role.")] = None
    department: Annotated[DepartmentLiteral | None, Field(description="Assigned department.")] = None