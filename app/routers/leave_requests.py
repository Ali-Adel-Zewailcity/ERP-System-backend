"""
Leave Requests Router — Leave request management endpoints.

Endpoints
---------
  POST   /leave-requests/               - Create a leave request
  GET    /leave-requests/               - List leave requests (paginated, filterable)
  GET    /leave-requests/export         - Export leave requests (XLSX or CSV)
  GET    /leave-requests/export/template - Download import template
  POST   /leave-requests/import         - Import leave requests from file
  POST   /leave-requests/bulk/delete    - Delete multiple leave requests
  POST   /leave-requests/bulk/status    - Change status of multiple leave requests
  GET    /leave-requests/{leave_id}     - Get a single leave request by ID
  PUT    /leave-requests/{leave_id}     - Update a leave request
  DELETE /leave-requests/{leave_id}     - Delete a leave request
"""

import io
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, status, Path, Query, UploadFile, File, Response

from app.db.database import database
from app.models.auth import UserResponse
from app.models.hr import (
    LeaveCreate,
    LeaveUpdate,
    LeaveResponse,
    LeaveListResponse,
    BulkDeleteRequest,
    LeaveBulkStatusRequest,
    ImportSummary,
)
from app.utils.dependency import require_organization_member
from app.utils.roles import require_table_access, require_write_access
from app.utils.leave_requests import (
    create_leave,
    get_leave,
    list_leaves,
    list_all_leaves_for_org,
    update_leave,
    delete_leave,
    SORTABLE_COLUMNS,
)
from app.utils.import_export import generate_export, _parse_xlsx, _parse_csv
from app.utils.activity_log import log_activity
from app.utils.attendance import create_attendance

router = APIRouter(prefix="/leave-requests", tags=["Leave Requests"])


# ─────────────────────────────────────────────────────────────────────────────
# Create
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=LeaveResponse,
    summary="Create Leave Request",
)
async def create_new_leave(
    req: LeaveCreate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> LeaveResponse:
    """Create a new leave request within the current organization."""
    require_write_access(current_user, "leave_requests")

    # Verify employee exists and belongs to the same org
    employee = await database.fetch_one(
        "SELECT id, full_name, department FROM employees WHERE id = :id AND org_id = :org_id",
        {"id": req.employee_id, "org_id": current_user.org_id},
    )
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found.",
        )

    # Calculate total_days (inclusive of both start and end)
    total_days = (req.end_date - req.start_date).days + 1

    new_record = await create_leave(
        org_id=current_user.org_id,
        employee_id=req.employee_id,
        leave_type=req.leave_type,
        start_date=req.start_date,
        end_date=req.end_date,
        total_days=total_days,
        reason=req.reason,
    )

    # Re-fetch with JOIN data
    full_record = await get_leave(current_user.org_id, new_record["id"])

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="created",
        entity_type="leave_request",
        entity_id=new_record["id"],
        new_value={"employee_id": req.employee_id, "leave_type": req.leave_type},
    )

    return LeaveResponse.model_validate(full_record or new_record)


# ─────────────────────────────────────────────────────────────────────────────
# List (paginated, filterable)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=LeaveListResponse,
    summary="List Leave Requests",
)
async def list_all_leaves(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=100, description="Search by employee name")] = None,
    status: Annotated[str | None, Query(pattern="^(pending|approved|rejected|cancelled)?$")] = None,
    leave_type: Annotated[str | None, Query(pattern="^(annual|sick|unpaid|emergency|maternity|paternity)?$")] = None,
    date_from: Annotated[date | None, Query(description="Filter: start date on or after (YYYY-MM-DD)")] = None,
    date_to: Annotated[date | None, Query(description="Filter: end date on or before (YYYY-MM-DD)")] = None,
    department: Annotated[str | None, Query(max_length=100, description="Filter by employee department")] = None,
    sort_by: Annotated[str | None, Query(description=f"Sort column. One of: {', '.join(sorted(SORTABLE_COLUMNS))}")] = None,
    sort_order: Annotated[str | None, Query(pattern="^(asc|desc)?$")] = None,
) -> LeaveListResponse:
    """List leave requests with pagination and optional filters."""
    require_table_access(current_user, "leave_requests")

    rows, total = await list_leaves(
        org_id=current_user.org_id,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        leave_type=leave_type,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
        department=department,
        sort_by=sort_by or "requested_at",
        sort_order=sort_order or "desc",
    )

    items = [LeaveResponse.model_validate(r) for r in rows]
    pages = (total + page_size - 1) // page_size if total else 0

    return LeaveListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

LEAVE_EXPORT_HEADERS = [
    "employee_name", "department", "leave_type",
    "start_date", "end_date", "total_days", "status", "reason",
]


