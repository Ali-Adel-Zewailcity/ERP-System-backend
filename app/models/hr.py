from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.phone import mobile_registry

# ─────────────────────────────────────────────────────────────────────────────
# Type Aliases (must be declared before any model that references them)
# ─────────────────────────────────────────────────────────────────────────────

EmployeeStatusLiteral = Literal["active", "resigned"]
AttendanceStatusLiteral = Literal["present", "absent", "late", "leave", "holiday"]
LeaveTypeLiteral = Literal["annual", "sick", "unpaid", "emergency", "maternity", "paternity"]
LeaveStatusLiteral = Literal["pending", "approved", "rejected", "cancelled"]


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


class LeaveBulkStatusRequest(BaseModel):
    """Request model for bulk leave request status change."""

    ids: list[int]
    status: LeaveStatusLiteral


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


# ─────────────────────────────────────────────────────────────────────────────
# Attendance
# ─────────────────────────────────────────────────────────────────────────────


class AttendanceCreate(BaseModel):
    """Request model for creating an attendance record."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "employee_id": 1,
                "attendance_date": "2026-07-08",
                "check_in_time": "09:00:00",
                "check_out_time": "18:00:00",
                "status": "present",
                "notes": "On time",
            }
        }
    )

    employee_id: int
    attendance_date: date
    check_in_time: time | None = None
    check_out_time: time | None = None
    status: AttendanceStatusLiteral
    notes: str | None = None


class AttendanceUpdate(BaseModel):
    """Request model for updating an attendance record. All fields are optional."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "check_in_time": "09:15:00",
                "check_out_time": "17:30:00",
                "status": "late",
                "notes": "Arrived late due to traffic",
            }
        }
    )

    check_in_time: time | None = None
    check_out_time: time | None = None
    status: AttendanceStatusLiteral | None = None
    notes: str | None = None


class AttendanceResponse(BaseModel):
    """Response model representing an attendance record."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "employee_id": 1,
                "employee_name": "Ali Hassan",
                "department": "Engineering",
                "org_id": 1,
                "attendance_date": "2026-07-08",
                "check_in_time": "09:00:00",
                "check_out_time": "18:00:00",
                "status": "present",
                "notes": "On time",
                "created_at": "2026-07-08T00:00:00Z",
                "updated_at": "2026-07-08T00:00:00Z",
            }
        },
    )

    id: int
    employee_id: int
    employee_name: str | None = None
    department: str | None = None
    org_id: int
    attendance_date: date
    check_in_time: time | None = None
    check_out_time: time | None = None
    status: str
    source: str = "manual"
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class AttendanceListResponse(BaseModel):
    """Paginated list response for attendance records."""

    items: list[AttendanceResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ─────────────────────────────────────────────────────────────────────────────
# Leave Requests
# ─────────────────────────────────────────────────────────────────────────────


class LeaveCreate(BaseModel):
    """Request model for creating a leave request."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "employee_id": 1,
                "leave_type": "annual",
                "start_date": "2026-08-01",
                "end_date": "2026-08-05",
                "reason": "Family vacation",
            }
        }
    )

    employee_id: int
    leave_type: LeaveTypeLiteral
    start_date: date
    end_date: date
    reason: str | None = None

    @field_validator("end_date")
    @classmethod
    def end_must_be_on_or_after_start(cls, v: date, info) -> date:
        start = info.data.get("start_date")
        if start and v < start:
            raise ValueError("End date must be on or after start date.")
        return v


class LeaveUpdate(BaseModel):
    """Request model for updating a leave request. All fields are optional."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "approved",
                "notes": "Approved by manager",
            }
        }
    )

    approved_by: int | None = None
    leave_type: LeaveTypeLiteral | None = None
    start_date: date | None = None
    end_date: date | None = None
    reason: str | None = None
    status: LeaveStatusLiteral | None = None

    @field_validator("end_date")
    @classmethod
    def end_must_be_on_or_after_start(cls, v: date | None, info) -> date | None:
        if v is None:
            return v
        start = info.data.get("start_date")
        if start and v < start:
            raise ValueError("End date must be on or after start date.")
        return v


class LeaveResponse(BaseModel):
    """Response model representing a leave request."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "employee_id": 1,
                "employee_name": "Ali Hassan",
                "department": "Engineering",
                "approved_by": None,
                "approver_name": None,
                "leave_type": "annual",
                "start_date": "2026-08-01",
                "end_date": "2026-08-05",
                "total_days": 5,
                "reason": "Family vacation",
                "status": "pending",
                "requested_at": "2026-07-09T00:00:00Z",
                "resolved_at": None,
            }
        },
    )

    id: int
    employee_id: int
    employee_name: str | None = None
    department: str | None = None
    approved_by: int | None = None
    approver_name: str | None = None
    leave_type: str
    start_date: date
    end_date: date
    total_days: int
    reason: str | None = None
    status: str
    requested_at: datetime
    resolved_at: datetime | None = None


class LeaveListResponse(BaseModel):
    """Paginated list response for leave requests."""

    items: list[LeaveResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ─────────────────────────────────────────────────────────────────────────────
# Payroll
# ─────────────────────────────────────────────────────────────────────────────


PayrollStatusLiteral = Literal["pending", "paid", "cancelled"]


class PayrollGenerate(BaseModel):
    """Request model for generating payroll."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "employee_id": 1,
                "month": 7,
                "year": 2026,
            }
        }
    )

    employee_id: int | None = None
    month: int
    year: int


class PayrollUpdate(BaseModel):
    """Request model for updating a payroll record. All fields are optional."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "bonus": 500.00,
                "allowance": 200.00,
                "deductions": 100.00,
                "status": "paid",
                "notes": "Approved by manager",
            }
        }
    )

    bonus: Decimal | None = None
    allowance: Decimal | None = None
    deductions: Decimal | None = None
    status: PayrollStatusLiteral | None = None
    notes: str | None = None


class PayrollResponse(BaseModel):
    """Response model representing a payroll record."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "org_id": 1,
                "employee_id": 1,
                "employee_name": "Ali Hassan",
                "department": "Engineering",
                "month": 7,
                "year": 2026,
                "days_worked": 22,
                "absences": 0,
                "overtime_hours": Decimal("2.5"),
                "bonus": Decimal("350.00"),
                "allowance": Decimal("0"),
                "deductions": Decimal("0"),
                "gross_salary": Decimal("50350.00"),
                "net_salary": Decimal("50350.00"),
                "basic_salary": Decimal("50000.00"),
                "status": "pending",
                "notes": None,
                "generated_at": "2026-07-09T00:00:00Z",
                "created_at": "2026-07-09T00:00:00Z",
                "updated_at": "2026-07-09T00:00:00Z",
            }
        },
    )

    id: int
    org_id: int
    employee_id: int
    employee_name: str | None = None
    department: str | None = None
    basic_salary: Decimal | None = None
    month: int
    year: int
    days_worked: int
    absences: int
    overtime_hours: Decimal
    bonus: Decimal
    allowance: Decimal
    deductions: Decimal
    gross_salary: Decimal
    net_salary: Decimal
    status: str
    notes: str | None = None
    generated_at: datetime
    created_at: datetime
    updated_at: datetime


class PayrollListResponse(BaseModel):
    """Paginated list response for payroll records."""

    items: list[PayrollResponse]
    total: int
    page: int
    page_size: int
    pages: int