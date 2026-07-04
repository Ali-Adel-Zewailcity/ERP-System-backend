"""
Organization Router — Endpoints for managing the single organization.

Endpoints
---------
  POST /organization/                     - Create a new organization (current user becomes owner).
  GET  /organization/                     - Get the current user's organization details.
  GET  /organization/members              - List all members of the organization.
  POST /organization/members/{user_id}    - Add an existing user to the organization.
  DELETE /organization/members/{user_id} - Remove a member from the organization.
  PUT /organization/members/{user_id}/role - Assign a fixed role to a member (owner only).
"""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Path

from app.db.database import database
from app.models.auth import UserResponse
from app.models.organization import (
    OrganizationCreateRequest,
    OrganizationResponse,
    OrganizationMemberResponse,
)
from app.models.roles import RoleAssignRequest
from app.utils.dependency import get_current_user, require_organization_member
from app.utils.roles import require_owner, require_owner_or_admin, validate_role_department_pair


router = APIRouter(prefix="/organization", tags=["Organization"])


# ─────────────────────────────────────────────────────────────────────────────
# Create / Get Organization
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=OrganizationResponse,
    summary="Create Organization",
    description="Creates a new organization and sets the authenticated user as its owner.",
)
async def create_organization(
    req: OrganizationCreateRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> OrganizationResponse:
    """Create a new organization and link the requesting user as its owner."""

    if current_user.org_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already belong to an organization.",
        )

    # Insert the organization
    insert_org_query = """
        INSERT INTO organizations (name, owner_id, phone, address)
        VALUES (:name, :owner_id, :phone, :address)
        RETURNING id, name, owner_id, phone, address, is_active, created_at, updated_at
    """
    new_org = await database.fetch_one(insert_org_query, {
        "name": req.name,
        "owner_id": current_user.id,
        "phone": req.phone,
        "address": req.address,
    })

    # Link the user to the org and set the 'owner' role
    await database.execute(
        "UPDATE users SET org_id = :org_id, role = 'owner', department = NULL WHERE id = :user_id",
        {"org_id": new_org["id"], "user_id": current_user.id},
    )

    return OrganizationResponse.model_validate(new_org)


@router.get(
    "/",
    response_model=OrganizationResponse,
    summary="Get My Organization",
    description="Returns the organization details for the currently authenticated user.",
)
async def get_organization(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> OrganizationResponse:
    """Retrieve the organization the current user belongs to."""

    org = await database.fetch_one(
        "SELECT * FROM organizations WHERE id = :org_id",
        {"org_id": current_user.org_id},
    )
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    return OrganizationResponse.model_validate(org)


# ─────────────────────────────────────────────────────────────────────────────
# Members
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/members",
    response_model=list[OrganizationMemberResponse],
    summary="List Organization Members",
    description="Retrieves users belonging to the organization. Owners/Admins see all; Managers see their department.",
)
async def list_members(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> list[OrganizationMemberResponse]:
    """List all members of the organization (or department for managers)."""
    if current_user.role in ("owner", "admin"):
        query = """
            SELECT id, username, email, phone, first_name, last_name, role, department
            FROM users
            WHERE org_id = :org_id
            ORDER BY id
        """
        params = {"org_id": current_user.org_id}
    elif current_user.role in ("hr_manager", "inventory_manager", "sales_manager"):
        dept_map = {
            "hr_manager": "hr",
            "inventory_manager": "inventory",
            "sales_manager": "sales",
        }
        dept = dept_map[current_user.role]
        query = """
            SELECT id, username, email, phone, first_name, last_name, role, department
            FROM users
            WHERE org_id = :org_id AND department = :dept
            ORDER BY id
        """
        params = {"org_id": current_user.org_id, "dept": dept}
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization owners, admins, or department managers can view members.",
        )

    rows = await database.fetch_all(query, params)
    return [OrganizationMemberResponse.model_validate(r) for r in rows]