@router.get(
    "/export",
    summary="Export Leave Requests",
    description="Export leave requests to XLSX or CSV.",
)
async def export_leave_requests(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    format: Annotated[str, Query(pattern="^(xlsx|csv)$")] = "xlsx",
    scope: Annotated[str, Query(pattern="^(filtered|all)$")] = "filtered",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    status_param: Annotated[str | None, Query(alias="status", pattern="^(pending|approved|rejected|cancelled)?$")] = None,
    leave_type: Annotated[str | None, Query(pattern="^(annual|sick|unpaid|emergency|maternity|paternity)?$")] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    department: Annotated[str | None, Query(max_length=100)] = None,
    sort_by: Annotated[str | None, Query()] = None,
    sort_order: Annotated[str | None, Query(pattern="^(asc|desc)?$")] = None,
):
    """Export leave requests to XLSX or CSV."""
    require_table_access(current_user, "leave_requests")

    if scope == "filtered":
        rows, _ = await list_leaves(
            org_id=current_user.org_id,
            page=page,
            page_size=page_size,
            search=search,
            status=status_param,
            leave_type=leave_type,
            date_from=date_from.isoformat() if date_from else None,
            date_to=date_to.isoformat() if date_to else None,
            department=department,
            sort_by=sort_by or "requested_at",
            sort_order=sort_order or "desc",
        )
    else:
        rows = await list_all_leaves_for_org(
            org_id=current_user.org_id,
            search=search,
            status=status_param,
            leave_type=leave_type,
            date_from=date_from.isoformat() if date_from else None,
            date_to=date_to.isoformat() if date_to else None,
            department=department,
            sort_by=sort_by or "requested_at",
            sort_order=sort_order or "desc",
        )

    content = generate_export(rows, format, headers=LEAVE_EXPORT_HEADERS)

    if format == "csv":
        media_type = "text/csv"
        filename = "leave_requests.csv"
    else:
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "leave_requests.xlsx"

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
    "leave_type",
    "start_date",
    "end_date",
    "reason",
]


@router.get(
    "/export/template",
    summary="Download Leave Import Template",
    description="Download an XLSX template for importing leave requests.",
)
async def download_leave_template(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
):
    """Return an XLSX template file."""
    require_table_access(current_user, "leave_requests")
    from app.utils.import_export import _write_rows_to_xlsx

    example = [{
        "employee_name": "Ali Hassan",
        "leave_type": "annual",
        "start_date": "2026-07-01",
        "end_date": "2026-07-05",
        "reason": "Annual vacation",
    }]
    content = _write_rows_to_xlsx(example, IMPORT_TEMPLATE_HEADERS)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=leave_import_template.xlsx"},
    )


