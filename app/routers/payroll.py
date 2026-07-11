"""
Payroll Router — Payroll record management endpoints.

Endpoints
---------
  GET    /payroll/               - List payroll records (paginated, filterable)
  GET    /payroll/{id}           - Get a single payroll record by ID
  POST   /payroll/generate       - Generate payroll for one or all employees
  PATCH  /payroll/{id}           - Update a payroll record (manual adjustments)
  DELETE /payroll/{id}           - Delete a payroll record
"""

from datetime import date
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, status, Path, Query

from app.db.database import database
from app.models.auth import UserResponse
from app.models.hr import PayrollGenerate, PayrollUpdate, PayrollResponse, PayrollListResponse
from app.utils.dependency import require_organization_member
from app.utils.roles import require_table_access, require_write_access
from app.utils.payroll import (
    get_payroll,
    list_payroll,
    generate_payroll as _generate_payroll,
    update_payroll as _update_payroll,
    delete_payroll as _delete_payroll,
    SORTABLE_COLUMNS,
)
from app.utils.activity_log import log_activity


router = APIRouter(prefix="/payroll", tags=["Payroll"])


# ─────────────────────────────────────────────────────────────────────────────
# List (paginated, filterable)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=PayrollListResponse,
    summary="List Payroll Records",
    description="Returns a paginated list of payroll records scoped to the current user's organization.",
)
async def list_all_payroll(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=100, description="Search by employee name")] = None,
    department: Annotated[str | None, Query(max_length=100, description="Filter by employee department")] = None,
    month: Annotated[int | None, Query(ge=1, le=12, description="Filter by month (1-12)")] = None,
    year: Annotated[int | None, Query(ge=2000, description="Filter by year")] = None,
    status: Annotated[str | None, Query(pattern="^(pending|paid|cancelled)?$", description="Filter by status")] = None,
    sort_by: Annotated[str | None, Query(description=f"Sort column. One of: {', '.join(sorted(SORTABLE_COLUMNS))}")] = None,
    sort_order: Annotated[str | None, Query(pattern="^(asc|desc)?$", description="Sort direction")] = None,
) -> PayrollListResponse:
    """List payroll records with pagination and optional filters."""
    require_table_access(current_user, "payroll")

    rows, total = await list_payroll(
        org_id=current_user.org_id,
        page=page,
        page_size=page_size,
        search=search,
        department=department,
        month=month,
        year=year,
        status=status,
        sort_by=sort_by or "created_at",
        sort_order=sort_order or "desc",
    )

    items = [PayrollResponse.model_validate(r) for r in rows]
    pages = (total + page_size - 1) // page_size if total else 0

    return PayrollListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Generate
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/generate",
    response_model=list[PayrollResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Generate Payroll",
    description=(
        "Automatically calculates and generates payroll for one employee "
        "(if employee_id is provided) or ALL employees in the organization "
        "for a given month/year. Uses attendance data for absences and overtime. "
        "If a payroll record already exists for the employee/month/year, it is updated."
    ),
)
async def generate_payroll_endpoint(
    req: PayrollGenerate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> list[PayrollResponse]:
    """Generate payroll records for the specified month/year."""
    require_write_access(current_user, "payroll")

    # Validate month/year
    if req.month < 1 or req.month > 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Month must be between 1 and 12.",
        )
    if req.year < 2000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Year must be greater than 2000.",
        )

    # If employee_id is specified, verify it exists in the org
    if req.employee_id:
        emp = await database.fetch_one(
            "SELECT id, full_name FROM employees WHERE id = :id AND org_id = :org_id",
            {"id": req.employee_id, "org_id": current_user.org_id},
        )
        if not emp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Employee not found.",
            )

    created = await _generate_payroll(
        org_id=current_user.org_id,
        employee_id=req.employee_id,
        month=req.month,
        year=req.year,
    )

    if not created:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No attendance data found for any employee in this period — cannot generate payroll. Please add attendance records first or create payroll manually.",
        )

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="generated",
        entity_type="payroll",
        new_value={
            "employee_id": req.employee_id,
            "month": req.month,
            "year": req.year,
            "count": len(created),
        },
    )

    return [PayrollResponse.model_validate(r) for r in created]


