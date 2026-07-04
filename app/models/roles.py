"""
Roles & Permissions — Pydantic models for the simplified fixed-hierarchy role system.

The system uses a fixed 4-level hierarchy with no dynamic permission tables:
  owner            → full access to everything
  admin            → full access to everything
  hr_manager       → full CRUD on HR-related tables
  inventory_manager → full CRUD on Inventory-related tables
  sales_manager    → full CRUD on Sales-related tables
  employee         → read-only access to their own department tables

Permissions are determined by the user's `role` and optionally `department` columns
on the `users` table — no external permission catalog needed.
"""

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

from app.models.auth import RoleLiteral, DepartmentLiteral


class UserPermissionsResponse(BaseModel):
    """
    Simplified permission matrix returned to the frontend.

    The `permissions` dict maps resource table names to True/False.
    The frontend uses this to show/hide sidebar items and guard routes.
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": 1,
                "org_id": 1,
                "role": "hr_manager",
                "department": "hr",
                "permissions": {
                    "employees": True,
                    "attendance": True,
                    "leave_requests": True,
                    "payroll": True,
                    "departments": True,
                }
            }
        }
    )

    user_id: Annotated[int, Field(description="Logged-in user ID.")]
    org_id: Annotated[int | None, Field(description="Organization ID.")] = None
    role: Annotated[RoleLiteral | None, Field(description="User's fixed role name.")] = None
    department: Annotated[DepartmentLiteral | None, Field(description="User's department (for managers and employees).")] = None
    permissions: Annotated[dict[str, bool], Field(
        default_factory=dict,
        description="Map of resource table names to access grant (True = has access)."
    )]


class RoleAssignRequest(BaseModel):
    """Request payload for assigning a fixed role (and optional department) to an organization member."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "role": "hr_manager",
                "department": "hr"
            }
        }
    )

    role: Annotated[RoleLiteral | None, Field(
        description="Fixed role to assign. Pass null to unassign the role."
    )] = None

    department: Annotated[DepartmentLiteral | None, Field(
        description=(
            "Required when role is 'hr_manager', 'inventory_manager', 'sales_manager', or 'employee'. "
            "Must match the role's domain (e.g., hr_manager → 'hr')."
        )
    )] = None
