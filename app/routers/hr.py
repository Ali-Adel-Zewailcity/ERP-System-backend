"""
HR Router — Employee management endpoints.

Endpoints
---------
  POST   /employees/               - Create a new employee
  GET    /employees/               - List employees (paginated, filterable)
  GET    /employees/stats          - Employee summary statistics
  GET    /employees/export/template - Download import template (XLSX)
  POST   /employees/import         - Import employees from file
  GET    /employees/export         - Export employees to file
  POST   /employees/bulk/delete    - Delete multiple employees
  POST   /employees/bulk/status    - Change status of multiple employees
  GET    /employees/{employee_id}  - Get a single employee by ID
  PUT    /employees/{employee_id}  - Update an employee
  DELETE /employees/{employee_id}  - Delete an employee
"""

import io
import json
import os
from datetime import date
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, status, Path, Query, UploadFile, File, Form, Response, Request

from app.db.database import database
from app.models.auth import UserResponse
from app.models.hr import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse,
    EmployeeListResponse,
    BulkDeleteRequest,
    BulkStatusRequest,
    ImportSummary,
    AttachmentResponse,
    ActivityLogResponse,
)
from app.utils.dependency import get_current_user, require_organization_member
from app.utils.roles import require_table_access, require_write_access
from app.utils.employees import (
    create_employee,
    get_employee,
    get_employee_stats,
    list_employees,
    update_employee,
    delete_employee,
    update_employee_photo,
    list_all_employees_for_org,
    SORTABLE_COLUMNS,
)
from app.utils.import_export import (
    generate_import_template,
    parse_import_file,
    validate_import_rows,
    generate_export,
    TEMPLATE_HEADERS,
)
from app.utils.file_storage import (
    save_photo,
    remove_photo,
    save_attachment,
    remove_attachment,
    validate_photo,
    validate_attachment,
)
from app.utils.activity_log import log_activity
from app.schema.hr import employee_attachments
from app.schema.auth import activity_logs


router = APIRouter(prefix="/employees", tags=["Employees"])


# ─────────────────────────────────────────────────────────────────────────────
# Create
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=EmployeeResponse,
    summary="Create Employee",
    description="Creates a new employee record scoped to the current user's organization.",
)
async def create_new_employee(
    req: EmployeeCreate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> EmployeeResponse:
    """Create a new employee within the current organization."""
    require_write_access(current_user, "employees")

    # Check for unique employee_number
    existing_number = await database.fetch_one(
        "SELECT id FROM employees WHERE org_id = :org_id AND employee_number = :employee_number",
        {"org_id": current_user.org_id, "employee_number": req.employee_number},
    )
    if existing_number:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An employee with this employee number already exists.",
        )

    # Check for unique email
    existing_email = await database.fetch_one(
        "SELECT id FROM employees WHERE org_id = :org_id AND email = :email",
        {"org_id": current_user.org_id, "email": req.email},
    )
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An employee with this email address already exists.",
        )

    new_employee = await create_employee(
        org_id=current_user.org_id,
        full_name=req.full_name,
        employee_number=req.employee_number,
        email=req.email,
        salary=req.salary,
        hire_date=req.hire_date,
        phone_number=req.phone_number,
        job_title=req.job_title,
        department=req.department,
        status=req.status,
    )

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="created",
        entity_type="employee",
        entity_id=new_employee["id"],
        new_value={"full_name": req.full_name, "employee_number": req.employee_number},
    )

    return EmployeeResponse.model_validate(new_employee)


# ─────────────────────────────────────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/stats",
    summary="Employee statistics",
    description="Returns total, active, resigned counts and distinct department count.",
)
async def employee_stats(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, int]:
    """Return summary statistics for employees in the user's organization."""
    require_table_access(current_user, "employees")
    return await get_employee_stats(current_user.org_id)


