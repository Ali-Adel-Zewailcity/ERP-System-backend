"""
Payroll utility — CRUD helper functions for payroll management.

All functions accept explicit parameters so they remain testable
without depending on FastAPI request objects.
"""

import calendar
from datetime import date, time, timedelta
from decimal import Decimal
from typing import Any

from app.db.database import database


SORTABLE_COLUMNS = frozenset({
    "employee_name", "month", "year", "basic_salary",
    "net_salary", "status", "department",
})

OVERTIME_RATE = Decimal("1.25")  # 125 % of hourly base rate
BASE_HOURS_PER_DAY = 8


async def get_payroll(org_id: int, payroll_id: int) -> dict[str, Any] | None:
    """Fetch a single payroll record by ID (with JOINed employee data)."""
    query = """
        SELECT p.id, p.org_id, p.employee_id, e.full_name AS employee_name,
               e.employee_number, e.job_title,
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
               e.employee_number, e.job_title,
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

    Policy: every employee has a fixed monthly Basic Salary. Absences
    without leave are deducted at a daily rate. Approved leave and
    holidays do NOT deduct salary.

    Calculation:
      - basic_salary from employees.salary
      - weekdays = number of Mon-Fri in the month/year
      - daily_rate = salary / weekdays
      - absence_deduction = daily_rate * absences
      - overtime_pay = daily_rate / 8 * overtime_hours * OVERTIME_RATE
      - gross_salary = basic_salary + bonus + allowance + overtime_pay
      - net_salary = gross_salary - absence_deduction - deductions
      - bonus, allowance, deductions are manual entries (default to 0).
    """

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

        # Calculate attendance-derived data (also returns weekdays)
        att_data = await _calculate_data(org_id, emp_id, month, year, emp)

        # Skip employees with no attendance records for this period
        if att_data is None:
            continue

        days_worked = att_data["days_worked"]
        absences = att_data["absences"]
        overtime_hours = att_data["overtime_hours"]
        weekdays = att_data["weekdays"]

        daily_rate = salary / Decimal(str(weekdays))
        per_hour_rate = daily_rate / Decimal(str(BASE_HOURS_PER_DAY))

        # Absence deduction = daily rate × absent days
        absence_deduction = (daily_rate * Decimal(str(absences))).quantize(Decimal("0.01"))

        # Overtime pay
        overtime_pay = (per_hour_rate * overtime_hours * OVERTIME_RATE).quantize(Decimal("0.01"))

        # Check if a payroll record already exists for this employee/month/year
        existing = await database.fetch_one(
            "SELECT id, bonus, allowance, deductions, notes, status FROM payroll WHERE org_id = :org_id AND employee_id = :emp_id AND month = :month AND year = :year",
            {"org_id": org_id, "emp_id": emp_id, "month": month, "year": year},
        )

        # Use existing manual values if regenerating, otherwise default to 0
        if existing:
            existing_bonus = Decimal(str(existing["bonus"]))
            existing_allowance = Decimal(str(existing["allowance"]))
            existing_deductions = Decimal(str(existing["deductions"]))
        else:
            existing_bonus = Decimal("0")
            existing_allowance = Decimal("0")
            existing_deductions = Decimal("0")

        # Gross = Basic Salary + Existing Bonus + Existing Allowance + Overtime Pay
        gross_salary = (salary + existing_bonus + existing_allowance + overtime_pay).quantize(Decimal("0.01"))

        # Net = Gross - Absence Deduction - Existing Manual Deductions
        net_salary = max(Decimal("0"), gross_salary - absence_deduction - existing_deductions).quantize(Decimal("0.01"))

        stored_absences = absences

        if existing:
            await database.execute(
                """
                UPDATE payroll
                SET days_worked = :days_worked, absences = :absences,
                    overtime_hours = :overtime_hours,
                    bonus = :bonus, allowance = :allowance, deductions = :deductions,
                    gross_salary = :gross_salary, net_salary = :net_salary,
                    notes = :notes, status = :status,
                    updated_at = datetime('now')
                WHERE id = :id AND org_id = :org_id
                """,
                {
                    "id": existing["id"],
                    "org_id": org_id,
                    "days_worked": days_worked,
                    "absences": stored_absences,
                    "overtime_hours": str(overtime_hours),
                    "bonus": str(existing_bonus),
                    "allowance": str(existing_allowance),
                    "deductions": str(existing_deductions),
                    "gross_salary": str(gross_salary),
                    "net_salary": str(net_salary),
                    "notes": existing["notes"],
                    "status": existing["status"],
                },
            )
            result = await get_payroll(org_id, existing["id"])
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
                    "absences": stored_absences,
                    "overtime_hours": str(overtime_hours),
                    "bonus": "0",
                    "allowance": "0",
                    "deductions": "0",
                    "gross_salary": str(gross_salary),
                    "net_salary": str(net_salary),
                },
            )
            if result:
                full = await get_payroll(org_id, result["id"])
                if full:
                    created.append(full)

    return created


