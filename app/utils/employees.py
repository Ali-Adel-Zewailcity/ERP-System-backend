"""
Employees utility — CRUD helper functions for employee management.

All functions accept explicit parameters so they remain testable
without depending on FastAPI request objects.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from app.db.database import database
from app.schema.hr import employees


async def create_employee(
    org_id: int,
    full_name: str,
    employee_number: str,
    email: str,
    salary: Decimal,
    hire_date: date,
    phone_number: str | None = None,
    job_title: str | None = None,
    department: str | None = None,
    status: str = "active",
) -> dict[str, Any]:
    """Insert a new employee and return the full record."""
    query = """
        INSERT INTO employees (org_id, full_name, employee_number, email,
                               phone_number, job_title, department,
                               salary, hire_date, status)
        VALUES (:org_id, :full_name, :employee_number, :email,
                :phone_number, :job_title, :department,
                :salary, :hire_date, :status)
        RETURNING id, org_id, full_name, employee_number, email,
                  phone_number, job_title, department,
                  salary, hire_date, status, profile_photo_path,
                  created_at, updated_at
    """
    return await database.fetch_one(query, {
        "org_id": org_id,
        "full_name": full_name,
        "employee_number": employee_number,
        "email": email,
        "phone_number": phone_number,
        "job_title": job_title,
        "department": department,
        "salary": str(salary),
        "hire_date": hire_date.isoformat(),
        "status": status,
    })


async def get_employee(org_id: int, employee_id: int) -> dict[str, Any] | None:
    """Fetch a single employee by ID scoped to the organization."""
    query = """
        SELECT id, org_id, full_name, employee_number, email,
               phone_number, job_title, department,
               salary, hire_date, status, profile_photo_path,
               created_at, updated_at
        FROM employees
        WHERE id = :id AND org_id = :org_id
    """
    result = await database.fetch_one(query, {"id": employee_id, "org_id": org_id})
    return dict(result) if result else None


SORTABLE_COLUMNS = frozenset({
    "employee_number", "full_name", "department",
    "salary", "hire_date", "status",
})


async def list_all_employees_for_org(
    org_id: int,
    search: str | None = None,
    department: str | None = None,
    status: str | None = None,
    hire_date_from: str | None = None,
    hire_date_to: str | None = None,
    sort_by: str = "id",
    sort_order: str = "asc",
) -> list[dict[str, Any]]:
    """Return ALL employees for an org (unpaginated) with optional filters."""
    conditions = ["org_id = :org_id"]
    params: dict[str, Any] = {"org_id": org_id}

    if search:
        conditions.append(
            "(full_name LIKE :search OR employee_number LIKE :search "
            "OR email LIKE :search OR phone_number LIKE :search "
            "OR job_title LIKE :search)"
        )
        params["search"] = f"%{search}%"

    if department:
        conditions.append("department = :department")
        params["department"] = department

    if status:
        conditions.append("status = :status")
        params["status"] = status

    if hire_date_from:
        conditions.append("hire_date >= :hire_date_from")
        params["hire_date_from"] = hire_date_from

    if hire_date_to:
        conditions.append("hire_date <= :hire_date_to")
        params["hire_date_to"] = hire_date_to

    where_clause = " AND ".join(conditions)

    if sort_by not in SORTABLE_COLUMNS:
        sort_by = "id"
    order_dir = "DESC" if sort_order.lower() == "desc" else "ASC"

    query = f"""
        SELECT id, org_id, full_name, employee_number, email,
               phone_number, job_title, department,
               salary, hire_date, status, profile_photo_path,
               created_at, updated_at
        FROM employees
        WHERE {where_clause}
        ORDER BY {sort_by} {order_dir}, id
    """
    rows = await database.fetch_all(query, params)
    return [dict(r) for r in rows]


async def list_employees(
    org_id: int,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    department: str | None = None,
    status: str | None = None,
    hire_date_from: str | None = None,
    hire_date_to: str | None = None,
    sort_by: str = "id",
    sort_order: str = "asc",
) -> tuple[list[dict[str, Any]], int]:
    """
    Return a paginated, filtered list of employees and the total count.

    Returns
    -------
    (rows, total_count)
    """
    conditions = ["org_id = :org_id"]
    params: dict[str, Any] = {"org_id": org_id}

    if search:
        conditions.append(
            "(full_name LIKE :search OR employee_number LIKE :search "
            "OR email LIKE :search OR phone_number LIKE :search "
            "OR job_title LIKE :search)"
        )
        params["search"] = f"%{search}%"

    if department:
        conditions.append("department = :department")
        params["department"] = department

    if status:
        conditions.append("status = :status")
        params["status"] = status

    if hire_date_from:
        conditions.append("hire_date >= :hire_date_from")
        params["hire_date_from"] = hire_date_from

    if hire_date_to:
        conditions.append("hire_date <= :hire_date_to")
        params["hire_date_to"] = hire_date_to

    where_clause = " AND ".join(conditions)

    # Total count
    count_query = f"SELECT COUNT(*) FROM employees WHERE {where_clause}"
    total = (await database.fetch_val(count_query, params)) or 0

    # Sorting (whitelist to prevent SQL injection)
    if sort_by not in SORTABLE_COLUMNS:
        sort_by = "id"
    order_dir = "DESC" if sort_order.lower() == "desc" else "ASC"

    # Paginated rows
    offset = (page - 1) * page_size
    data_query = f"""
        SELECT id, org_id, full_name, employee_number, email,
               phone_number, job_title, department,
               salary, hire_date, status, profile_photo_path,
               created_at, updated_at
        FROM employees
        WHERE {where_clause}
        ORDER BY {sort_by} {order_dir}, id
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = page_size
    params["offset"] = offset
    rows = await database.fetch_all(data_query, params)

    return [dict(r) for r in rows], total


