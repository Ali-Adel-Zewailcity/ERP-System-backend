"""
Attendance Router — Attendance record management endpoints.

Endpoints
---------
  POST   /attendance/               - Create an attendance record
  GET    /attendance/               - List attendance records (paginated, filterable)
  GET    /attendance/{id}           - Get a single attendance record by ID
  PUT    /attendance/{id}           - Update an attendance record
  DELETE /attendance/{id}           - Delete an attendance record
  GET    /attendance/export         - Export attendance records (XLSX or CSV)
  GET    /attendance/export/template - Download import template
  POST   /attendance/import         - Import attendance records from file
"""

import io
from datetime import date
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, status, Path, Query, UploadFile, File, Response

from app.db.database import database
from app.models.auth import UserResponse
from app.models.hr import (
    AttendanceCreate,
    AttendanceUpdate,
    AttendanceResponse,
    AttendanceListResponse,
    AttendanceStatsResponse,
    ImportSummary,
)
from app.utils.dependency import require_organization_member
from app.utils.roles import require_table_access, require_write_access
from app.utils.attendance import (
    create_attendance,
    get_attendance,
    list_attendance,
    list_all_attendance_for_org,
    get_attendance_stats,
    bulk_delete_attendance,
    bulk_update_attendance_status,
    update_attendance,
    delete_attendance,
    SORTABLE_COLUMNS,
)
from app.utils.import_export import generate_export, _parse_xlsx, _parse_csv
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

    # Re-fetch with JOIN data (employee_name, department)
    full_record = await get_attendance(current_user.org_id, new_record["id"])

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="created",
        entity_type="attendance",
        entity_id=new_record["id"],
        new_value={"employee_id": req.employee_id, "attendance_date": str(req.attendance_date)},
    )

    return AttendanceResponse.model_validate(full_record or new_record)


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
# Statistics
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/stats",
    response_model=AttendanceStatsResponse,
    summary="Attendance Statistics",
    description="Returns summary statistics (present/absent/late today, total this month) for the dashboard cards.",
)
async def attendance_stats(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> AttendanceStatsResponse:
    """Return attendance statistics for the organization."""
    require_table_access(current_user, "attendance")
    stats = await get_attendance_stats(current_user.org_id)
    return AttendanceStatsResponse(**stats)


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

ATTENDANCE_EXPORT_HEADERS = [
    "employee_name", "department", "attendance_date",
    "check_in_time", "check_out_time", "overtime", "status", "notes",
]


def _calc_overtime(check_in: str | None, check_out: str | None) -> str:
    """Calculate overtime (hours beyond 8h) as a human-readable string."""
    if not check_in or not check_out:
        return ""
    try:
        parts_in = check_in.split(":")
        parts_out = check_out.split(":")
        in_min = int(parts_in[0]) * 60 + int(parts_in[1])
        out_min = int(parts_out[0]) * 60 + int(parts_out[1])
        diff = out_min - in_min
        if diff <= 8 * 60:
            return "0h"
        ot = diff - 8 * 60
        h = ot // 60
        m = ot % 60
        return f"{h}h{m}m" if m else f"{h}h"
    except (ValueError, IndexError):
        return ""


@router.get(
    "/export",
    summary="Export Attendance Records",
    description="Export attendance records to XLSX or CSV.",
)
async def export_attendance(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    format: Annotated[str, Query(pattern="^(xlsx|csv)$")] = "xlsx",
    scope: Annotated[str, Query(pattern="^(filtered|all)$")] = "filtered",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    status_param: Annotated[str | None, Query(alias="status", pattern="^(present|absent|late|leave|holiday)?$")] = None,
    attendance_date_from: Annotated[date | None, Query()] = None,
    attendance_date_to: Annotated[date | None, Query()] = None,
    department: Annotated[str | None, Query(max_length=100)] = None,
    sort_by: Annotated[str | None, Query()] = None,
    sort_order: Annotated[str | None, Query(pattern="^(asc|desc)?$")] = None,
):
    """Export attendance records to XLSX or CSV."""
    require_table_access(current_user, "attendance")

    if scope == "filtered":
        rows = await list_all_attendance_for_org(
            org_id=current_user.org_id,
            search=search,
            status=status_param,
            attendance_date_from=attendance_date_from.isoformat() if attendance_date_from else None,
            attendance_date_to=attendance_date_to.isoformat() if attendance_date_to else None,
            department=department,
            sort_by=sort_by or "attendance_date",
            sort_order=sort_order or "desc",
        )
    else:
        rows = await list_all_attendance_for_org(
            org_id=current_user.org_id,
            search=search,
            status=status_param,
            attendance_date_from=attendance_date_from.isoformat() if attendance_date_from else None,
            attendance_date_to=attendance_date_to.isoformat() if attendance_date_to else None,
            department=department,
            sort_by=sort_by or "attendance_date",
            sort_order=sort_order or "desc",
        )

    for row in rows:
        row["overtime"] = _calc_overtime(row.get("check_in_time"), row.get("check_out_time"))

    content = generate_export(rows, format, headers=ATTENDANCE_EXPORT_HEADERS)

    if format == "csv":
        media_type = "text/csv"
        filename = "attendance.csv"
    else:
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "attendance.xlsx"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Import
# ─────────────────────────────────────────────────────────────────────────────

IMPORT_TEMPLATE_HEADERS = [
    "employee_name",
    "attendance_date",
    "check_in_time",
    "check_out_time",
    "status",
    "notes",
]


@router.get(
    "/export/template",
    summary="Download Attendance Import Template",
    description="Download an XLSX template for importing attendance records.",
)
async def download_attendance_template(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
):
    """Return an XLSX template file."""
    require_table_access(current_user, "attendance")
    from app.utils.import_export import _write_rows_to_xlsx

    example = [{
        "employee_name": "Ali Hassan",
        "attendance_date": "2026-07-01",
        "check_in_time": "09:00",
        "check_out_time": "17:00",
        "status": "present",
        "notes": "",
    }]
    content = _write_rows_to_xlsx(example, IMPORT_TEMPLATE_HEADERS)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=attendance_import_template.xlsx"},
    )


