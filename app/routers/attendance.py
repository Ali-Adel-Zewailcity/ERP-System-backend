"""
Attendance Router — Attendance record management endpoints.

Endpoints
---------
  POST   /attendance/               - Create an attendance record
  GET    /attendance/               - List attendance records (paginated, filterable)
  GET    /attendance/{id}           - Get a single attendance record by ID
  PUT    /attendance/{id}           - Update an attendance record
  DELETE /attendance/{id}           - Delete an attendance record
"""

from datetime import date
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Path, Query

from app.db.database import database
from app.models.auth import UserResponse
from app.models.hr import (
    AttendanceCreate,
    AttendanceUpdate,
    AttendanceResponse,
    AttendanceListResponse,
)
from app.utils.dependency import require_organization_member
from app.utils.roles import require_table_access, require_write_access
from app.utils.attendance import (
    create_attendance,
    get_attendance,
    list_attendance,
    update_attendance,
    delete_attendance,
    SORTABLE_COLUMNS,
)
from app.utils.activity_log import log_activity


router = APIRouter(prefix="/attendance", tags=["Attendance"])


# ─────────────────────────────────────────────────────────────────────────────
# Create
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=AttendanceResponse,
    summary="Create Attendance Record",
    description="Creates a new attendance record scoped to the current user's organization.",
)
async def create_new_attendance(
    req: AttendanceCreate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> AttendanceResponse:
    """Create a new attendance record within the current organization."""
    require_write_access(current_user, "attendance")

    # Verify employee exists and belongs to the same org
    employee = await database.fetch_one(
        "SELECT id FROM employees WHERE id = :id AND org_id = :org_id",
        {"id": req.employee_id, "org_id": current_user.org_id},
    )
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found.",
        )

    # Check for duplicate attendance (one record per employee per day)
    existing = await database.fetch_one(
        "SELECT id FROM attendance WHERE employee_id = :employee_id AND attendance_date = :attendance_date",
        {"employee_id": req.employee_id, "attendance_date": req.attendance_date.isoformat()},
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An attendance record already exists for this employee on this date.",
        )

    new_record = await create_attendance(
        org_id=current_user.org_id,
        employee_id=req.employee_id,
        attendance_date=req.attendance_date,
        check_in_time=req.check_in_time,
        check_out_time=req.check_out_time,
        status=req.status,
        notes=req.notes,
    )

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="created",
        entity_type="attendance",
        entity_id=new_record["id"],
        new_value={"employee_id": req.employee_id, "attendance_date": str(req.attendance_date)},
    )

    return AttendanceResponse.model_validate(new_record)


# ─────────────────────────────────────────────────────────────────────────────
# List (paginated, filterable)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=AttendanceListResponse,
    summary="List Attendance Records",
    description=(
        "Returns a paginated list of attendance records scoped to the current user's "
        "organization. Supports search by employee name, status filter, date range, "
        "and department filter."
    ),
)
async def list_all_attendance(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=100, description="Search by employee name")] = None,
    status: Annotated[str | None, Query(pattern="^(present|absent|late|leave|holiday)?$")] = None,
    attendance_date_from: Annotated[date | None, Query(description="Filter: date on or after (YYYY-MM-DD)")] = None,
    attendance_date_to: Annotated[date | None, Query(description="Filter: date on or before (YYYY-MM-DD)")] = None,
    department: Annotated[str | None, Query(max_length=100, description="Filter by employee department")] = None,
    sort_by: Annotated[str | None, Query(description=f"Sort column. One of: {', '.join(sorted(SORTABLE_COLUMNS))}")] = None,
    sort_order: Annotated[str | None, Query(pattern="^(asc|desc)?$", description="Sort direction: asc or desc")] = None,
) -> AttendanceListResponse:
    """List attendance records with pagination and optional filters."""
    require_table_access(current_user, "attendance")

    rows, total = await list_attendance(
        org_id=current_user.org_id,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        attendance_date_from=attendance_date_from.isoformat() if attendance_date_from else None,
        attendance_date_to=attendance_date_to.isoformat() if attendance_date_to else None,
        department=department,
        sort_by=sort_by or "attendance_date",
        sort_order=sort_order or "desc",
    )

    items = [AttendanceResponse.model_validate(r) for r in rows]
    pages = (total + page_size - 1) // page_size if total else 0

    return AttendanceListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Get by ID
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{attendance_id}",
    response_model=AttendanceResponse,
    summary="Get Attendance Record",
    description="Returns a single attendance record by ID.",
)
async def get_attendance_by_id(
    attendance_id: Annotated[int, Path(description="ID of the attendance record to retrieve.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> AttendanceResponse:
    """Retrieve an attendance record by its ID."""
    require_table_access(current_user, "attendance")

    record = await get_attendance(current_user.org_id, attendance_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendance record not found.",
        )

    return AttendanceResponse.model_validate(record)


# ─────────────────────────────────────────────────────────────────────────────
# Update
# ─────────────────────────────────────────────────────────────────────────────

@router.put(
    "/{attendance_id}",
    response_model=AttendanceResponse,
    summary="Update Attendance Record",
    description="Updates an existing attendance record. Only provided fields are changed.",
)
async def update_attendance_by_id(
    attendance_id: Annotated[int, Path(description="ID of the attendance record to update.")],
    req: AttendanceUpdate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> AttendanceResponse:
    """Update an attendance record."""
    require_write_access(current_user, "attendance")

    # Verify the record exists
    existing = await get_attendance(current_user.org_id, attendance_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendance record not found.",
        )

    # Build update dict with only the provided fields
    values = {}
    for field in ("check_in_time", "check_out_time", "status", "notes"):
        val = getattr(req, field, None)
        if val is not None:
            if field in ("check_in_time", "check_out_time"):
                values[field] = val.isoformat()
            else:
                values[field] = val

    updated = await update_attendance(
        org_id=current_user.org_id,
        attendance_id=attendance_id,
        values=values,
    )

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="updated",
        entity_type="attendance",
        entity_id=attendance_id,
        old_value={k: str(existing[k]) for k in values if k in existing},
        new_value={k: str(v) for k, v in values.items()},
    )

    return AttendanceResponse.model_validate(updated)


# ─────────────────────────────────────────────────────────────────────────────
# Delete
# ─────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/{attendance_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Attendance Record",
    description="Deletes an attendance record. Requires write access.",
)
async def delete_attendance_by_id(
    attendance_id: Annotated[int, Path(description="ID of the attendance record to delete.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, str]:
    """Delete an attendance record."""
    require_write_access(current_user, "attendance")

    existing = await get_attendance(current_user.org_id, attendance_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendance record not found.",
        )

    await delete_attendance(current_user.org_id, attendance_id)

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="deleted",
        entity_type="attendance",
        entity_id=attendance_id,
    )

    return {"message": f"Attendance record {attendance_id} has been deleted."}