async def get_employee_stats(
    org_id: int,
) -> dict[str, int]:
    """Return summary statistics for employees in the given organization."""
    query = """
        SELECT
            COUNT(*)                                              AS total,
            SUM(CASE WHEN status = 'active'   THEN 1 ELSE 0 END)  AS active,
            SUM(CASE WHEN status = 'resigned' THEN 1 ELSE 0 END)  AS resigned,
            COUNT(DISTINCT department)                             AS departments
        FROM employees
        WHERE org_id = :org_id
    """
    row = await database.fetch_one(query, {"org_id": org_id})
    return {
        "total":       row["total"] or 0,
        "active":      row["active"] or 0,
        "resigned":    row["resigned"] or 0,
        "departments": row["departments"] or 0,
    }


async def update_employee(
    org_id: int,
    employee_id: int,
    values: dict[str, Any],
) -> dict[str, Any] | None:
    """Update an employee record and return the updated row, or None if not found."""
    if not values:
        return await get_employee(org_id, employee_id)

    set_clause = ", ".join(f"{k} = :{k}" for k in values)
    values["id"] = employee_id
    values["org_id"] = org_id

    query = f"""
        UPDATE employees
        SET {set_clause}
        WHERE id = :id AND org_id = :org_id
        RETURNING id, org_id, full_name, employee_number, email,
                  phone_number, job_title, department,
                  salary, hire_date, status, profile_photo_path,
                  created_at, updated_at
    """
    return await database.fetch_one(query, values)


async def update_employee_photo(
    org_id: int,
    employee_id: int,
    photo_path: str | None,
) -> dict[str, Any] | None:
    query = """
        UPDATE employees
        SET profile_photo_path = :photo_path
        WHERE id = :id AND org_id = :org_id
        RETURNING id, org_id, full_name, employee_number, email,
                  phone_number, job_title, department,
                  salary, hire_date, status, profile_photo_path,
                  created_at, updated_at
    """
    return await database.fetch_one(query, {
        "photo_path": photo_path,
        "id": employee_id,
        "org_id": org_id,
    })


async def delete_employee(org_id: int, employee_id: int) -> bool:
    """Delete an employee. Returns True if a row was deleted."""
    query = "DELETE FROM employees WHERE id = :id AND org_id = :org_id"
    result = await database.execute(query, {"id": employee_id, "org_id": org_id})
    return bool(result)