@router.post(
    "/import",
    response_model=ImportSummary,
    summary="Import Leave Requests",
    description="Import leave requests from an XLSX or CSV file.",
)
async def import_leave_requests(
    file: Annotated[UploadFile, File(description="XLSX or CSV file")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> ImportSummary:
    """Import leave requests from a file."""
    require_write_access(current_user, "leave_requests")

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

    # Build a lookup of employee name → employee_id for this org
    employees_lookup = await database.fetch_all(
        "SELECT id, full_name FROM employees WHERE org_id = :org_id",
        {"org_id": current_user.org_id},
    )
    name_to_id = {r["full_name"].strip().lower(): r["id"] for r in employees_lookup}

    errors = []
    imported = 0

    for i, row in enumerate(rows, start=1):
        row_errors = []
        emp_name = (row.get("employee_name") or "").strip()
        emp_id = name_to_id.get(emp_name.lower())

        if not emp_name:
            row_errors.append("employee_name is required.")
        elif not emp_id:
            row_errors.append(f"Employee '{emp_name}' not found in your organization.")

        raw_leave_type = (row.get("leave_type") or "").strip().lower()
        valid_leave_types = {"annual", "sick", "unpaid", "emergency", "maternity", "paternity"}
        if raw_leave_type and raw_leave_type not in valid_leave_types:
            row_errors.append(f"Invalid leave_type '{raw_leave_type}'. Must be one of: {', '.join(sorted(valid_leave_types))}.")
        if not raw_leave_type:
            row_errors.append("leave_type is required.")

        raw_start = row.get("start_date")
        raw_end = row.get("end_date")
        if not raw_start:
            row_errors.append("start_date is required.")
        if not raw_end:
            row_errors.append("end_date is required.")

        if row_errors:
            errors.append({"row": i, "reasons": "; ".join(row_errors)})
            continue

        try:
            start = date.fromisoformat(raw_start)
            end = date.fromisoformat(raw_end)
            total_days = (end - start).days + 1

            await create_leave(
                org_id=current_user.org_id,
                employee_id=emp_id,
                leave_type=raw_leave_type,
                start_date=start,
                end_date=end,
                total_days=total_days,
                reason=row.get("reason") or None,
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
# Bulk Delete
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/bulk/delete",
    status_code=status.HTTP_200_OK,
    summary="Bulk Delete Leave Requests",
    description="Delete multiple leave requests by IDs.",
)
async def bulk_delete_leave_requests(
    req: BulkDeleteRequest,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, Any]:
    """Delete multiple leave requests."""
    require_write_access(current_user, "leave_requests")

    deleted = 0
    for leave_id in req.ids:
        existing = await get_leave(current_user.org_id, leave_id)
        if not existing:
            continue
        # Clean up auto-generated attendance records for approved leaves
        if existing["status"] == "approved":
            emp_id = existing["employee_id"]
            s = date.fromisoformat(existing["start_date"])
            e = date.fromisoformat(existing["end_date"])
            await database.execute(
                """DELETE FROM attendance
                   WHERE employee_id = :eid
                     AND attendance_date BETWEEN :sdt AND :edt
                     AND source = 'leave'""",
                {"eid": emp_id, "sdt": s.isoformat(), "edt": e.isoformat()},
            )
        await delete_leave(current_user.org_id, leave_id)
        deleted += 1
        await log_activity(
                org_id=current_user.org_id,
                user_id=current_user.id,
                action="deleted",
                entity_type="leave_request",
                entity_id=leave_id,
            )

    return {"message": f"{deleted} leave request(s) deleted.", "deleted": deleted}


# ─────────────────────────────────────────────────────────────────────────────
# Bulk Status Change
# ─────────────────────────────────────────────────────────────────────────────

VALID_BULK_STATUSES = {"pending", "approved", "rejected", "cancelled"}


@router.post(
    "/bulk/status",
    status_code=status.HTTP_200_OK,
    summary="Bulk Change Leave Status",
    description="Change the status of multiple leave requests.",
)
async def bulk_change_leave_status(
    req: LeaveBulkStatusRequest,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, Any]:
    """Change the status of multiple leave requests."""
    require_write_access(current_user, "leave_requests")

    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    for leave_id in req.ids:
        existing = await get_leave(current_user.org_id, leave_id)
        if not existing:
            continue

        old_status = existing["status"]
        new_status = req.status
        do_attendance_sync = old_status != new_status

        if do_attendance_sync and new_status == "approved":
            # Create 'leave' attendance records for each date in the leave range
            emp_id = existing["employee_id"]
            start = date.fromisoformat(existing["start_date"])
            end = date.fromisoformat(existing["end_date"])
            current = start
            while current <= end:
                # Check if a manual attendance record already exists for this day
                existing_att = await database.fetch_one(
                    "SELECT id, source FROM attendance WHERE employee_id = :eid AND attendance_date = :dt",
                    {"eid": emp_id, "dt": current.isoformat()},
                )
                if existing_att and existing_att["source"] == "manual":
                    current += timedelta(days=1)
                    continue
                if existing_att and existing_att["source"] == "leave":
                    current += timedelta(days=1)
                    continue
                await create_attendance(
                    org_id=current_user.org_id,
                    employee_id=emp_id,
                    attendance_date=current,
                    status="leave",
                    source="leave",
                )
                current += timedelta(days=1)

        elif do_attendance_sync and new_status in ("rejected", "cancelled"):
            # Remove auto-generated leave attendance records
            emp_id = existing["employee_id"]
            start = date.fromisoformat(existing["start_date"])
            end = date.fromisoformat(existing["end_date"])
            await database.execute(
                """DELETE FROM attendance
                   WHERE employee_id = :eid
                     AND attendance_date BETWEEN :sdt AND :edt
                     AND source = 'leave'""",
                {"eid": emp_id, "sdt": start.isoformat(), "edt": end.isoformat()},
            )

        await update_leave(
            org_id=current_user.org_id,
            leave_id=leave_id,
            values={"status": req.status, "resolved_at": now},
        )
        updated += 1
        await log_activity(
            org_id=current_user.org_id,
            user_id=current_user.id,
            action="status_changed",
            entity_type="leave_request",
            entity_id=leave_id,
            old_value={"status": existing["status"]},
            new_value={"status": req.status},
        )

    return {"message": f"{updated} leave request(s) updated.", "updated": updated}


# ─────────────────────────────────────────────────────────────────────────────
# Get by ID
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{leave_id}",
    response_model=LeaveResponse,
    summary="Get Leave Request",
)
async def get_leave_by_id(
    leave_id: Annotated[int, Path(description="ID of the leave request to retrieve.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> LeaveResponse:
    """Retrieve a leave request by its ID."""
    require_table_access(current_user, "leave_requests")

    record = await get_leave(current_user.org_id, leave_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Leave request not found.",
        )

    return LeaveResponse.model_validate(record)


# ─────────────────────────────────────────────────────────────────────────────
# Update
# ─────────────────────────────────────────────────────────────────────────────

@router.put(
    "/{leave_id}",
    response_model=LeaveResponse,
    summary="Update Leave Request",
)
async def update_leave_by_id(
    leave_id: Annotated[int, Path(description="ID of the leave request to update.")],
    req: LeaveUpdate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> LeaveResponse:
    """Update a leave request."""
    require_write_access(current_user, "leave_requests")

    existing = await get_leave(current_user.org_id, leave_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Leave request not found.",
        )

    values = {}
    for field in ("approved_by", "leave_type", "start_date", "end_date", "reason", "status"):
        val = getattr(req, field, None)
        if val is not None:
            if field in ("start_date", "end_date"):
                values[field] = val.isoformat()
            else:
                values[field] = val

    if "status" in values and existing["status"] != values["status"]:
        values["resolved_at"] = datetime.now(timezone.utc).isoformat()

    # Recalculate total_days if dates changed
    if "start_date" in values or "end_date" in values:
        start = values.get("start_date") or existing["start_date"]
        end = values.get("end_date") or existing["end_date"]
        if isinstance(start, str):
            start = date.fromisoformat(start)
        if isinstance(end, str):
            end = date.fromisoformat(end)
        values["total_days"] = (end - start).days + 1

    old_status = existing["status"]
    new_status = values.get("status")
    do_attendance_sync = new_status is not None and old_status != new_status

    if do_attendance_sync and new_status == "approved":
        emp_id = existing["employee_id"]
        effective_start = date.fromisoformat(values.get("start_date", existing["start_date"]))
        effective_end = date.fromisoformat(values.get("end_date", existing["end_date"]))
        current = effective_start
        while current <= effective_end:
            existing_att = await database.fetch_one(
                "SELECT id, source FROM attendance WHERE employee_id = :eid AND attendance_date = :dt",
                {"eid": emp_id, "dt": current.isoformat()},
            )
            if existing_att and existing_att["source"] == "manual":
                current += timedelta(days=1)
                continue
            if existing_att and existing_att["source"] == "leave":
                current += timedelta(days=1)
                continue
            await create_attendance(
                org_id=current_user.org_id,
                employee_id=emp_id,
                attendance_date=current,
                status="leave",
                source="leave",
            )
            current += timedelta(days=1)

    elif do_attendance_sync and new_status in ("rejected", "cancelled"):
        emp_id = existing["employee_id"]
        effective_start = date.fromisoformat(values.get("start_date", existing["start_date"]))
        effective_end = date.fromisoformat(values.get("end_date", existing["end_date"]))
        await database.execute(
            """DELETE FROM attendance
               WHERE employee_id = :eid
                 AND attendance_date BETWEEN :sdt AND :edt
                 AND source = 'leave'""",
            {"eid": emp_id, "sdt": effective_start.isoformat(), "edt": effective_end.isoformat()},
        )

    updated = await update_leave(
        org_id=current_user.org_id,
        leave_id=leave_id,
        values=values,
    )

    full_record = await get_leave(current_user.org_id, leave_id)

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="updated",
        entity_type="leave_request",
        entity_id=leave_id,
        old_value={k: str(existing[k]) for k in values if k in existing},
        new_value={k: str(v) for k, v in values.items()},
    )

    return LeaveResponse.model_validate(full_record or updated)


# ─────────────────────────────────────────────────────────────────────────────
# Delete
# ─────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/{leave_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Leave Request",
)
async def delete_leave_by_id(
    leave_id: Annotated[int, Path(description="ID of the leave request to delete.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, str]:
    """Delete a leave request."""
    require_write_access(current_user, "leave_requests")

    existing = await get_leave(current_user.org_id, leave_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Leave request not found.",
        )

    # Clean up auto-generated attendance records when a leave is deleted
    if existing["status"] == "approved":
        emp_id = existing["employee_id"]
        start = date.fromisoformat(existing["start_date"])
        end = date.fromisoformat(existing["end_date"])
        await database.execute(
            """DELETE FROM attendance
               WHERE employee_id = :eid
                 AND attendance_date BETWEEN :sdt AND :edt
                 AND source = 'leave'""",
            {"eid": emp_id, "sdt": start.isoformat(), "edt": end.isoformat()},
        )

    await delete_leave(current_user.org_id, leave_id)

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="deleted",
        entity_type="leave_request",
        entity_id=leave_id,
    )

    return {"message": f"Leave request {leave_id} has been deleted."}
