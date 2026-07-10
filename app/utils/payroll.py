"""
Payroll utility — CRUD helper functions for payroll management.

All functions accept explicit parameters so they remain testable
without depending on FastAPI request objects.
"""

import calendar
from datetime import date, time
from decimal import Decimal
from typing import Any

from app.db.database import database


SORTABLE_COLUMNS = frozenset({
    "employee_name", "month", "year", "basic_salary",
    "net_salary", "status", "department",
})

OVERTIME_RATE = Decimal("1.25")  # 125 % of hourly base rate
BASE_HOURS_PER_DAY = 8
WORKING_DAYS_PER_MONTH = 22  # typical month excluding weekends


async def get_payroll(org_id: int, payroll_id: int) -> dict[str, Any] | None:
    """Fetch a single payroll record by ID (with JOINed employee data)."""
    query = """
        SELECT p.id, p.org_id, p.employee_id, e.full_name AS employee_name,
               e.department, e.salary AS basic_salary,
               p.month, p.year,
               p.days_worked, p.absences, p.overtime_hours,
               p.bonus, p.allowance, p.deductions,
               p.gross_salary, p.net_salary,
               p.status, p.notes, p.generated_at,
               p.created_at, p.updated_at
        FROM payroll p
        JOIN employees e ON e.id = p.employee_id
        WHERE p.id = :id AND p.org_id = :org_id
    """
    result = await database.fetch_one(query, {"id": payroll_id, "org_id": org_id})
    return dict(result) if result else None