async def _calculate_data(
    org_id: int,
    employee_id: int,
    month: int,
    year: int,
    emp: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Calculate attendance-derived metrics for an employee in a given month.

    Working days are bounded by the employee's hire_date and today's date,
    so pre-hire and future days are never counted as absent.

    Present = attendance with status 'present', 'late', 'leave', or 'holiday'.
    Absent = status 'absent' or no attendance record on a working day.
    """
    start_date = date(year, month, 1)
    total_days_in_month = calendar.monthrange(year, month)[1]
    end_date = date(year, month, total_days_in_month)

    # Bounded date range — exclude pre-hire and future days
    emp_dict = dict(emp) if emp else {}
    if emp_dict.get("hire_date"):
        hire_raw = emp_dict["hire_date"]
        hire_date = date.fromisoformat(hire_raw) if isinstance(hire_raw, str) else hire_raw
    else:
        row = await database.fetch_one(
            "SELECT hire_date FROM employees WHERE id = :id AND org_id = :org_id",
            {"id": employee_id, "org_id": org_id},
        )
        if not row:
            return None
        hire_date = row["hire_date"]
        if isinstance(hire_date, str):
            hire_date = date.fromisoformat(hire_date)

    today = date.today()
    effective_start = max(hire_date, start_date)
    effective_end = min(today, end_date)

    if effective_start > effective_end:
        return None

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

    # Span of the employee's eligible date range (hire_date to today)
    span = (effective_end - effective_start).days + 1

    # Total calendar days in the month — used as the daily-rate denominator
    weekdays = total_days_in_month

    if not rows:
        return None

    attendance_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        raw = row["attendance_date"]
        if isinstance(raw, str):
            d = raw[:10]
        else:
            d = raw.strftime("%Y-%m-%d") if hasattr(raw, "strftime") else str(raw)
        attendance_map[d] = {
            "status": row["status"],
            "check_in_time": row["check_in_time"],
            "check_out_time": row["check_out_time"],
        }

    present_days = 0
    absent_days = 0
    total_overtime_minutes = 0

    present_statuses = {"present", "late", "leave", "holiday"}

    for key, att in attendance_map.items():
        att_date = date.fromisoformat(key[:10])
        if att_date > today or att_date < effective_start:
            continue
        status = att["status"]
        if status in present_statuses:
            present_days += 1
            if status == "present":
                cin = att["check_in_time"]
                cout = att["check_out_time"]
                if cin and cout:
                    worked_mins = _to_minutes(cout) - _to_minutes(cin)
                    if worked_mins > 8 * 60:
                        total_overtime_minutes += worked_mins - 8 * 60

    for offset in range(span):
        d = effective_start + timedelta(days=offset)
        if d.weekday() in (4, 5):
            continue
        key = d.isoformat()
        if key not in attendance_map or attendance_map[key]["status"] not in present_statuses:
            absent_days += 1

    overtime_hours = Decimal(str(round(total_overtime_minutes / 60, 1)))

    return {
        "days_worked": present_days,
        "absences": absent_days,
        "overtime_hours": max(Decimal("0"), overtime_hours),
        "weekdays": weekdays,
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
        return await get_payroll(org_id, payroll_id)

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

    return await get_payroll(org_id, payroll_id)


async def delete_payroll(org_id: int, payroll_id: int) -> None:
    """Delete a payroll record."""
    await database.execute(
        "DELETE FROM payroll WHERE id = :id AND org_id = :org_id",
        {"id": payroll_id, "org_id": org_id},
    )