# ─────────────────────────────────────────────────────────────────────────────
# List (paginated, filterable)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=EmployeeListResponse,
    summary="List Employees",
    description=(
        "Returns a paginated list of employees scoped to the current user's "
        "organization. Supports search, department filter, and status filter."
    ),
)
async def list_all_employees(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    department: Annotated[str | None, Query(max_length=100)] = None,
    status: Annotated[str | None, Query(pattern="^(active|resigned)?$")] = None,
    hire_date_from: Annotated[date | None, Query(description="Filter: hire date on or after (YYYY-MM-DD)")] = None,
    hire_date_to: Annotated[date | None, Query(description="Filter: hire date on or before (YYYY-MM-DD)")] = None,
    sort_by: Annotated[str | None, Query(description=f"Sort column. One of: {', '.join(sorted(SORTABLE_COLUMNS))}")] = None,
    sort_order: Annotated[str | None, Query(pattern="^(asc|desc)?$", description="Sort direction: asc or desc")] = None,
) -> EmployeeListResponse:
    """List employees with pagination and optional filters."""
    require_table_access(current_user, "employees")

    rows, total = await list_employees(
        org_id=current_user.org_id,
        page=page,
        page_size=page_size,
        search=search,
        department=department,
        status=status,
        hire_date_from=hire_date_from.isoformat() if hire_date_from else None,
        hire_date_to=hire_date_to.isoformat() if hire_date_to else None,
        sort_by=sort_by or "id",
        sort_order=sort_order or "asc",
    )

    items = [EmployeeResponse.model_validate(r) for r in rows]
    pages = (total + page_size - 1) // page_size if total else 0

    return EmployeeListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Export template
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/export/template",
    summary="Download Import Template",
    description="Download an XLSX template for importing employees.",
)
async def download_import_template(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
):
    """Return an XLSX template file."""
    require_table_access(current_user, "employees")
    content = generate_import_template()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=employee_import_template.xlsx"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Import
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/import",
    response_model=ImportSummary,
    summary="Import Employees",
    description="Import employees from an XLSX or CSV file. Invalid rows are skipped.",
)
async def import_employees(
    file: Annotated[UploadFile, File(description="XLSX or CSV file")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> ImportSummary:
    """Import employees from a file. Valid rows are imported, invalid rows are skipped."""
    require_write_access(current_user, "employees")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty.")

    try:
        rows = parse_import_file(content, file.filename or "import.xlsx")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No data found in file.")

    # Fetch existing employees for uniqueness checks
    existing = await database.fetch_all(
        "SELECT employee_number, email FROM employees WHERE org_id = :org_id",
        {"org_id": current_user.org_id},
    )
    existing_list = [dict(r) for r in existing]

    valid_rows, errors = validate_import_rows(rows, existing_list)

    imported = 0
    for row in valid_rows:
        try:
            from datetime import date as _date_cls
            hire_date_raw = row["hire_date"]
            hire_date = _date_cls.fromisoformat(hire_date_raw) if isinstance(hire_date_raw, str) else hire_date_raw

            await create_employee(
                org_id=current_user.org_id,
                full_name=row["full_name"],
                employee_number=row["employee_number"],
                email=row["email"],
                salary=row["salary"],
                hire_date=hire_date,
                phone_number=row.get("phone_number"),
                job_title=row.get("job_title"),
                department=row.get("department"),
                status=row.get("status", "active"),
            )
            imported += 1
        except Exception as exc:
            name = row.get("full_name", "unknown")
            reason = str(exc) if str(exc) else "Unknown error"
            errors.append({"row": 0, "reasons": f"Failed to import '{name}': {reason}"})

    return ImportSummary(
        total=len(rows),
        imported=imported,
        failed=len(rows) - imported,
        errors=errors,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/export",
    summary="Export Employees",
    description="Export employees to XLSX or CSV. Supports filtered or all employees.",
)
async def export_employees(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    format: Annotated[str, Query(pattern="^(xlsx|csv)$")] = "xlsx",
    scope: Annotated[str, Query(pattern="^(filtered|all)$")] = "filtered",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    department: Annotated[str | None, Query(max_length=100)] = None,
    status_param: Annotated[str | None, Query(alias="status", pattern="^(active|resigned)?$")] = None,
    hire_date_from: Annotated[date | None, Query()] = None,
    hire_date_to: Annotated[date | None, Query()] = None,
    sort_by: Annotated[str | None, Query()] = None,
    sort_order: Annotated[str | None, Query(pattern="^(asc|desc)?$")] = None,
):
    """Export employees to XLSX or CSV."""
    require_table_access(current_user, "employees")

    if scope == "filtered":
        rows, _ = await list_employees(
            org_id=current_user.org_id,
            page=page,
            page_size=page_size,
            search=search,
            department=department,
            status=status_param,
            hire_date_from=hire_date_from.isoformat() if hire_date_from else None,
            hire_date_to=hire_date_to.isoformat() if hire_date_to else None,
            sort_by=sort_by or "id",
            sort_order=sort_order or "asc",
        )
    else:
        rows = await list_all_employees_for_org(
            org_id=current_user.org_id,
            search=search,
            department=department,
            status=status_param,
            hire_date_from=hire_date_from.isoformat() if hire_date_from else None,
            hire_date_to=hire_date_to.isoformat() if hire_date_to else None,
            sort_by=sort_by or "id",
            sort_order=sort_order or "asc",
        )

    content = generate_export([dict(r) for r in rows], format)

    if format == "csv":
        media_type = "text/csv"
        filename = "employees.csv"
    else:
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "employees.xlsx"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bulk delete
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/bulk/delete",
    summary="Bulk Delete Employees",
    description="Delete multiple employees by ID. Requires write access.",
)
async def bulk_delete_employees(
    req: BulkDeleteRequest,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, object]:
    """Delete multiple employees at once."""
    require_write_access(current_user, "employees")

    if not req.ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No employee IDs provided.")

    placeholders = ",".join(f":id_{i}" for i in range(len(req.ids)))
    params: dict[str, object] = {f"id_{i}": uid for i, uid in enumerate(req.ids)}
    params["org_id"] = current_user.org_id
    query = f"DELETE FROM employees WHERE id IN ({placeholders}) AND org_id = :org_id"
    result = await database.execute(query, params)

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="bulk_deleted",
        entity_type="employee",
        new_value={"ids": list(req.ids)},
    )

    return {"deleted": result, "message": f"{result} employee(s) deleted."}


