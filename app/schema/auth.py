"""
Auth — SQLAlchemy Core table definitions.

Tables
------
  organizations  - single organization tenant
  users          - system accounts linked to an org, with a fixed role and department
  activity_logs  - immutable audit trail (append-only; no UPDATE / DELETE allowed)

Role hierarchy (fixed, not stored in a separate table):
  owner            → assigned automatically when the org is created
  admin            → full access to all modules
  hr_manager       → full CRUD on HR tables
  inventory_manager → full CRUD on Inventory tables
  sales_manager    → full CRUD on Sales tables
  employee         → read-only access to their department's tables (scoped by `department` column)

Department values (for manager/employee scoping):
  hr | inventory | sales | None (owner/admin have no department restriction)
"""

import sqlalchemy as sa
from app.db.metadata import metadata


# Valid role and department values
VALID_ROLES = ("owner", "admin", "hr_manager", "inventory_manager", "sales_manager", "employee")
VALID_DEPARTMENTS = ("hr", "inventory", "sales")

# ─────────────────────────────────────────────────────────────────────────────
# organizations
# ─────────────────────────────────────────────────────────────────────────────
organizations = sa.Table(
    "organizations",
    metadata,
    sa.Column("id",           sa.Integer,      primary_key=True, autoincrement=True),
    sa.Column("name",         sa.String(150),  nullable=False),
    sa.Column("owner_id",     sa.Integer,
              sa.ForeignKey("users.id", ondelete="RESTRICT",
                            name="fk_organizations_owner_id"),
              nullable=False, index=True),
    sa.Column("phone",        sa.String(30),   nullable=False),
    sa.Column("address",      sa.Text,         nullable=True),
    sa.Column("is_active",    sa.Boolean,      nullable=False, server_default=sa.text("true")),
    sa.Column("created_at",   sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.Column("updated_at",   sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now(), onupdate=sa.func.now()),
)

# ─────────────────────────────────────────────────────────────────────────────
# users
# ─────────────────────────────────────────────────────────────────────────────
users = sa.Table(
    "users",
    metadata,
    sa.Column("id",            sa.Integer,    primary_key=True, autoincrement=True),
    sa.Column("org_id",        sa.Integer,    nullable=True),
    sa.Column("role",          sa.String(30), nullable=True),
    sa.Column("department",    sa.String(20), nullable=True),
    sa.Column("username",      sa.String(20), nullable=False, unique=True),
    sa.Column("email",         sa.String(255), nullable=False, unique=True),
    sa.Column("phone",         sa.String(30),  nullable=False, unique=True),
    sa.Column("password_hash", sa.String(255), nullable=False),
    sa.Column("first_name",    sa.String(80), nullable=True),
    sa.Column("last_name",     sa.String(80), nullable=True),
    sa.Column("is_active",     sa.Boolean,    nullable=False, server_default=sa.text("true")),
    sa.Column("created_at",    sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    sa.Column("updated_at",    sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    sa.Column("last_login",    sa.Date,       nullable=True, server_default=sa.func.now()),
)

# ─────────────────────────────────────────────────────────────────────────────
# activity_logs  (append-only audit trail — never updated or deleted)
# ─────────────────────────────────────────────────────────────────────────────
activity_logs = sa.Table(
    "activity_logs",
    metadata,
    sa.Column("id",          sa.Integer,  primary_key=True, autoincrement=True),
    sa.Column("org_id",      sa.Integer,     sa.ForeignKey("organizations.id", ondelete="CASCADE"),
              nullable=False, index=True),
    sa.Column("user_id",     sa.Integer,     sa.ForeignKey("users.id", ondelete="SET NULL"),
              nullable=True, index=True),
    sa.Column("module",      sa.String(30),  nullable=False),
    sa.Column("action",      sa.String(50),  nullable=False),
    sa.Column("entity_type", sa.String(50),  nullable=True),
    sa.Column("entity_id",   sa.Integer,     nullable=True),
    sa.Column("old_value",   sa.Text,        nullable=True),
    sa.Column("new_value",   sa.Text,        nullable=True),
    sa.Column("ip_address",  sa.String(45),  nullable=True),
    sa.Column("user_agent",  sa.Text,        nullable=True),
    sa.Column("timestamp",   sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now(), index=True),
    sa.CheckConstraint(
        "module IN ('inventory','sales','hr','auth','reporting','system')",
        name="ck_activity_logs_valid_module",
    ),
)

