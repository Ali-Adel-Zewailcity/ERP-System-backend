from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.phone import mobile_registry

EmployeeStatusLiteral = Literal["active", "resigned"]


class EmployeeCreate(BaseModel):
    """Request model for creating a new employee."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "full_name": "Ali Hassan",
                "employee_number": "EMP-001",
                "email": "ali@company.com",
                "phone_number": "1012345678",
                "job_title": "Software Engineer",
                "department": "Engineering",
                "salary": 50000.00,
                "hire_date": "2026-01-15",
            }
        }
    )

    full_name: Annotated[str, Field(min_length=2, max_length=160)]
    employee_number: Annotated[str, Field(min_length=1, max_length=30)]
    email: Annotated[str, Field(max_length=255)]
    phone_number: Annotated[str | None, Field(max_length=20)] = None
    job_title: Annotated[str | None, Field(max_length=120)] = None
    department: Annotated[str | None, Field(max_length=100)] = None
    salary: Annotated[Decimal, Field(max_digits=12, decimal_places=2, ge=0)]
    hire_date: date
    status: EmployeeStatusLiteral = "active"

    @field_validator("phone_number", mode="before")
    @classmethod
    def validate_and_normalize_phone(cls, value: str | None):
        if value is None:
            return value
        return mobile_registry.parse_and_normalize(value)


class EmployeeUpdate(BaseModel):
    """Request model for updating an existing employee. All fields are optional."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "full_name": "Ali Hassan Updated",
                "job_title": "Senior Software Engineer",
                "salary": 60000.00,
                "status": "active",
            }
        }
    )

    full_name: Annotated[str | None, Field(min_length=2, max_length=160)] = None
    employee_number: Annotated[str | None, Field(min_length=1, max_length=30)] = None
    email: Annotated[str | None, Field(max_length=255)] = None
    phone_number: Annotated[str | None, Field(max_length=20)] = None
    job_title: Annotated[str | None, Field(max_length=120)] = None
    department: Annotated[str | None, Field(max_length=100)] = None
    salary: Annotated[Decimal | None, Field(max_digits=12, decimal_places=2, ge=0)] = None
    hire_date: date | None = None
    status: EmployeeStatusLiteral | None = None

    @field_validator("phone_number", mode="before")
    @classmethod
    def validate_and_normalize_phone(cls, value: str | None):
        if value is None:
            return value
        return mobile_registry.parse_and_normalize(value)


class EmployeeResponse(BaseModel):
    """Response model representing an employee record."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "org_id": 1,
                "full_name": "Ali Hassan",
                "employee_number": "EMP-001",
                "email": "ali@company.com",
                "phone_number": "1012345678",
                "job_title": "Software Engineer",
                "department": "Engineering",
                "salary": 50000.00,
                "hire_date": "2026-01-15",
                "status": "active",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        },
    )

    id: int
    org_id: int
    full_name: str
    employee_number: str
    email: str
    phone_number: str | None = None
    job_title: str | None = None
    department: str | None = None
    salary: Decimal
    hire_date: date
    status: str
    profile_photo_path: str | None = None
    created_at: datetime
    updated_at: datetime


class EmployeeListResponse(BaseModel):
    """Paginated list response for employees."""

    items: list[EmployeeResponse]
    total: int
    page: int
    page_size: int
    pages: int


class BulkDeleteRequest(BaseModel):
    """Request model for bulk deleting employees."""

    ids: list[int]


class BulkStatusRequest(BaseModel):
    """Request model for bulk status change."""

    ids: list[int]
    status: EmployeeStatusLiteral


class ImportSummary(BaseModel):
    """Summary of an import operation."""

    total: int
    imported: int
    failed: int
    errors: list[dict[str, str | int]]


class ExportParams(BaseModel):
    """Query params for exporting employees."""

    format: str = "xlsx"
    scope: str = "filtered"
    search: str | None = None
    department: str | None = None
    status: str | None = None
    hire_date_from: date | None = None
    hire_date_to: date | None = None
    sort_by: str | None = None
    sort_order: str | None = None


class AttachmentResponse(BaseModel):
    """Response model for an employee attachment."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    file_type: str
    file_name: str
    content_type: str | None = None
    file_size: int | None = None
    uploaded_by: int | None = None
    created_at: datetime


class ActivityLogResponse(BaseModel):
    """Response model for an activity log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    module: str
    action: str
    entity_type: str | None = None
    entity_id: int | None = None
    old_value: Any = None
    new_value: Any = None
    timestamp: datetime