# ─────────────────────────────────────────────────────────────────────────────
# Bulk status change
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/bulk/status",
    summary="Bulk Status Change",
    description="Change the status of multiple employees at once.",
)
async def bulk_change_status(
    req: BulkStatusRequest,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, object]:
    """Change the status of multiple employees at once."""
    require_write_access(current_user, "employees")

    if not req.ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No employee IDs provided.")

    placeholders = ",".join(f":id_{i}" for i in range(len(req.ids)))
    params: dict[str, object] = {f"id_{i}": uid for i, uid in enumerate(req.ids)}
    params["org_id"] = current_user.org_id
    params["status"] = req.status
    query = f"UPDATE employees SET status = :status WHERE id IN ({placeholders}) AND org_id = :org_id"
    result = await database.execute(query, params)

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="bulk_status_changed",
        entity_type="employee",
        new_value={"ids": list(req.ids), "status": req.status},
    )

    return {"updated": result, "message": f"{result} employee(s) updated to '{req.status}'."}


# ─────────────────────────────────────────────────────────────────────────────
# Get by ID
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{employee_id}",
    response_model=EmployeeResponse,
    summary="Get Employee",
    description="Returns a single employee record by ID.",
)
async def get_employee_by_id(
    employee_id: Annotated[int, Path(description="ID of the employee to retrieve.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> EmployeeResponse:
    """Retrieve an employee by their ID."""
    require_table_access(current_user, "employees")

    employee = await get_employee(current_user.org_id, employee_id)
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found.",
        )

    return EmployeeResponse.model_validate(employee)


# ─────────────────────────────────────────────────────────────────────────────
# Update
# ─────────────────────────────────────────────────────────────────────────────

@router.put(
    "/{employee_id}",
    response_model=EmployeeResponse,
    summary="Update Employee",
    description="Updates an existing employee record. Only provided fields are changed.",
)
async def update_employee_by_id(
    employee_id: Annotated[int, Path(description="ID of the employee to update.")],
    req: EmployeeUpdate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> EmployeeResponse:
    """Update an employee record."""
    require_write_access(current_user, "employees")

    # Verify the employee exists
    existing = await get_employee(current_user.org_id, employee_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found.",
        )

    # Build update dict with only the provided fields
    values = {}
    for field in ("full_name", "employee_number", "email", "phone_number",
                  "job_title", "department", "hire_date", "status"):
        val = getattr(req, field, None)
        if val is not None:
            if field == "hire_date":
                values[field] = val.isoformat()
            else:
                values[field] = val

    if req.salary is not None:
        values["salary"] = str(req.salary)

    # Check uniqueness for employee_number and email if changed
    if "employee_number" in values:
        existing_number = await database.fetch_one(
            "SELECT id FROM employees WHERE org_id = :org_id AND employee_number = :employee_number AND id != :id",
            {"org_id": current_user.org_id, "employee_number": values["employee_number"], "id": employee_id},
        )
        if existing_number:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An employee with this employee number already exists.",
            )

    if "email" in values:
        existing_email = await database.fetch_one(
            "SELECT id FROM employees WHERE org_id = :org_id AND email = :email AND id != :id",
            {"org_id": current_user.org_id, "email": values["email"], "id": employee_id},
        )
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An employee with this email address already exists.",
            )

    updated = await update_employee(
        org_id=current_user.org_id,
        employee_id=employee_id,
        values=values,
    )

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="updated",
        entity_type="employee",
        entity_id=employee_id,
        old_value={k: str(existing[k]) for k in values if k in existing},
        new_value={k: str(v) for k, v in values.items()},
    )

    return EmployeeResponse.model_validate(updated)