async def list_payroll(
    org_id: int,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    department: str | None = None,
    month: int | None = None,
    year: int | None = None,
    status: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[dict[str, Any]], int]:
    """List payroll records with pagination and optional filters."""
    conditions = ["p.org_id = :org_id"]
    params: dict[str, Any] = {"org_id": org_id}

    if search:
        conditions.append("e.full_name LIKE :search")
        params["search"] = f"%{search}%"
    if department:
        conditions.append("e.department = :department")
        params["department"] = department
    if month is not None:
        conditions.append("p.month = :month")
        params["month"] = month
    if year is not None:
        conditions.append("p.year = :year")
        params["year"] = year
    if status:
        conditions.append("p.status = :status")
        params["status"] = status

    where = " AND ".join(conditions)

    # Validate sort_by and sort_order
    allowed_sort = {"month", "year", "days_worked", "absences", "overtime_hours",
                    "bonus", "allowance", "deductions", "gross_salary", "net_salary",
                    "status", "generated_at", "created_at", "updated_at",
                    "employee_name", "department"}
    sort_col = sort_by if sort_by in allowed_sort else "created_at"
    sort_dir = "ASC" if sort_order and sort_order.upper() == "ASC" else "DESC"

    # Map virtual sort columns to actual expressions
    if sort_col == "employee_name":
        sort_expr = f"e.full_name {sort_dir}"
    elif sort_col == "department_name":
        sort_expr = f"e.department {sort_dir}"
    else:
        sort_expr = f"p.{sort_col} {sort_dir}"

    count_query = f"""
        SELECT COUNT(*) AS cnt
        FROM payroll p
        JOIN employees e ON e.id = p.employee_id
        WHERE {where}
    """
    count_result = await database.fetch_one(count_query, params)
    total = count_result["cnt"] if count_result else 0

    offset = (page - 1) * page_size
    data_query = f"""
        SELECT p.id, p.org_id, p.employee_id, e.full_name AS employee_name,
               e.department, e.salary AS basic_salary,
               p.month, p.year,
               p.days_worked, p.absences, p.overtime_hours,
               p.bonus, p.allowance, p.deductions,
               p.gross_salary, p.net_salary,
               p.status, p.notes, p.generated_at,
               p.created_at, p.updated_at
        FROM payroll p
        JOIN employees e ON e.id = p.employee_id
        WHERE {where}
        ORDER BY {sort_expr}
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = page_size
    params["offset"] = offset

    rows = await database.fetch_all(data_query, params)
    return [dict(r) for r in rows], total


def _to_minutes(t: time | str | None) -> int:
    if t is None:
        return 0
    if isinstance(t, str):
        parts = t.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    return t.hour * 60 + t.minute


async def generate_payroll(
    org_id: int,
    employee_id: int | None,
    month: int,
    year: int,
) -> list[dict[str, Any]]:
    """
    Generate payroll for one or all employees in an org for a given month.

    Calculation:
      - basic_salary from employees.salary
      - per_day_rate = salary / working_days_in_month
      - deduction = per_day_rate * absences
      - overtime_pay = per_day_rate / 8 * overtime_hours * OVERTIME_RATE
      - gross_salary = basic_salary + overtime_pay
      - net_salary = gross_salary - deduction
      - Overtime pay is stored in the bonus column.
    """
    total_days = WORKING_DAYS_PER_MONTH  # fixed for consistency

    if employee_id:
        emp_rows = await database.fetch_all(
            "SELECT id, salary, full_name FROM employees WHERE id = :id AND org_id = :org_id",
            {"id": employee_id, "org_id": org_id},
        )
    else:
        emp_rows = await database.fetch_all(
            "SELECT id, salary, full_name FROM employees WHERE org_id = :org_id",
            {"org_id": org_id},
        )

    if not emp_rows:
        return []

    created: list[dict[str, Any]] = []

    for emp in emp_rows:
        emp_id = emp["id"]
        salary = Decimal(str(emp["salary"]))
        per_day_rate = salary / Decimal(str(total_days))
        per_hour_rate = per_day_rate / Decimal(str(BASE_HOURS_PER_DAY))

        # Calculate attendance-derived data
        att_data = await _calculate_data(org_id, emp_id, month, year)

        days_worked = att_data["days_worked"]
        absences = att_data["absences"]
        overtime_hours = att_data["overtime_hours"]

        # Deduction for absences
        deduction = (per_day_rate * Decimal(str(absences))).quantize(Decimal("0.01"))

        # Overtime pay → bonus column
        overtime_pay = (per_hour_rate * overtime_hours * OVERTIME_RATE).quantize(Decimal("0.01"))

        # Gross = base salary only (overtime is tracked separately in bonus column)
        gross_salary = salary.quantize(Decimal("0.01"))

        # Net = gross + bonus + allowance - deductions (floor at 0)
        net_salary = max(Decimal("0"), gross_salary + overtime_pay - deduction).quantize(Decimal("0.01"))

        # Upsert: if a payroll already exists for this employee/month/year, update it
        existing = await database.fetch_one(
            "SELECT id FROM payroll WHERE org_id = :org_id AND employee_id = :emp_id AND month = :month AND year = :year",
            {"org_id": org_id, "emp_id": emp_id, "month": month, "year": year},
        )

        if existing:
            await database.execute(
                """
                UPDATE payroll
                SET days_worked = :days_worked, absences = :absences,
                    overtime_hours = :overtime_hours,
                    bonus = :bonus, allowance = :allowance, deductions = :deductions,
                    gross_salary = :gross_salary, net_salary = :net_salary,
                    status = 'pending',
                    updated_at = datetime('now')
                WHERE id = :id AND org_id = :org_id
                """,
                {
                    "id": existing["id"],
                    "org_id": org_id,
                    "days_worked": days_worked,
                    "absences": absences,
                    "overtime_hours": str(overtime_hours),
                    "bonus": str(overtime_pay),
                    "allowance": "0",
                    "deductions": str(deduction),
                    "gross_salary": str(gross_salary),
                    "net_salary": str(net_salary),
                },
            )
            result = await _get_payroll(org_id, existing["id"])
            if result:
                created.append(result)
        else:
            result = await database.fetch_one(
                """
                INSERT INTO payroll (org_id, employee_id, month, year,
                                     days_worked, absences, overtime_hours,
                                     bonus, allowance, deductions,
                                     gross_salary, net_salary, status,
                                     generated_at, created_at, updated_at)
                VALUES (:org_id, :employee_id, :month, :year,
                        :days_worked, :absences, :overtime_hours,
                        :bonus, :allowance, :deductions,
                        :gross_salary, :net_salary, 'pending',
                        datetime('now'), datetime('now'), datetime('now'))
                RETURNING id
                """,
                {
                    "org_id": org_id,
                    "employee_id": emp_id,
                    "month": month,
                    "year": year,
                    "days_worked": days_worked,
                    "absences": absences,
                    "overtime_hours": str(overtime_hours),
                    "bonus": str(overtime_pay),
                    "allowance": "0",
                    "deductions": str(deduction),
                    "gross_salary": str(gross_salary),
                    "net_salary": str(net_salary),
                },
            )
            if result:
                full = await _get_payroll(org_id, result["id"])
                if full:
                    created.append(full)

    return created


async def _calculate_data(
    org_id: int,
    employee_id: int,
    month: int,
    year: int,
) -> dict[str, Any]:
    """Calculate attendance-derived metrics for an employee in a given month."""
    start_date = date(year, month, 1)
    total_days_in_month = calendar.monthrange(year, month)[1]
    end_date = date(year, month, total_days_in_month)

    rows = await database.fetch_all(
        """
        SELECT attendance_date, check_in_time, check_out_time, status
        FROM attendance
        WHERE employee_id = :employee_id
          AND org_id = :org_id
          AND attendance_date >= :start_date
          AND attendance_date <= :end_date
        ORDER BY attendance_date
        """,
        {
            "employee_id": employee_id,
            "org_id": org_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
    )

    total_days = calendar.monthrange(year, month)[1]
    weekdays = sum(1 for day in range(1, total_days + 1)
                   if date(year, month, day).weekday() < 5)

    # If no attendance records exist at all, treat as full attendance (no data ≠ absent every day)
    if not rows:
        return {
            "days_worked": weekdays,
            "absences": 0,
            "overtime_hours": Decimal("0"),
        }

    absent_days = 0
    total_overtime_minutes = 0

    attendance_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        d = row["attendance_date"].isoformat() if hasattr(row["attendance_date"], 'isoformat') else str(row["attendance_date"])
        attendance_map[d] = {
            "status": row["status"],
            "check_in_time": row["check_in_time"],
            "check_out_time": row["check_out_time"],
        }

        if row["status"] == "present":
            cin = row["check_in_time"]
            cout = row["check_out_time"]
            if cin and cout:
                worked_mins = _to_minutes(cout) - _to_minutes(cin)
                if worked_mins > 8 * 60:
                    total_overtime_minutes += worked_mins - 8 * 60

    for day in range(1, total_days + 1):
        d = date(year, month, day)
        if d.weekday() >= 5:
            continue
        key = d.isoformat()
        if key not in attendance_map:
            absent_days += 1
        elif attendance_map[key]["status"] == "absent":
            absent_days += 1

    overtime_hours = Decimal(str(round(total_overtime_minutes / 60, 1)))
    days_worked = weekdays - absent_days

    return {
        "days_worked": max(0, days_worked),
        "absences": max(0, absent_days),
        "overtime_hours": max(Decimal("0"), overtime_hours),
    }


async def _get_payroll(org_id: int, payroll_id: int) -> dict[str, Any] | None:
    """Internal fetch without JOIN (for insert-return)."""
    result = await database.fetch_one(
        "SELECT * FROM payroll WHERE id = :id AND org_id = :org_id",
        {"id": payroll_id, "org_id": org_id},
    )
    return dict(result) if result else None


async def update_payroll(
    org_id: int,
    payroll_id: int,
    values: dict[str, Any],
) -> dict[str, Any] | None:
    """Update a payroll record with the given values and return the updated record."""
    if not values:
        return await _get_payroll(org_id, payroll_id)

    # Always set updated_at explicitly (onupdate does not fire on raw UPDATE)
    set_items = []
    params: dict[str, Any] = {}
    for k, v in values.items():
        set_items.append(f"{k} = :{k}")
        params[k] = v

    set_clause = ", ".join(set_items)
    query = f"""
        UPDATE payroll
        SET {set_clause}, updated_at = datetime('now')
        WHERE id = :id AND org_id = :org_id
    """
    params["id"] = payroll_id
    params["org_id"] = org_id

    await database.execute(query, params)

    return await _get_payroll(org_id, payroll_id)


async def delete_payroll(org_id: int, payroll_id: int) -> None:
    """Delete a payroll record."""
    await database.execute(
        "DELETE FROM payroll WHERE id = :id AND org_id = :org_id",
        {"id": payroll_id, "org_id": org_id},
    )