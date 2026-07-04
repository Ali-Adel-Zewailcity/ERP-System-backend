"""
RBAC Router — Simplified permissions endpoint.

Endpoints
---------
  GET /rbac/mypermissions  - Returns the current user's simplified permission map.
"""

from typing import Annotated
from fastapi import APIRouter, Depends

from app.models.roles import UserPermissionsResponse
from app.utils.dependency import user_permissions


router = APIRouter(prefix="/rbac", tags=["RBAC & Permissions"])


@router.get(
    "/mypermissions",
    response_model=UserPermissionsResponse,
    summary="Get Current User's Permission Map",
    description=(
        "Returns the resolved permission map for the currently authenticated user.\n\n"
        "The `permissions` object maps database table names to `true` for every table "
        "the user is allowed to access. This is determined entirely by the user's fixed "
        "`role` and (for employees) their `department`.\n\n"
        "**Roles and their accessible tables:**\n"
        "- `owner` / `admin`: all tables\n"
        "- `hr_manager`: HR tables (employees, attendance, leave_requests, payroll, departments)\n"
        "- `inventory_manager`: Inventory tables (products, inventory_stock, suppliers, purchase_orders, ...)\n"
        "- `sales_manager`: Sales tables (customers, sales_orders, returns, ...)\n"
        "- `employee`: Read-only access to their assigned department's tables\n"
    ),
)
async def get_my_permissions(
    perms: Annotated[UserPermissionsResponse, Depends(user_permissions)]
) -> UserPermissionsResponse:
    """Return the current user's permission map."""
    return perms