from datetime import date, datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Path, Query

from app.db.database import database
from app.models.auth import UserResponse
from app.models.hr import (
    LeaveCreate,
    LeaveUpdate,
    LeaveResponse,
    LeaveListResponse,
)
from app.utils.dependency import require_organization_member
from app.utils.roles import require_table_access, require_write_access
from app.utils.leave_requests import (
    create_leave,
    get_leave,
    list_leaves,
    update_leave,
    delete_leave,
    SORTABLE_COLUMNS,
)
from app.utils.activity_log import log_activity

router = APIRouter(prefix="/leave-requests", tags=["Leave Requests"])


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

    await delete_leave(current_user.org_id, leave_id)

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="deleted",
        entity_type="leave_request",
        entity_id=leave_id,
    )

    return {"message": f"Leave request {leave_id} has been deleted."}
