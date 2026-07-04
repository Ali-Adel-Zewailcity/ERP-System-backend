"""
HR Module - SQLAlchemy Core table definitions.

Tables
------
  departments    - organisational units; each has an optional manager
  employees      - employee master data (links to a user account)
  attendance     - daily check-in / check-out records
  leave_requests - employee leave applications with manager approval
  payroll        - monthly payslip records generated automatically
"""

from __future__ import annotations

import sqlalchemy as sa

from app.db.metadata import metadata

# ─────────────────────────────────────────────────────────────────────────────
# departments
# ─────────────────────────────────────────────────────────────────────────────
departments = sa.Table(
    "departments",
    metadata,
    sa.Column("id",         sa.Integer,    primary_key=True, autoincrement=True),
    sa.Column("org_id",     sa.Integer,    sa.ForeignKey("organizations.id", ondelete="CASCADE"),
              nullable=False, index=True),
    # manager_id references users; SET NULL if the manager account is removed.
    # Using use_alter=True + name to break the forward-reference cycle with employees.
    sa.Column("manager_id", sa.Integer,    sa.ForeignKey("users.id", ondelete="SET NULL",
              name="fk_departments_manager_id_users", use_alter=True),
              nullable=True),
    sa.Column("name",       sa.String(100), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.UniqueConstraint("org_id", "name", name="uq_departments_org_id_name"),
)

# ─────────────────────────────────────────────────────────────────────────────
# employees
# ─────────────────────────────────────────────────────────────────────────────
employees = sa.Table(
    "employees",
    metadata,
    sa.Column("id",             sa.Integer,        primary_key=True, autoincrement=True),
    sa.Column("org_id",         sa.Integer,        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
              nullable=False, index=True),
    # An employee may or may not have a system user account.
    sa.Column("user_id",        sa.Integer,        sa.ForeignKey("users.id", ondelete="SET NULL"),
              nullable=True, unique=True),
    sa.Column("department_id",  sa.Integer,        sa.ForeignKey("departments.id", ondelete="SET NULL"),
              nullable=True, index=True),
    # Direct superior/manager of this employee (enables hierarchical organizational charts and tree tracking)
    sa.Column("superior_id",    sa.Integer,        sa.ForeignKey("employees.id", ondelete="SET NULL"),
              nullable=True, index=True),
    sa.Column("first_name",     sa.String(80),     nullable=False),
    sa.Column("last_name",      sa.String(80),     nullable=False),
    sa.Column("job_title",      sa.String(120),    nullable=True),
    sa.Column("hire_date",      sa.Date,           nullable=False),
    sa.Column("base_salary",    sa.Numeric(12, 2), nullable=False),
    sa.Column("phone",          sa.String(20),     nullable=True),
    sa.Column("national_id",    sa.String(30),     nullable=True),
    # JSON array of document URLs (contracts, certificates …)
    sa.Column("documents",      sa.Text,           nullable=True),
    sa.Column("is_active",      sa.Boolean,        nullable=False, server_default=sa.text("1")),
    sa.Column("created_at",     sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.Column("updated_at",     sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now(), onupdate=sa.func.now()),
    sa.CheckConstraint("base_salary >= 0", name="ck_employees_base_salary_non_negative"),
)

# ─────────────────────────────────────────────────────────────────────────────
# attendance
# ─────────────────────────────────────────────────────────────────────────────
_ATTENDANCE_STATUSES = "('present','absent','late','on_leave','holiday')"

attendance = sa.Table(
    "attendance",
    metadata,
    sa.Column("id",          sa.Integer,  primary_key=True, autoincrement=True),
    sa.Column("employee_id", sa.Integer,  sa.ForeignKey("employees.id", ondelete="CASCADE"),
              nullable=False, index=True),
    sa.Column("date",        sa.Date,     nullable=False),
    sa.Column("check_in",    sa.Time(timezone=True), nullable=True),
    sa.Column("check_out",   sa.Time(timezone=True), nullable=True),
    sa.Column("status",      sa.String(10), nullable=False),
    sa.Column("notes",       sa.Text,      nullable=True),
    # One record per employee per day.
    sa.UniqueConstraint("employee_id", "date", name="uq_attendance_employee_id_date"),
    sa.CheckConstraint(
        f"status IN {_ATTENDANCE_STATUSES}",
        name="ck_attendance_valid_status",
    ),
    # check_out must be after check_in when both are provided.
    sa.CheckConstraint(
        "check_out IS NULL OR check_in IS NULL OR check_out > check_in",
        name="ck_attendance_checkout_after_checkin",
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# leave_requests
# ─────────────────────────────────────────────────────────────────────────────
_LEAVE_TYPES   = "('annual','sick','unpaid','emergency','maternity','paternity')"
_LEAVE_STATUSES = "('pending','approved','rejected','cancelled')"

leave_requests = sa.Table(
    "leave_requests",
    metadata,
    sa.Column("id",           sa.Integer,  primary_key=True, autoincrement=True),
    sa.Column("employee_id",  sa.Integer,  sa.ForeignKey("employees.id", ondelete="CASCADE"),
              nullable=False, index=True),
    sa.Column("approved_by",  sa.Integer,  sa.ForeignKey("users.id", ondelete="SET NULL"),
              nullable=True),
    sa.Column("leave_type",   sa.String(15), nullable=False),
    sa.Column("start_date",   sa.Date,       nullable=False),
    sa.Column("end_date",     sa.Date,       nullable=False),
    sa.Column("total_days",   sa.Integer,    nullable=False),
    sa.Column("reason",       sa.Text,       nullable=True),
    sa.Column("status",       sa.String(10), nullable=False, server_default=sa.text("'pending'")),
    sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.Column("resolved_at",  sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint(
        f"leave_type IN {_LEAVE_TYPES}",
        name="ck_leave_requests_valid_type",
    ),
    sa.CheckConstraint(
        f"status IN {_LEAVE_STATUSES}",
        name="ck_leave_requests_valid_status",
    ),
    sa.CheckConstraint("end_date >= start_date", name="ck_leave_requests_dates_logical"),
    sa.CheckConstraint("total_days > 0",         name="ck_leave_requests_days_positive"),
)

# ─────────────────────────────────────────────────────────────────────────────
# payroll
# ─────────────────────────────────────────────────────────────────────────────
payroll = sa.Table(
    "payroll",
    metadata,
    sa.Column("id",           sa.Integer,        primary_key=True, autoincrement=True),
    sa.Column("employee_id",  sa.Integer,        sa.ForeignKey("employees.id", ondelete="RESTRICT"),
              nullable=False, index=True),
    sa.Column("month",        sa.SmallInteger,   nullable=False),   # 1–12
    sa.Column("year",         sa.SmallInteger,   nullable=False),   # e.g. 2026
    sa.Column("days_worked",  sa.Integer,        nullable=False, server_default=sa.text("0")),
    sa.Column("absences",     sa.Integer,        nullable=False, server_default=sa.text("0")),
    sa.Column("bonuses",      sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
    sa.Column("deductions",   sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
    sa.Column("gross_salary", sa.Numeric(12, 2), nullable=False),
    sa.Column("net_salary",   sa.Numeric(12, 2), nullable=False),
    sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
    # Only one payslip per employee per month/year.
    sa.UniqueConstraint("employee_id", "month", "year", name="uq_payroll_employee_month_year"),
    sa.CheckConstraint("month BETWEEN 1 AND 12",  name="ck_payroll_valid_month"),
    sa.CheckConstraint("year  > 2000",            name="ck_payroll_valid_year"),
    sa.CheckConstraint("days_worked >= 0",        name="ck_payroll_days_worked_non_negative"),
    sa.CheckConstraint("absences   >= 0",         name="ck_payroll_absences_non_negative"),
    sa.CheckConstraint("bonuses    >= 0",         name="ck_payroll_bonuses_non_negative"),
    sa.CheckConstraint("deductions >= 0",         name="ck_payroll_deductions_non_negative"),
    sa.CheckConstraint("gross_salary >= 0",       name="ck_payroll_gross_non_negative"),
    sa.CheckConstraint("net_salary  >= 0",        name="ck_payroll_net_non_negative"),
)
