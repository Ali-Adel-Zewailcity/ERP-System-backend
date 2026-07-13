"""
Top Performance Router — Computed per-employee metrics for a given month.

Sources
-------
  attendance       present/absent/late counts (bounded by hire_date + today)
  leave_requests   approved leave days overlapping the target month
"""

import calendar
from collections import defaultdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.db.database import database
from app.models.auth import UserResponse
from app.models.hr import (
    TopPerformanceItem,
    TopPerformanceStats,
    TopPerformanceResponse,
)
from app.utils.dependency import require_organization_member
from app.utils.roles import require_table_access


router = APIRouter(prefix="/top-performance", tags=["Top Performance"])


@router.get("/", response_model=TopPerformanceResponse,
            summary="Top Performance")
async def list_top_performance(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    month: Annotated[int, Query(ge=1, le=12)] = date.today().month,
    year: Annotated[int, Query(ge=2020)] = date.today().year,
    department: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> TopPerformanceResponse:
    """Return per-employee performance data aggregated for a given month/year."""
    require_table_access(current_user, "employees")

    org_id = current_user.org_id
    last_day = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end = date(year, month, last_day)
    today = date.today()
    ms = month_start.isoformat()
    me = month_end.isoformat()
    today_s = today.isoformat()

    # ── 1a. Fetch active employees with hire_date ──
    emp_rows = await database.fetch_all(
        """SELECT id AS employee_id, full_name AS employee_name,
                   department, hire_date
           FROM employees
           WHERE org_id = :org_id
             AND status = 'active'
             AND (:department IS NULL OR department = :department)
        """,
        {"org_id": org_id, "department": department},
    )

    # ── 1b. Fetch ALL attendance records for this org in the month ──
    raw_att_rows = await database.fetch_all(
        """SELECT a.employee_id, a.attendance_date, a.status
           FROM attendance a
           JOIN employees e ON e.id = a.employee_id AND e.org_id = a.org_id
           WHERE a.org_id = :org_id
             AND e.status = 'active'
             AND a.attendance_date >= :ms
             AND a.attendance_date <= :me
             AND (:department IS NULL OR e.department = :department)
        """,
        {"org_id": org_id, "ms": ms, "me": me, "department": department},
    )

    att_by_emp: dict[int, list[dict]] = defaultdict(list)
    for r in raw_att_rows:
        rec = dict(r)
        ad = rec["attendance_date"]
        rec["_date_obj"] = date.fromisoformat(ad[:10]) if isinstance(ad, str) else ad
        att_by_emp[rec["employee_id"]].append(rec)

    # ── 2. Approved leave overlap with target month ──
    leave_rows = await database.fetch_all(
        """SELECT employee_id, start_date, end_date
           FROM leave_requests
           WHERE org_id = :org_id
             AND status = 'approved'
             AND start_date <= :me
             AND end_date >= :ms""",
        {"org_id": org_id, "ms": ms, "me": me},
    )

    leave_map: dict[int, int] = {}
    for row in leave_rows:
        emp_id = row["employee_id"]
        s = row["start_date"]
        e = row["end_date"]
        if isinstance(s, str):
            s = date.fromisoformat(s)
        if isinstance(e, str):
            e = date.fromisoformat(e)
        overlap = min(e, month_end) - max(s, month_start)
        leave_map[emp_id] = leave_map.get(emp_id, 0) + overlap.days + 1

    # ── 3. Assemble items with per-employee bounded date range ──
    items: list[TopPerformanceItem] = []
    for emp in emp_rows:
        emp_id = emp["employee_id"]
        hire_raw = emp["hire_date"]
        hire_d = date.fromisoformat(hire_raw) if isinstance(hire_raw, str) else hire_raw

        eff_start = max(month_start, hire_d)
        eff_end = min(month_end, today)
        if eff_start > eff_end:
            continue

        present = absent = late = 0
        for a in att_by_emp.get(emp_id, []):
            ad = a["_date_obj"]
            if ad < eff_start or ad > eff_end:
                continue
            if a["status"] == "present":
                present += 1
            elif a["status"] == "absent":
                absent += 1
            elif a["status"] == "late":
                late += 1

        working = present + absent + late
        rate = round((present / working) * 100, 1) if working > 0 else 0.0
        items.append(TopPerformanceItem(
            employee_id=emp_id,
            employee_name=emp["employee_name"],
            department=emp["department"],
            attendance_rate=rate,
            late_count=late,
            leave_days_used=leave_map.get(emp_id, 0),
            perfect_attendance=absent == 0,
        ))

    items.sort(key=lambda i: (-i.attendance_rate, i.employee_name))
    total = len(items)

    # ── 4. Aggregate stats (over the FULL set before pagination) ──
    top = items[0] if items else None
    most_late = max(items, key=lambda i: i.late_count) if items else None
    avg_rate = round(
        sum(i.attendance_rate for i in items) / total, 1
    ) if total > 0 else 0.0
    perfect_count = sum(1 for i in items if i.perfect_attendance)

    stats = TopPerformanceStats(
        top_performer_name=top.employee_name if top else None,
        top_performer_rate=top.attendance_rate if top else None,
        avg_attendance_rate=avg_rate,
        perfect_attendance_count=perfect_count,
        most_late_name=most_late.employee_name if most_late else None,
        most_late_count=most_late.late_count if most_late else 0,
    )

    # ── 5. Paginate ──
    start = (page - 1) * page_size
    paged = items[start:start + page_size]
    pages = (total + page_size - 1) // page_size if total else 0

    return TopPerformanceResponse(
        items=paged, total=total, page=page, page_size=page_size,
        pages=pages, stats=stats,
    )