# ─────────────────────────────────────────────────────────────────────────────
# Delete
# ─────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/{employee_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Employee",
    description="Deletes an employee record. Requires write access (manager+).",
)
async def delete_employee_by_id(
    employee_id: Annotated[int, Path(description="ID of the employee to delete.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, str]:
    """Delete an employee record."""
    require_write_access(current_user, "employees")

    existing = await get_employee(current_user.org_id, employee_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found.",
        )

    full_name = existing.get("full_name", "Unknown")
    await delete_employee(current_user.org_id, employee_id)

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="deleted",
        entity_type="employee",
        entity_id=employee_id,
        old_value={"full_name": full_name},
    )

    return {"message": f"Employee {employee_id} has been deleted."}


# ─────────────────────────────────────────────────────────────────────────────
# Profile Photo
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/{employee_id}/photo",
    status_code=status.HTTP_200_OK,
    response_model=EmployeeResponse,
    summary="Upload Profile Photo",
    description="Upload or replace an employee's profile photo.",
)
async def upload_employee_photo(
    employee_id: Annotated[int, Path(description="ID of the employee.")],
    file: Annotated[UploadFile, File(description="Profile photo (JPEG, PNG, GIF, WebP)")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    request: Request,
) -> EmployeeResponse:
    """Upload or replace an employee's profile photo."""
    require_write_access(current_user, "employees")

    employee = await get_employee(current_user.org_id, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found.")

    content = await file.read()
    content_type = file.content_type or "image/jpeg"

    try:
        validate_photo(content_type, len(content))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Remove old photo if exists
    if employee.get("profile_photo_path"):
        await remove_photo(employee["profile_photo_path"])

    file_path = await save_photo(current_user.org_id, employee_id, content, file.filename or "photo.jpg")
    updated = await update_employee_photo(current_user.org_id, employee_id, file_path)

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="photo_updated",
        entity_type="employee",
        entity_id=employee_id,
    )

    return EmployeeResponse.model_validate(updated)


@router.delete(
    "/{employee_id}/photo",
    status_code=status.HTTP_200_OK,
    response_model=EmployeeResponse,
    summary="Remove Profile Photo",
    description="Remove an employee's profile photo (falls back to default avatar).",
)
async def remove_employee_photo(
    employee_id: Annotated[int, Path(description="ID of the employee.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> EmployeeResponse:
    """Remove the employee's profile photo."""
    require_write_access(current_user, "employees")

    employee = await get_employee(current_user.org_id, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found.")

    if employee.get("profile_photo_path"):
        await remove_photo(employee["profile_photo_path"])

    updated = await update_employee_photo(current_user.org_id, employee_id, None)

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="photo_removed",
        entity_type="employee",
        entity_id=employee_id,
    )

    return EmployeeResponse.model_validate(updated)


@router.get(
    "/{employee_id}/photo",
    summary="Get Profile Photo",
    description="Serve the employee's profile photo file.",
)
async def get_employee_photo(
    employee_id: Annotated[int, Path(description="ID of the employee.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
):
    """Return the employee's profile photo file."""
    require_table_access(current_user, "employees")

    employee = await get_employee(current_user.org_id, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found.")

    if not employee.get("profile_photo_path"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No profile photo uploaded.")

    file_path = employee["profile_photo_path"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo file not found on disk.")

    with open(file_path, "rb") as f:
        content = f.read()

    ext = os.path.splitext(file_path)[1].lower()
    media_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                 ".gif": "image/gif", ".webp": "image/webp"}
    media_type = media_map.get(ext, "application/octet-stream")

    return Response(content=content, media_type=media_type)


# ─────────────────────────────────────────────────────────────────────────────
# Attachments
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/{employee_id}/attachments",
    status_code=status.HTTP_201_CREATED,
    response_model=AttachmentResponse,
    summary="Upload Attachment",
    description="Attach a document to an employee (CV, Contract, National ID, Passport, Other).",
)
async def upload_employee_attachment(
    employee_id: Annotated[int, Path(description="ID of the employee.")],
    file: Annotated[UploadFile, File(description="File to attach.")],
    file_type: Annotated[str, Form(pattern="^(cv|contract|national_id|passport|other)$")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> AttachmentResponse:
    """Upload a file attachment for an employee."""
    require_write_access(current_user, "employees")

    employee = await get_employee(current_user.org_id, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found.")

    content = await file.read()
    content_type = file.content_type or "application/octet-stream"

    try:
        validate_attachment(content_type, len(content))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Insert DB record first to get the attachment ID
    insert_query = employee_attachments.insert().values(
        employee_id=employee_id,
        file_type=file_type,
        file_name=file.filename or "file",
        file_path="",  # placeholder, updated after save
        content_type=content_type,
        file_size=len(content),
        uploaded_by=current_user.id,
    ).returning(*employee_attachments.c)

    record = await database.fetch_one(insert_query)
    if not record:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create attachment record.")

    file_path = await save_attachment(
        current_user.org_id, employee_id, record["id"], content, file.filename or "file"
    )

    # Update the file_path
    update_query = employee_attachments.update().where(
        employee_attachments.c.id == record["id"]
    ).values(file_path=file_path)
    await database.execute(update_query)

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="attachment_uploaded",
        entity_type="employee_attachment",
        entity_id=record["id"],
        new_value={"file_name": file.filename, "file_type": file_type},
    )

    record = dict(record)
    record["file_path"] = file_path
    return AttachmentResponse.model_validate(record)


@router.get(
    "/{employee_id}/attachments",
    response_model=list[AttachmentResponse],
    summary="List Attachments",
    description="List all attachments for an employee.",
)
async def list_employee_attachments(
    employee_id: Annotated[int, Path(description="ID of the employee.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> list[AttachmentResponse]:
    """List all attachments for an employee."""
    require_table_access(current_user, "employees")

    query = employee_attachments.select().where(
        employee_attachments.c.employee_id == employee_id
    ).order_by(employee_attachments.c.created_at.desc())

    rows = await database.fetch_all(query)
    return [AttachmentResponse.model_validate(r) for r in rows]


@router.get(
    "/{employee_id}/attachments/{attachment_id}/download",
    summary="Download Attachment",
    description="Download an attachment file.",
)
async def download_employee_attachment(
    employee_id: Annotated[int, Path(description="ID of the employee.")],
    attachment_id: Annotated[int, Path(description="ID of the attachment.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
):
    """Download an attachment file."""
    require_table_access(current_user, "employees")

    query = employee_attachments.select().where(
        employee_attachments.c.id == attachment_id,
        employee_attachments.c.employee_id == employee_id,
    )
    record = await database.fetch_one(query)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found.")

    file_path = record["file_path"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found on disk.")

    with open(file_path, "rb") as f:
        content = f.read()

    filename = record["file_name"] or f"attachment_{attachment_id}"
    media_type = record["content_type"] or "application/octet-stream"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete(
    "/{employee_id}/attachments/{attachment_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Attachment",
    description="Delete an attachment. Admin/HR only.",
)
async def delete_employee_attachment(
    employee_id: Annotated[int, Path(description="ID of the employee.")],
    attachment_id: Annotated[int, Path(description="ID of the attachment.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, str]:
    """Delete an attachment and its file from disk."""
    require_write_access(current_user, "employees")

    query = employee_attachments.select().where(
        employee_attachments.c.id == attachment_id,
        employee_attachments.c.employee_id == employee_id,
    )
    record = await database.fetch_one(query)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found.")

    file_path = record["file_path"]
    if file_path:
        await remove_attachment(file_path)

    delete_query = employee_attachments.delete().where(employee_attachments.c.id == attachment_id)
    await database.execute(delete_query)

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="attachment_deleted",
        entity_type="employee_attachment",
        entity_id=attachment_id,
        old_value={"file_name": record["file_name"]},
    )

    return {"message": f"Attachment '{record['file_name']}' deleted."}


# ─────────────────────────────────────────────────────────────────────────────
# Activity Log
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{employee_id}/activity",
    response_model=list[ActivityLogResponse],
    summary="Employee Activity Log",
    description="View activity history for an employee.",
)
async def get_employee_activity(
    employee_id: Annotated[int, Path(description="ID of the employee.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> list[ActivityLogResponse]:
    """View the activity history for an employee."""
    require_table_access(current_user, "employees")

    query = (
        activity_logs.select()
        .where(
            activity_logs.c.org_id == current_user.org_id,
            activity_logs.c.entity_type == "employee",
            activity_logs.c.entity_id == employee_id,
        )
        .order_by(activity_logs.c.timestamp.desc())
        .limit(100)
    )
    rows = await database.fetch_all(query)
    return [ActivityLogResponse.model_validate(r) for r in rows]
