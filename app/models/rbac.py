"""
RBAC & Permissions Schemas - Pydantic v2 request/response models. 

These models power the granular permission system, allowing organizations to manage
roles, resource-action permissions, row-level data scoping, and field-level security.
"""

from typing import Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schema.auth import ResourceLiteral, ActionLiteral, RESTRICT_ALLOWED_ACTIONS


class PermissionResponse(BaseModel):
    """Response model representing a registered permission."""
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "resource": "employees",
                "action": "read",
                "description": "Allows viewing employee profiles within the organization."
            }
        }
    )

    id: Annotated[int, Field(description="Unique database identifier for the permission.")]

    resource: Annotated[ResourceLiteral, Field(
        description="The system entity or domain (e.g., 'employees', 'customers', 'products')."
        )]

    action: Annotated[ActionLiteral, Field(
        description=(
            "The operation allowed on the resource:\n"
            "- 'create': Onboard new entities or add database records.\n"
            "- 'read': View existing records on dashboards or lists.\n"
            "- 'update': Modify existing record values.\n"
            "- 'delete': Permanently remove or archive records.\n"
            "- 'export': Download bulk data to external spreadsheets (separated from 'read' for Data Loss Prevention).\n"
            )
        )]

    description: Annotated[str | None, Field(
        description="Human-readable explanation of what this permission grants."
        )] = None

    @model_validator(mode="after")
    def validate_resource_action(self) -> "PermissionResponse":
        allowed_actions = RESTRICT_ALLOWED_ACTIONS.get(self.resource, None)
        if allowed_actions and self.action not in allowed_actions:
            allowed_str = ", ".join(f"'{a}'" for a in allowed_actions)
            raise ValueError(f"The '{self.resource}' resource only supports the following actions: {allowed_str}.")
        return self


class AssignedRolePermissionResponse(BaseModel):
    """Response model representing a permission assigned to a role."""
    model_config = ConfigDict(from_attributes=True)

    permission_id: Annotated[int, Field(description="Permission ID.")]
    resource: Annotated[ResourceLiteral, Field(description="Target resource.")]
    action: Annotated[ActionLiteral, Field(description="Target action.")]
    description: Annotated[str | None, Field(description="Permission description.")] = None
    scope: Annotated[str | None, Field(description="Row-level scope ('all', 'department', 'own').")]
    denied_fields: Annotated[list[str], Field(default_factory=list, description="Denied database columns.")]


class RolePermissionAssign(BaseModel):
    """
    Request model to assign or update a permission for a role.
    Includes row-level scoping and field-level restrictions.
    """
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "permission_id": 5,
            "scope": "department",
            "denied_fields": ["base_salary", "national_id"]
        }
    })

    permission_id: Annotated[int, Field(description="ID of the permission to grant to the role.")]
    
    scope: Annotated[Literal["all", "department", "own"] | None, Field(
            description=(
                "Row-level data scope:\n"
                "- 'all': Access all records belonging to the user's specific organization (supported by all resources).\n"
                "- 'department': Access only records belonging to the user's assigned department (restricted to specific resources: users, activity_logs, payroll, leave_requests, employees, attendance).\n"
                "- 'own': Access only records created by or assigned to the user directly (restricted to specific resources: users, activity_logs, payroll, leave_requests, employees, attendance).\n"
            )
        )] = None
    
    denied_fields: Annotated[list[str] | None, Field(
            default_factory=list,
            description=(
                "Field-level security: List of database column names restricted from this role.\n"
                "How to know which table they belong to: Because this request assigns a specific `permission_id`, "
                "and that permission defines the target `resource` (table name), these denied fields belong specifically "
                "to that resource table!"
            )
        )]


class RolePermissionAssignRequest(BaseModel):
    """Request payload for assigning or updating multiple permissions for a role in bulk."""
    permissions: Annotated[list[RolePermissionAssign], Field(
        description="List of permission grants to configure for the role."
    )]


class RolePermissionDeleteRequest(BaseModel):
    """Request payload for removing multiple permissions from a role in bulk."""
    permission_ids: Annotated[list[int], Field(
        description="List of permission IDs to unassign from the role."
    )]


class GrantedPermissionGrant(BaseModel):
    """Details of a granted permission inside the user's resolved permission payload."""
    scope: Annotated[str | None, Field(
            description="Row-level scope ('all', 'department', 'own'). Note: 'all' is strictly scoped to the user's organization and applies to all resources. 'department' and 'own' apply only to specific resources (`users`, `activity_logs`, `payroll`, `leave_requests`, `employees`, `attendance`)."
        )]

    denied_fields: Annotated[list[str], Field(
            default_factory=list,
            description="List of fields restricted from access."
        )]


class UserPermissionsMatrixResponse(BaseModel):
    """
    Comprehensive response model returned to the frontend.
    Contains user metadata, ownership status, and a nested matrix of allowed resources and actions.
    Frontend apps use this to dynamically hide/show UI components and table columns.
    """
    user_id: Annotated[int, Field(description="Current logged-in user ID.")]
    org_id: Annotated[int | None, Field(description="Organization ID.")] = None
    role_name: Annotated[str | None, Field(description="Name of the user's assigned role.")] = None
    is_org_owner: Annotated[bool, Field(
            description="If true, the user is the owner of the organization and has unrestricted access to all resources."
        )]
    
    # Dictionary mapping: { resource_name: { action_name: GrantedPermissionGrant } }
    # Example: { "employees": { "read": { "scope": "department", "denied_fields": ["base_salary"] } } }
    permissions: Annotated[dict[str, dict[str, GrantedPermissionGrant]], Field(
            default_factory=dict,
            description="Map of allowed resources to their granted actions and scope rules."
        )]


class ResourceColumnsResponse(BaseModel):
    """Response model returning retrievable column names for a resource table."""
    resource: Annotated[str, Field(description="Name of the database table resource.")]
    columns: Annotated[list[str], Field(description="List of retrievable column names.")]