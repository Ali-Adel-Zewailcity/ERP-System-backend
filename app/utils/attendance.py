"""
Attendance utility — CRUD helper functions for attendance management.

All functions accept explicit parameters so they remain testable
without depending on FastAPI request objects.
"""

from datetime import date, time
from typing import Any

from app.db.database import database


SORTABLE_COLUMNS = frozenset({
    "attendance_date", "status", "employee_id",
})


async def create_attendance(
    org_id: int,
    employee_id: int,
    attendance_date: date,
    status: str,
    check_in_time: time | None = None,
    check_out_time: time | None = None,
    notes: str | None = None,
    source: str = "manual",
) -> dict[str, Any]:
    """Insert a new attendance record and return the full record."""
    query = """
        INSERT INTO attendance (org_id, employee_id, attendance_date,
                                check_in_time, check_out_time, status, notes, source)
        VALUES (:org_id, :employee_id, :attendance_date,
                :check_in_time, :check_out_time, :status, :notes, :source)
        RETURNING id, org_id, employee_id, attendance_date,
                  check_in_time, check_out_time, status, source, notes,
                  created_at, updated_at
    """
    result = await database.fetch_one(query, {
        "org_id": org_id,
        "employee_id": employee_id,
        "attendance_date": attendance_date.isoformat(),
        "check_in_time": check_in_time.isoformat() if check_in_time else None,
        "check_out_time": check_out_time.isoformat() if check_out_time else None,
        "status": status,
        "notes": notes,
        "source": source,
    })
    return dict(result)


async def get_attendance(org_id: int, attendance_id: int) -> dict[str, Any] | None:
    """Fetch a single attendance record by ID scoped to the organization."""
    query = """
        SELECT a.id, a.org_id, a.employee_id, a.attendance_date,
               a.check_in_time, a.check_out_time, a.status, a.source, a.notes,
               a.created_at, a.updated_at,
                e.full_name AS employee_name, e.employee_number, e.department
        FROM attendance a
        JOIN employees e ON a.employee_id = e.id
        WHERE a.id = :id AND a.org_id = :org_id
    """
    result = await database.fetch_one(query, {"id": attendance_id, "org_id": org_id})
    return dict(result) if result else None


async def list_attendance(
    org_id: int,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    status: str | None = None,
    attendance_date_from: str | None = None,
    attendance_date_to: str | None = None,
    department: str | None = None,
    sort_by: str = "attendance_date",
    sort_order: str = "desc",
) -> tuple[list[dict[str, Any]], int]:
    """
    Return a paginated, filtered list of attendance records and the total count.
    Filters: search by employee name, status, date range, department.
    """
    conditions = ["a.org_id = :org_id"]
    params: dict[str, Any] = {"org_id": org_id}

    if search:
        conditions.append("e.full_name LIKE :search")
        params["search"] = f"%{search}%"

    if status:
        conditions.append("a.status = :status")
        params["status"] = status

    if attendance_date_from:
        conditions.append("a.attendance_date >= :attendance_date_from")
        params["attendance_date_from"] = attendance_date_from

    if attendance_date_to:
        conditions.append("a.attendance_date <= :attendance_date_to")
        params["attendance_date_to"] = attendance_date_to

    if department:
        conditions.append("e.department = :department")
        params["department"] = department

    where_clause = " AND ".join(conditions)
    join_clause = "JOIN employees e ON a.employee_id = e.id"

    # Total count
    count_query = f"SELECT COUNT(*) FROM attendance a {join_clause} WHERE {where_clause}"
    total = (await database.fetch_val(count_query, params)) or 0

    # Sorting (whitelist to prevent SQL injection)
    if sort_by not in SORTABLE_COLUMNS:
        sort_by = "attendance_date"
    order_dir = "DESC" if sort_order.lower() == "desc" else "ASC"

    # Paginated rows
    offset = (page - 1) * page_size
    data_query = f"""
        SELECT a.id, a.org_id, a.employee_id, a.attendance_date,
               a.check_in_time, a.check_out_time, a.status, a.source, a.notes,
               a.created_at, a.updated_at,
                e.full_name AS employee_name, e.employee_number, e.department
        FROM attendance a
        {join_clause}
        WHERE {where_clause}
        ORDER BY a.{sort_by} {order_dir}, a.id
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = page_size
    params["offset"] = offset
    rows = await database.fetch_all(data_query, params)

    return [dict(r) for r in rows], total


async def update_attendance(
    org_id: int,
    attendance_id: int,
    values: dict[str, Any],
) -> dict[str, Any] | None:
    """Update an attendance record and return the updated row, or None if not found."""
    if not values:
        return await get_attendance(org_id, attendance_id)

    set_clause = ", ".join(f"{k} = :{k}" for k in values)
    values["id"] = attendance_id
    values["org_id"] = org_id

    query = f"""
        UPDATE attendance
        SET {set_clause}, updated_at = datetime('now')
        WHERE id = :id AND org_id = :org_id
        RETURNING id, org_id, employee_id, attendance_date,
                  check_in_time, check_out_time, status, source, notes,
                  created_at, updated_at
    """
    result = await database.fetch_one(query, values)
    return dict(result) if result else None


async def list_all_attendance_for_org(
    org_id: int,
    search: str | None = None,
    department: str | None = None,
    status: str | None = None,
    attendance_date_from: str | None = None,
    attendance_date_to: str | None = None,
    sort_by: str = "attendance_date",
    sort_order: str = "desc",
) -> list[dict[str, Any]]:
    """Return ALL attendance records for an org (unpaginated) with optional filters."""
    conditions = ["a.org_id = :org_id"]
    params: dict[str, Any] = {"org_id": org_id}

    if search:
        conditions.append("e.full_name LIKE :search")
        params["search"] = f"%{search}%"

    if department:
        conditions.append("e.department = :department")
        params["department"] = department

    if status:
        conditions.append("a.status = :status")
        params["status"] = status

    if attendance_date_from:
        conditions.append("a.attendance_date >= :attendance_date_from")
        params["attendance_date_from"] = attendance_date_from

    if attendance_date_to:
        conditions.append("a.attendance_date <= :attendance_date_to")
        params["attendance_date_to"] = attendance_date_to

    where_clause = " AND ".join(conditions)

    if sort_by not in SORTABLE_COLUMNS:
        sort_by = "attendance_date"
    order_dir = "DESC" if sort_order.lower() == "desc" else "ASC"

    query = f"""
        SELECT a.id, a.org_id, a.employee_id, a.attendance_date,
               a.check_in_time, a.check_out_time, a.status, a.source, a.notes,
               a.created_at, a.updated_at,
                e.full_name AS employee_name, e.employee_number, e.department
        FROM attendance a
        JOIN employees e ON a.employee_id = e.id
        WHERE {where_clause}
        ORDER BY a.{sort_by} {order_dir}, a.id
    """
    rows = await database.fetch_all(query, params)
    return [dict(r) for r in rows]


async def delete_attendance(org_id: int, attendance_id: int) -> bool:
    """Delete an attendance record. Returns True if a row was deleted."""
    query = "DELETE FROM attendance WHERE id = :id AND org_id = :org_id"
    result = await database.execute(query, {"id": attendance_id, "org_id": org_id})
    return bool(result)