@router.post(
    "/import",
    response_model=ImportSummary,
    summary="Import Attendance Records",
    description="Import attendance records from an XLSX or CSV file.",
)
async def import_attendance(
    file: Annotated[UploadFile, File(description="XLSX or CSV file")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> ImportSummary:
    """Import attendance records from a file."""
    require_write_access(current_user, "attendance")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty.")

    filename = file.filename or "import.xlsx"
    try:
        if filename.endswith(".csv"):
            rows = _parse_csv(content)
        else:
            rows = _parse_xlsx(content)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No data found in file.")

    # Build lookups for employee identification
    employees_lookup = await database.fetch_all(
        "SELECT id, full_name, employee_number FROM employees WHERE org_id = :org_id",
        {"org_id": current_user.org_id},
    )
    number_to_id: dict[str, int] = {}
    name_to_ids: dict[str, list[int]] = {}
    for r in employees_lookup:
        en = r["employee_number"]
        if en:
            number_to_id[en.strip().lower()] = r["id"]
        fn = r["full_name"].strip().lower()
        name_to_ids.setdefault(fn, []).append(r["id"])

    errors = []
    imported = 0

    for i, row in enumerate(rows, start=1):
        row_errors = []
        emp_name = (row.get("employee_name") or "").strip()
        emp_number = (row.get("employee_number") or "").strip()
        emp_id = None

        if not emp_name and not emp_number:
            row_errors.append("employee_name is required.")
        else:
            if emp_number:
                emp_id = number_to_id.get(emp_number.strip().lower())
                if not emp_id:
                    row_errors.append(f"Employee number '{emp_number}' not found in your organization.")
            else:
                matched_ids = name_to_ids.get(emp_name.lower())
                if matched_ids is None:
                    row_errors.append(f"Employee '{emp_name}' not found in your organization.")
                elif len(matched_ids) > 1:
                    row_errors.append(
                        f"Multiple employees found with name '{emp_name}'. "
                        "Please specify employee_number to resolve the ambiguity."
                    )
                else:
                    emp_id = matched_ids[0]

        raw_date = row.get("attendance_date")
        if not raw_date:
            row_errors.append("attendance_date is required.")

        raw_status = (row.get("status") or "").strip().lower()
        valid_statuses = {"present", "absent", "late", "leave", "holiday"}
        if raw_status and raw_status not in valid_statuses:
            row_errors.append(f"Invalid status '{raw_status}'. Must be one of: {', '.join(sorted(valid_statuses))}.")
        if not raw_status:
            row_errors.append("status is required.")

        if row_errors:
            errors.append({"row": i, "reasons": "; ".join(row_errors)})
            continue

        check_in = row.get("check_in_time") or None
        check_out = row.get("check_out_time") or None

        # Pre-check for duplicate attendance record
        duplicate_check = await database.fetch_one(
            "SELECT id FROM attendance WHERE employee_id = :employee_id AND attendance_date = :attendance_date",
            {"employee_id": emp_id, "attendance_date": raw_date},
        )
        if duplicate_check:
            errors.append({
                "row": i,
                "reasons": f"Attendance already exists for this employee on {raw_date}.",
            })
            continue

        try:
            from datetime import time

            def parse_time(val):
                if not val:
                    return None
                parts = str(val).split(":")
                return time(int(parts[0]), int(parts[1]))

            await create_attendance(
                org_id=current_user.org_id,
                employee_id=emp_id,
                attendance_date=date.fromisoformat(raw_date),
                status=raw_status,
                check_in_time=parse_time(check_in),
                check_out_time=parse_time(check_out),
                notes=row.get("notes") or None,
            )
            imported += 1
        except Exception as exc:
            errors.append({"row": i, "reasons": f"Failed to import: {str(exc)}"})

    return ImportSummary(
        total=len(rows),
        imported=imported,
        failed=len(rows) - imported,
        errors=errors,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bulk operations (filter-based)
# ─────────────────────────────────────────────────────────────────────────────


@router.delete(
    "/bulk",
    status_code=status.HTTP_200_OK,
    summary="Bulk Delete Attendance",
    description="Delete attendance records matching the current filter criteria. Supports same filters as list endpoint.",
)
async def bulk_delete_attendance_endpoint(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    search: Annotated[str | None, Query(max_length=100)] = None,
    department: Annotated[str | None, Query(max_length=100)] = None,
    status: Annotated[str | None, Query(pattern="^(present|absent|late|leave|holiday)?$")] = None,
    attendance_date_from: Annotated[str | None, Query()] = None,
    attendance_date_to: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """Delete all attendance records matching the specified filter criteria."""
    require_write_access(current_user, "attendance")
    deleted = await bulk_delete_attendance(
        org_id=current_user.org_id,
        search=search,
        department=department,
        status=status,
        attendance_date_from=attendance_date_from,
        attendance_date_to=attendance_date_to,
    )
    return {"deleted": deleted}


@router.post(
    "/bulk-status",
    status_code=status.HTTP_200_OK,
    summary="Bulk Status Change",
    description="Update status of attendance records matching the filter criteria.",
)
async def bulk_update_status_endpoint(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    new_status: Annotated[str, Query(pattern="^(present|absent|late|leave|holiday)$")],
    search: Annotated[str | None, Query(max_length=100)] = None,
    department: Annotated[str | None, Query(max_length=100)] = None,
    status: Annotated[str | None, Query(pattern="^(present|absent|late|leave|holiday)?$")] = None,
    attendance_date_from: Annotated[str | None, Query()] = None,
    attendance_date_to: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """Update status of all attendance records matching the specified filter criteria."""
    require_write_access(current_user, "attendance")
    updated = await bulk_update_attendance_status(
        org_id=current_user.org_id,
        new_status=new_status,
        search=search,
        department=department,
        current_status=status,
        attendance_date_from=attendance_date_from,
        attendance_date_to=attendance_date_to,
    )
    return {"updated": updated}


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

    # Re-fetch with JOIN data (employee_name, department)
    full_record = await get_attendance(current_user.org_id, attendance_id)

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="updated",
        entity_type="attendance",
        entity_id=attendance_id,
        old_value={k: str(existing[k]) for k in values if k in existing},
        new_value={k: str(v) for k, v in values.items()},
    )

    return AttendanceResponse.model_validate(full_record or updated)


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

    # Check if payroll has already been generated for this period
    att_date = existing["attendance_date"]
    if isinstance(att_date, str):
        parts = att_date.split("-")
        month = int(parts[1])
        year = int(parts[0])
    else:
        month = att_date.month
        year = att_date.year
    payroll_exists = await database.fetch_one(
        "SELECT id FROM payroll WHERE employee_id = :employee_id AND month = :month AND year = :year AND org_id = :org_id",
        {
            "employee_id": existing["employee_id"],
            "month": month,
            "year": year,
            "org_id": current_user.org_id,
        },
    )
    if payroll_exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attendance cannot be deleted because payroll has already been generated for this period.",
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