@router.post(
    "/members/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Add Member to Organization",
    description="Adds an existing user (by user_id) to the organization. Owner only.",
)
async def add_member(
    user_id: Annotated[int, Path(description="ID of the user to add to the organization.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, str]:
    """Add an existing user to the organization (no role assigned yet)."""
    require_owner(current_user)

    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already in this organization.",
        )

    target_user = await database.fetch_one(
        "SELECT id, org_id FROM users WHERE id = :user_id",
        {"user_id": user_id},
    )
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with ID {user_id} does not exist.")

    if target_user["org_id"] is not None:
        if target_user["org_id"] == current_user.org_id:
            detail = f"User {user_id} already belongs to this organization."
        else:
            detail = f"User {user_id} belongs to another organization and cannot be added."
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    await database.execute(
        "UPDATE users SET org_id = :org_id WHERE id = :user_id",
        {"org_id": current_user.org_id, "user_id": user_id},
    )

    return {"message": f"User {user_id} has been successfully added to your organization."}


@router.delete(
    "/members/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove Member from Organization",
    description="Removes a member from the organization and clears their role. Owner only.",
)
async def remove_member(
    user_id: Annotated[int, Path(description="ID of the user to remove from the organization.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, str]:
    """Remove a user from the organization."""
    require_owner(current_user)

    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove yourself from the organization.",
        )

    target_user = await database.fetch_one(
        "SELECT id, role FROM users WHERE id = :user_id AND org_id = :org_id",
        {"user_id": user_id, "org_id": current_user.org_id},
    )
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found in your organization.")

    if target_user["role"] == "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot remove the organization owner.")

    await database.execute(
        "UPDATE users SET org_id = NULL, role = NULL, department = NULL WHERE id = :user_id",
        {"user_id": user_id},
    )

    return {"message": f"User {user_id} has been removed from the organization."}


# ─────────────────────────────────────────────────────────────────────────────
# Role Assignment
# ─────────────────────────────────────────────────────────────────────────────

@router.put(
    "/members/{user_id}/role",
    status_code=status.HTTP_200_OK,
    summary="Assign Role to Member",
    description=(
        "Assigns a fixed role (and department if applicable) to a member. Owner only.\n\n"
        "**Valid roles:** `admin`, `hr_manager`, `inventory_manager`, `sales_manager`, `employee`\n\n"
        "**Department rules:**\n"
        "- `admin`: no department needed\n"
        "- `hr_manager`: department must be `'hr'`\n"
        "- `inventory_manager`: department must be `'inventory'`\n"
        "- `sales_manager`: department must be `'sales'`\n"
        "- `employee`: department required (`'hr'`, `'inventory'`, or `'sales'`)\n"
        "- Pass `role: null` to unassign the role.\n"
    ),
)
async def assign_member_role(
    user_id: Annotated[int, Path(description="ID of the user to assign a role to.")],
    req: RoleAssignRequest,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, str]:
    """Assign or unassign a fixed role to/from an organization member."""
    require_owner(current_user)

    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot modify your own role.",
        )

    target_user = await database.fetch_one(
        "SELECT id, role FROM users WHERE id = :user_id AND org_id = :org_id",
        {"user_id": user_id, "org_id": current_user.org_id},
    )
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found in your organization.")

    if target_user["role"] == "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot change the role of the organization owner.")

    # Prevent assigning 'owner' role — there can only be one owner
    if req.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The 'owner' role cannot be assigned. Transfer ownership is not supported.",
        )

    # Validate role/department combination
    validate_role_department_pair(req.role, req.department)

    await database.execute(
        "UPDATE users SET role = :role, department = :department WHERE id = :user_id",
        {"role": req.role, "department": req.department, "user_id": user_id},
    )

    if req.role is None:
        msg = f"Role unassigned from user {user_id}."
    else:
        msg = f"Role '{req.role}' successfully assigned to user {user_id}."
        if req.department:
            msg += f" Department: '{req.department}'."

    return {"message": msg}