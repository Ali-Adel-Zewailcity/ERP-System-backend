from datetime import date
from typing import Any

from app.db.database import database


SORTABLE_COLUMNS = frozenset({
    "start_date", "end_date", "status", "leave_type", "total_days", "requested_at",
})


async def create_leave(
    org_id: int,
    employee_id: int,
    leave_type: str,
    start_date: date,
    end_date: date,
    total_days: int,
    reason: str | None = None,
) -> dict[str, Any]:
    """Insert a new leave request and return the full record."""
    query = """
        INSERT INTO leave_requests (employee_id, leave_type, start_date,
                                     end_date, total_days, reason)
        VALUES (:employee_id, :leave_type, :start_date,
                :end_date, :total_days, :reason)
        RETURNING id, employee_id, approved_by, leave_type,
                  start_date, end_date, total_days, reason, status,
                  requested_at, resolved_at
    """
    result = await database.fetch_one(query, {
        "employee_id": employee_id,
        "leave_type": leave_type,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_days": total_days,
        "reason": reason,
    })
    return dict(result)


async def get_leave(org_id: int, leave_id: int) -> dict[str, Any] | None:
    """Fetch a single leave request by ID scoped to the organization."""
    query = """
        SELECT lr.id, lr.employee_id, lr.approved_by,
               lr.leave_type, lr.start_date, lr.end_date,
               lr.total_days, lr.reason, lr.status,
               lr.requested_at, lr.resolved_at,
               e.full_name AS employee_name, e.department,
               au.username AS approver_name
        FROM leave_requests lr
        JOIN employees e ON lr.employee_id = e.id
        LEFT JOIN users au ON lr.approved_by = au.id
        WHERE lr.id = :id AND e.org_id = :org_id
    """
    result = await database.fetch_one(query, {"id": leave_id, "org_id": org_id})
    return dict(result) if result else None


async def list_leaves(
    org_id: int,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    status: str | None = None,
    leave_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    department: str | None = None,
    sort_by: str = "requested_at",
    sort_order: str = "desc",
) -> tuple[list[dict[str, Any]], int]:
    """Return a paginated, filtered list of leave requests and total count."""
    conditions = ["e.org_id = :org_id"]
    params: dict[str, Any] = {"org_id": org_id}

    if search:
        conditions.append("e.full_name LIKE :search")
        params["search"] = f"%{search}%"

    if status:
        conditions.append("lr.status = :status")
        params["status"] = status

    if leave_type:
        conditions.append("lr.leave_type = :leave_type")
        params["leave_type"] = leave_type

    if date_from:
        conditions.append("lr.start_date >= :date_from")
        params["date_from"] = date_from

    if date_to:
        conditions.append("lr.end_date <= :date_to")
        params["date_to"] = date_to

    if department:
        conditions.append("e.department = :department")
        params["department"] = department

    where_clause = " AND ".join(conditions)

    # Total count
    count_query = f"""
        SELECT COUNT(*)
        FROM leave_requests lr
        JOIN employees e ON lr.employee_id = e.id
        WHERE {where_clause}
    """
    total = (await database.fetch_val(count_query, params)) or 0

    # Sorting (whitelist to prevent SQL injection)
    if sort_by not in SORTABLE_COLUMNS:
        sort_by = "requested_at"
    order_dir = "DESC" if sort_order.lower() == "desc" else "ASC"

    # Paginated rows
    offset = (page - 1) * page_size
    data_query = f"""
        SELECT lr.id, lr.employee_id, lr.approved_by,
               lr.leave_type, lr.start_date, lr.end_date,
               lr.total_days, lr.reason, lr.status,
               lr.requested_at, lr.resolved_at,
               e.full_name AS employee_name, e.department,
               au.username AS approver_name
        FROM leave_requests lr
        JOIN employees e ON lr.employee_id = e.id
        LEFT JOIN users au ON lr.approved_by = au.id
        WHERE {where_clause}
        ORDER BY lr.{sort_by} {order_dir}, lr.id
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = page_size
    params["offset"] = offset
    rows = await database.fetch_all(data_query, params)

    return [dict(r) for r in rows], total


async def list_all_leaves_for_org(
    org_id: int,
    search: str | None = None,
    status: str | None = None,
    leave_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    department: str | None = None,
    sort_by: str = "requested_at",
    sort_order: str = "desc",
) -> list[dict[str, Any]]:
    """Return ALL leave requests for an org (unpaginated) with optional filters."""
    conditions = ["e.org_id = :org_id"]
    params: dict[str, Any] = {"org_id": org_id}

    if search:
        conditions.append("e.full_name LIKE :search")
        params["search"] = f"%{search}%"

    if status:
        conditions.append("lr.status = :status")
        params["status"] = status

    if leave_type:
        conditions.append("lr.leave_type = :leave_type")
        params["leave_type"] = leave_type

    if date_from:
        conditions.append("lr.start_date >= :date_from")
        params["date_from"] = date_from

    if date_to:
        conditions.append("lr.end_date <= :date_to")
        params["date_to"] = date_to

    if department:
        conditions.append("e.department = :department")
        params["department"] = department

    where_clause = " AND ".join(conditions)

    if sort_by not in SORTABLE_COLUMNS:
        sort_by = "requested_at"
    order_dir = "DESC" if sort_order.lower() == "desc" else "ASC"

    query = f"""
        SELECT lr.id, lr.employee_id, lr.approved_by,
               lr.leave_type, lr.start_date, lr.end_date,
               lr.total_days, lr.reason, lr.status,
               lr.requested_at, lr.resolved_at,
               e.full_name AS employee_name, e.department,
               au.username AS approver_name
        FROM leave_requests lr
        JOIN employees e ON lr.employee_id = e.id
        LEFT JOIN users au ON lr.approved_by = au.id
        WHERE {where_clause}
        ORDER BY lr.{sort_by} {order_dir}, lr.id
    """
    rows = await database.fetch_all(query, params)
    return [dict(r) for r in rows]


async def update_leave(
    org_id: int,
    leave_id: int,
    values: dict[str, Any],
) -> dict[str, Any] | None:
    """Update a leave request and return the updated row, or None if not found."""
    if not values:
        return await get_leave(org_id, leave_id)

    set_clause = ", ".join(f"{k} = :{k}" for k in values)
    values["id"] = leave_id
    values["org_id"] = org_id

    query = f"""
        UPDATE leave_requests
        SET {set_clause}
        WHERE id = :id
          AND employee_id IN (SELECT id FROM employees WHERE org_id = :org_id)
        RETURNING id, employee_id, approved_by, leave_type,
                  start_date, end_date, total_days, reason, status,
                  requested_at, resolved_at
    """
    result = await database.fetch_one(query, values)
    if result:
        return await get_leave(org_id, result["id"])
    return None


async def delete_leave(org_id: int, leave_id: int) -> bool:
    """Delete a leave request. Returns True if a row was deleted."""
    query = """
        DELETE FROM leave_requests
        WHERE id = :id
          AND employee_id IN (SELECT id FROM employees WHERE org_id = :org_id)
    """
    result = await database.execute(query, {"id": leave_id, "org_id": org_id})
    return bool(result)
