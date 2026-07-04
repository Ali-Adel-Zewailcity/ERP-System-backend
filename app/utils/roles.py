"""
Roles utility — static permission map and helper functions.

This module is the single source of truth for which roles can access which
database tables. Permissions are determined entirely from the user's `role`
and `department` fields — no database lookups needed.

Role hierarchy:
  owner            → same as admin (set automatically when org is created)
  admin            → full access to all tables
  hr_manager       → HR tables only (full CRUD enforced at endpoint level)
  inventory_manager → Inventory tables only
  sales_manager    → Sales tables only
  employee         → read access to their department's tables (enforced at endpoint level)
"""

from typing import Literal
from fastapi import HTTPException, status

from app.models.auth import UserResponse, RoleLiteral, DepartmentLiteral


# ─────────────────────────────────────────────────────────────────────────────
# Static permission tables
# ─────────────────────────────────────────────────────────────────────────────

# HR table names
HR_TABLES: frozenset[str] = frozenset({"employees", "attendance", "leave_requests", "payroll", "departments"})

# Inventory table names
INVENTORY_TABLES: frozenset[str] = frozenset({"products", "inventory_stock", "suppliers", "purchase_orders", "product_categories", "supplier_products", "purchase_order_items"})

# Sales table names
SALES_TABLES: frozenset[str] = frozenset({"customers", "sales_orders", "sales_order_items", "returns", "return_items"})

# Admin-only tables (user/org management, audit)
ADMIN_TABLES: frozenset[str] = frozenset({"users", "roles", "activity_logs"})

ALL_TABLES: frozenset[str] = HR_TABLES | INVENTORY_TABLES | SALES_TABLES | ADMIN_TABLES

# Maps each role to the set of tables it can access
ROLE_TABLE_ACCESS: dict[str, frozenset[str]] = {
    "owner":              ALL_TABLES,
    "admin":              ALL_TABLES,
    "hr_manager":         HR_TABLES | ADMIN_TABLES,
    "inventory_manager":  INVENTORY_TABLES | ADMIN_TABLES,
    "sales_manager":      SALES_TABLES | ADMIN_TABLES,
    # employee: derived from department — see get_employee_tables()
}

# Maps department → accessible tables (read-only for employees, enforced at endpoint)
DEPARTMENT_TABLE_ACCESS: dict[str, frozenset[str]] = {
    "hr":        HR_TABLES,
    "inventory": INVENTORY_TABLES,
    "sales":     SALES_TABLES,
}

# Roles considered privileged (owner or admin)
PRIVILEGED_ROLES: frozenset[str] = frozenset({"owner", "admin"})


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_permissions_for_user(user: UserResponse) -> dict[str, bool]:
    """
    Returns a flat dict mapping table names to True for all tables the user
    can access, based solely on their `role` and `department` fields.
    """
    role = user.role
    if role is None:
        return {}

    if role == "employee":
        dept = user.department
        tables = DEPARTMENT_TABLE_ACCESS.get(dept, frozenset()) if dept else frozenset()
    else:
        tables = ROLE_TABLE_ACCESS.get(role, frozenset())

    return {table: True for table in sorted(tables)}


def is_owner(user: UserResponse) -> bool:
    """Return True if the user is the organization owner."""
    return user.role == "owner"


def is_privileged(user: UserResponse) -> bool:
    """Return True if the user is an owner or admin."""
    return user.role in PRIVILEGED_ROLES


def require_owner(user: UserResponse) -> None:
    """Raise 403 if the user is not an owner."""
    if not is_owner(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the organization owner can perform this action.",
        )


def require_owner_or_admin(user: UserResponse) -> None:
    """Raise 403 if the user is not an owner or admin."""
    if not is_privileged(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization owners or admins can perform this action.",
        )


def require_table_access(user: UserResponse, table: str) -> None:
    """Raise 403 if the user does not have access to the given table."""
    permissions = get_permissions_for_user(user)
    if not permissions.get(table):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have permission to access '{table}'.",
        )


def validate_role_department_pair(role: RoleLiteral | None, department: DepartmentLiteral | None) -> None:
    """
    Validate that the role/department combination makes sense.
    - Managers and employees must have a matching department.
    - Owner and admin must NOT have a department.
    """
    ROLE_REQUIRED_DEPT: dict[str, str] = {
        "hr_manager": "hr",
        "inventory_manager": "inventory",
        "sales_manager": "sales",
    }

    if role is None:
        return  # Unassigning role — always valid

    if role in ("owner", "admin"):
        if department is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Role '{role}' does not belong to a specific department. Remove the department field.",
            )
        return

    if role == "employee":
        if department is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An employee must have a department assigned ('hr', 'inventory', or 'sales').",
            )
        return

    if role in ROLE_REQUIRED_DEPT:
        expected = ROLE_REQUIRED_DEPT[role]
        if department != expected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Role '{role}' requires department='{expected}', but got '{department}'.",
            )