# ─────────────────────────────────────────────────────────────────────────────
# Get by ID
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{payroll_id}",
    response_model=PayrollResponse,
    summary="Get Payroll Record",
    description="Returns a single payroll record by ID.",
)
async def get_payroll_by_id(
    payroll_id: Annotated[int, Path(description="ID of the payroll record to retrieve.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> PayrollResponse:
    """Retrieve a payroll record by its ID."""
    require_table_access(current_user, "payroll")

    record = await get_payroll(current_user.org_id, payroll_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payroll record not found.",
        )

    return PayrollResponse.model_validate(record)


# ─────────────────────────────────────────────────────────────────────────────
# Update (manual adjustments)
# ─────────────────────────────────────────────────────────────────────────────

@router.patch(
    "/{payroll_id}",
    response_model=PayrollResponse,
    summary="Update Payroll Record",
    description="Updates an existing payroll record (manual adjustments). Recalculates net_salary if bonus/allowance/deductions change.",
)
async def update_payroll_by_id(
    payroll_id: Annotated[int, Path(description="ID of the payroll record to update.")],
    req: PayrollUpdate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> PayrollResponse:
    """Update a payroll record with manual adjustments."""
    require_write_access(current_user, "payroll")

    # Verify the record exists
    existing = await get_payroll(current_user.org_id, payroll_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payroll record not found.",
        )

    # Build update dict with only the provided fields
    values: dict[str, Any] = {}
    old_values: dict[str, Any] = {}

    for field in ("bonus", "allowance", "deductions", "status", "notes"):
        val = getattr(req, field, None)
        if val is not None:
            values[field] = val
            old_values[field] = str(existing.get(field, ""))

    # Recalculate net_salary if financial fields changed
    if any(k in values for k in ("bonus", "allowance", "deductions")):
        from decimal import Decimal

        current_bonus = Decimal(str(values.get("bonus", existing.get("bonus", 0))))
        current_allowance = Decimal(str(values.get("allowance", existing.get("allowance", 0))))
        current_deductions = Decimal(str(values.get("deductions", existing.get("deductions", 0))))

        old_bonus = Decimal(str(existing.get("bonus", 0)))
        old_allowance = Decimal(str(existing.get("allowance", 0)))
        old_deductions = Decimal(str(existing.get("deductions", 0)))
        old_gross = Decimal(str(existing.get("gross_salary", 0)))
        old_net = Decimal(str(existing.get("net_salary", 0)))

        # absence_deduction is invariant (determined by attendance data)
        absence_deduction = old_gross - old_net - old_deductions

        # Recalculate gross with new bonus/allowance replacing old ones
        new_gross = old_gross - old_bonus - old_allowance + current_bonus + current_allowance
        new_gross = new_gross.quantize(Decimal("0.01"))

        # Recalculate net
        new_net = max(Decimal("0"), new_gross - absence_deduction - current_deductions).quantize(Decimal("0.01"))

        values["gross_salary"] = str(new_gross)
        values["net_salary"] = str(new_net)

    updated = await _update_payroll(
        org_id=current_user.org_id,
        payroll_id=payroll_id,
        values=values,
    )

    full_record = await get_payroll(current_user.org_id, payroll_id)

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="updated",
        entity_type="payroll",
        entity_id=payroll_id,
        old_value=old_values,
        new_value={k: str(v) for k, v in values.items()},
    )

    return PayrollResponse.model_validate(full_record or updated)


# ─────────────────────────────────────────────────────────────────────────────
# Delete
# ─────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/{payroll_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Payroll Record",
    description="Deletes a payroll record. Requires write access.",
)
async def delete_payroll_by_id(
    payroll_id: Annotated[int, Path(description="ID of the payroll record to delete.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, str]:
    """Delete a payroll record."""
    require_write_access(current_user, "payroll")

    existing = await get_payroll(current_user.org_id, payroll_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payroll record not found.",
        )

    await _delete_payroll(current_user.org_id, payroll_id)

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="deleted",
        entity_type="payroll",
        entity_id=payroll_id,
    )

    return {"message": f"Payroll record {payroll_id} has been deleted."}