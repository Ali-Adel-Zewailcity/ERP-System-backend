"""
Sales Router — Customer, Sales Order, and Return management endpoints.

Endpoints
---------
  Customers    — CRUD
  Sales Orders — CRUD + line items
  Returns      — CRUD + return items
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, status, Path, Query

from app.db.database import database
from app.models.auth import UserResponse
from app.models.sales import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    SalesOrderCreate,
    SalesOrderUpdate,
    SalesOrderResponse,
    SalesOrderListResponse,
    ReturnCreate,
    ReturnUpdate,
    ReturnResponse,
    ReturnListResponse,
)
from app.utils.dependency import get_current_user, require_organization_member
from app.utils.roles import require_table_access, require_write_access
from app.utils.activity_log import log_activity
from app.schema.sales import (
    customers as customers_table,
    sales_orders as sales_orders_table,
    sales_order_items as sales_order_items_table,
    returns as returns_table,
    return_items as return_items_table,
)

# ─────────────────────────────────────────────────────────────────────────────
# Customers
# ─────────────────────────────────────────────────────────────────────────────

customer_router = APIRouter(prefix="/customers", tags=["Customers"])


@customer_router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=CustomerResponse,
    summary="Create Customer",
    description="Creates a new customer scoped to the current user's organization.",
)
async def create_customer(
    req: CustomerCreate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> CustomerResponse:
    """Create a new customer within the current organization."""
    require_write_access(current_user, "customers")

    query = customers_table.insert().values(
        org_id=current_user.org_id,
        name=req.name,
        email=req.email,
        phone=req.phone,
        address=req.address,
        credit_limit=str(req.credit_limit),
        notes=req.notes,
        is_active=req.is_active,
    ).returning(*customers_table.c)

    record = await database.fetch_one(query)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create customer.",
        )

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="created",
        entity_type="customer",
        entity_id=record["id"],
        new_value={"name": req.name},
    )

    return CustomerResponse.model_validate(record)


@customer_router.get(
    "/",
    response_model=list[CustomerResponse],
    summary="List Customers",
    description="Returns a list of customers scoped to the current user's organization.",
)
async def list_customers(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    search: Annotated[str | None, Query(max_length=100)] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> list[CustomerResponse]:
    """List customers with optional search and active filter."""
    require_table_access(current_user, "customers")

    conditions = [customers_table.c.org_id == current_user.org_id]
    if search:
        conditions.append(customers_table.c.name.ilike(f"%{search}%"))
    if is_active is not None:
        conditions.append(customers_table.c.is_active == is_active)

    query = (
        customers_table.select()
        .where(*conditions)
        .order_by(customers_table.c.name.asc())
    )
    rows = await database.fetch_all(query)
    return [CustomerResponse.model_validate(r) for r in rows]


@customer_router.get(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Get Customer",
    description="Returns a single customer by ID.",
)
async def get_customer(
    customer_id: Annotated[int, Path(description="ID of the customer.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> CustomerResponse:
    """Retrieve a customer by ID."""
    require_table_access(current_user, "customers")

    query = customers_table.select().where(
        customers_table.c.id == customer_id,
        customers_table.c.org_id == current_user.org_id,
    )
    record = await database.fetch_one(query)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found.",
        )

    return CustomerResponse.model_validate(record)


@customer_router.put(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Update Customer",
    description="Updates an existing customer. Only provided fields are changed.",
)
async def update_customer(
    customer_id: Annotated[int, Path(description="ID of the customer.")],
    req: CustomerUpdate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> CustomerResponse:
    """Update a customer record."""
    require_write_access(current_user, "customers")

    existing = await database.fetch_one(
        customers_table.select().where(
            customers_table.c.id == customer_id,
            customers_table.c.org_id == current_user.org_id,
        )
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found.",
        )

    values: dict[str, Any] = {}
    for field in ("name", "email", "phone", "address", "notes", "is_active"):
        val = getattr(req, field, None)
        if val is not None:
            values[field] = val
    if req.credit_limit is not None:
        values["credit_limit"] = str(req.credit_limit)

    if not values:
        return CustomerResponse.model_validate(existing)

    query = (
        customers_table.update()
        .where(
            customers_table.c.id == customer_id,
            customers_table.c.org_id == current_user.org_id,
        )
        .values(**values)
        .returning(*customers_table.c)
    )
    updated = await database.fetch_one(query)

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="updated",
        entity_type="customer",
        entity_id=customer_id,
        old_value={k: str(existing[k]) for k in values if k in existing},
        new_value={k: str(v) for k, v in values.items()},
    )

    return CustomerResponse.model_validate(updated)


@customer_router.delete(
    "/{customer_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Customer",
    description="Deletes a customer. Requires write access.",
)
async def delete_customer(
    customer_id: Annotated[int, Path(description="ID of the customer.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, str]:
    """Delete a customer record."""
    require_write_access(current_user, "customers")

    existing = await database.fetch_one(
        customers_table.select().where(
            customers_table.c.id == customer_id,
            customers_table.c.org_id == current_user.org_id,
        )
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found.",
        )

    await database.execute(
        customers_table.delete().where(
            customers_table.c.id == customer_id,
            customers_table.c.org_id == current_user.org_id,
        )
    )

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="deleted",
        entity_type="customer",
        entity_id=customer_id,
        old_value={"name": existing["name"]},
    )

    return {"message": f"Customer '{existing['name']}' deleted."}


# ─────────────────────────────────────────────────────────────────────────────
# Sales Orders
# ─────────────────────────────────────────────────────────────────────────────

order_router = APIRouter(prefix="/sales-orders", tags=["Sales Orders"])


@order_router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=SalesOrderResponse,
    summary="Create Sales Order",
    description="Creates a new sales order with line items.",
)
async def create_sales_order(
    req: SalesOrderCreate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> SalesOrderResponse:
    """Create a new sales order with items."""
    require_write_access(current_user, "sales_orders")

    # Verify customer exists and belongs to the same org
    customer = await database.fetch_one(
        "SELECT id FROM customers WHERE id = :id AND org_id = :org_id",
        {"id": req.customer_id, "org_id": current_user.org_id},
    )
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found.",
        )

    if not req.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one item is required.",
        )

    total_amount = sum(item.unit_price * item.quantity for item in req.items)

    async with database.transaction():
        order_query = sales_orders_table.insert().values(
            org_id=current_user.org_id,
            customer_id=req.customer_id,
            created_by=current_user.id,
            total_amount=str(total_amount),
            notes=req.notes,
        ).returning(*sales_orders_table.c)

        order = await database.fetch_one(order_query)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create sales order.",
            )

        for item in req.items:
            item_query = sales_order_items_table.insert().values(
                order_id=order["id"],
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=str(item.unit_price),
            )
            await database.execute(item_query)

    # Re-fetch with items
    full = await _get_order_with_items(current_user.org_id, order["id"])

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="created",
        entity_type="sales_order",
        entity_id=order["id"],
        new_value={"customer_id": req.customer_id, "total_amount": str(total_amount)},
    )

    return SalesOrderResponse.model_validate(full)


@order_router.get(
    "/",
    response_model=SalesOrderListResponse,
    summary="List Sales Orders",
    description="Returns a paginated list of sales orders.",
)
async def list_sales_orders(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Annotated[str | None, Query(pattern="^(draft|confirmed|processing|shipped|delivered|cancelled)?$")] = None,
    customer_id: Annotated[int | None, Query()] = None,
) -> SalesOrderListResponse:
    """List sales orders with pagination and optional filters."""
    require_table_access(current_user, "sales_orders")

    conditions = [sales_orders_table.c.org_id == current_user.org_id]
    if status:
        conditions.append(sales_orders_table.c.status == status)
    if customer_id:
        conditions.append(sales_orders_table.c.customer_id == customer_id)

    count_query = (
        sales_orders_table.select()
        .with_only_columns(sales_orders_table.c.id)
        .where(*conditions)
    )
    total = await database.fetch_val(
        count_query.alias("subq").count().select()
    ) or 0

    offset = (page - 1) * page_size
    query = (
        sales_orders_table.select()
        .where(*conditions)
        .order_by(sales_orders_table.c.created_at.desc())
        .limit(page_size)
        .offset(offset)
    )
    rows = await database.fetch_all(query)

    items = []
    for r in rows:
        full = await _get_order_with_items(current_user.org_id, r["id"])
        items.append(SalesOrderResponse.model_validate(full))

    pages = (total + page_size - 1) // page_size if total else 0

    return SalesOrderListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@order_router.get(
    "/{order_id}",
    response_model=SalesOrderResponse,
    summary="Get Sales Order",
    description="Returns a single sales order by ID with its line items.",
)
async def get_sales_order(
    order_id: Annotated[int, Path(description="ID of the sales order.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> SalesOrderResponse:
    """Retrieve a sales order by ID."""
    require_table_access(current_user, "sales_orders")

    full = await _get_order_with_items(current_user.org_id, order_id)
    if not full:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sales order not found.",
        )

    return SalesOrderResponse.model_validate(full)


@order_router.put(
    "/{order_id}",
    response_model=SalesOrderResponse,
    summary="Update Sales Order",
    description="Updates a sales order (status, notes, items).",
)
async def update_sales_order(
    order_id: Annotated[int, Path(description="ID of the sales order.")],
    req: SalesOrderUpdate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> SalesOrderResponse:
    """Update a sales order record."""
    require_write_access(current_user, "sales_orders")

    existing = await database.fetch_one(
        sales_orders_table.select().where(
            sales_orders_table.c.id == order_id,
            sales_orders_table.c.org_id == current_user.org_id,
        )
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sales order not found.",
        )

    values: dict[str, Any] = {}
    if req.customer_id is not None:
        values["customer_id"] = req.customer_id
    if req.status is not None:
        values["status"] = req.status
    if req.notes is not None:
        values["notes"] = req.notes

    async with database.transaction():
        if values:
            update_query = (
                sales_orders_table.update()
                .where(
                    sales_orders_table.c.id == order_id,
                    sales_orders_table.c.org_id == current_user.org_id,
                )
                .values(**values)
            )
            await database.execute(update_query)

        if req.items is not None:
            await database.execute(
                sales_order_items_table.delete().where(
                    sales_order_items_table.c.order_id == order_id,
                )
            )
            for item in req.items:
                if item.product_id is None:
                    continue
                qty = item.quantity or 1
                price = item.unit_price or Decimal("0")
                item_query = sales_order_items_table.insert().values(
                    order_id=order_id,
                    product_id=item.product_id,
                    quantity=qty,
                    unit_price=str(price),
                )
                await database.execute(item_query)

    # Re-calculate total
    items_rows = await database.fetch_all(
        sales_order_items_table.select().where(
            sales_order_items_table.c.order_id == order_id,
        )
    )
    new_total = sum(
        Decimal(str(it["unit_price"])) * it["quantity"]
        for it in items_rows
    )
    await database.execute(
        sales_orders_table.update()
        .where(sales_orders_table.c.id == order_id)
        .values(total_amount=str(new_total))
    )

    full = await _get_order_with_items(current_user.org_id, order_id)

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="updated",
        entity_type="sales_order",
        entity_id=order_id,
        old_value={k: str(existing[k]) for k in values if k in existing},
        new_value={k: str(v) for k, v in values.items()},
    )

    return SalesOrderResponse.model_validate(full)


@order_router.delete(
    "/{order_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Sales Order",
    description="Deletes a sales order and its items. Requires write access.",
)
async def delete_sales_order(
    order_id: Annotated[int, Path(description="ID of the sales order.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, str]:
    """Delete a sales order and its line items."""
    require_write_access(current_user, "sales_orders")

    existing = await database.fetch_one(
        sales_orders_table.select().where(
            sales_orders_table.c.id == order_id,
            sales_orders_table.c.org_id == current_user.org_id,
        )
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sales order not found.",
        )

    async with database.transaction():
        await database.execute(
            sales_order_items_table.delete().where(
                sales_order_items_table.c.order_id == order_id,
            )
        )
        await database.execute(
            sales_orders_table.delete().where(
                sales_orders_table.c.id == order_id,
                sales_orders_table.c.org_id == current_user.org_id,
            )
        )

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="deleted",
        entity_type="sales_order",
        entity_id=order_id,
        old_value={"id": order_id},
    )

    return {"message": f"Sales order {order_id} deleted."}


async def _get_order_with_items(org_id: int, order_id: int) -> dict[str, Any] | None:
    """Fetch a sales order and its items, return a combined dict."""
    order = await database.fetch_one(
        sales_orders_table.select().where(
            sales_orders_table.c.id == order_id,
            sales_orders_table.c.org_id == org_id,
        )
    )
    if not order:
        return None

    order = dict(order)

    items = await database.fetch_all(
        sales_order_items_table.select().where(
            sales_order_items_table.c.order_id == order_id,
        ).order_by(sales_order_items_table.c.id)
    )
    order["items"] = [dict(i) for i in items]

    customer = await database.fetch_one(
        "SELECT name FROM customers WHERE id = :id",
        {"id": order["customer_id"]},
    )
    order["customer_name"] = customer["name"] if customer else None

    return order


# ─────────────────────────────────────────────────────────────────────────────
# Returns
# ─────────────────────────────────────────────────────────────────────────────

return_router = APIRouter(prefix="/returns", tags=["Returns"])


@return_router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=ReturnResponse,
    summary="Create Return",
    description="Creates a new return request with return items.",
)
async def create_return(
    req: ReturnCreate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> ReturnResponse:
    """Create a new return with items."""
    require_write_access(current_user, "returns")

    order = await database.fetch_one(
        "SELECT id FROM sales_orders WHERE id = :id AND org_id = :org_id",
        {"id": req.order_id, "org_id": current_user.org_id},
    )
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sales order not found.",
        )

    if not req.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one return item is required.",
        )

    async with database.transaction():
        return_query = returns_table.insert().values(
            org_id=current_user.org_id,
            order_id=req.order_id,
            processed_by=current_user.id,
            reason=req.reason,
        ).returning(*returns_table.c)

        record = await database.fetch_one(return_query)
        if not record:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create return.",
            )

        for item in req.items:
            item_query = return_items_table.insert().values(
                return_id=record["id"],
                product_id=item.product_id,
                quantity=item.quantity,
                inspection_status=item.inspection_status,
                refund_method=item.refund_method,
            )
            await database.execute(item_query)

    full = await _get_return_with_items(current_user.org_id, record["id"])

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="created",
        entity_type="return",
        entity_id=record["id"],
        new_value={"order_id": req.order_id, "reason": req.reason},
    )

    return ReturnResponse.model_validate(full)


@return_router.get(
    "/",
    response_model=ReturnListResponse,
    summary="List Returns",
    description="Returns a paginated list of return requests.",
)
async def list_returns(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Annotated[str | None, Query(pattern="^(pending|approved|rejected|completed)?$")] = None,
) -> ReturnListResponse:
    """List returns with pagination and optional filters."""
    require_table_access(current_user, "returns")

    conditions = [returns_table.c.org_id == current_user.org_id]
    if status:
        conditions.append(returns_table.c.status == status)

    count_query = (
        returns_table.select()
        .with_only_columns(returns_table.c.id)
        .where(*conditions)
    )
    total = await database.fetch_val(
        count_query.alias("subq").count().select()
    ) or 0

    offset = (page - 1) * page_size
    query = (
        returns_table.select()
        .where(*conditions)
        .order_by(returns_table.c.created_at.desc())
        .limit(page_size)
        .offset(offset)
    )
    rows = await database.fetch_all(query)

    items = []
    for r in rows:
        full = await _get_return_with_items(current_user.org_id, r["id"])
        items.append(ReturnResponse.model_validate(full))

    pages = (total + page_size - 1) // page_size if total else 0

    return ReturnListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@return_router.get(
    "/{return_id}",
    response_model=ReturnResponse,
    summary="Get Return",
    description="Returns a single return request by ID with its items.",
)
async def get_return(
    return_id: Annotated[int, Path(description="ID of the return.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> ReturnResponse:
    """Retrieve a return by ID."""
    require_table_access(current_user, "returns")

    full = await _get_return_with_items(current_user.org_id, return_id)
    if not full:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Return not found.",
        )

    return ReturnResponse.model_validate(full)


@return_router.put(
    "/{return_id}",
    response_model=ReturnResponse,
    summary="Update Return",
    description="Updates a return (status, refund amount, items).",
)
async def update_return(
    return_id: Annotated[int, Path(description="ID of the return.")],
    req: ReturnUpdate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> ReturnResponse:
    """Update a return record."""
    require_write_access(current_user, "returns")

    existing = await database.fetch_one(
        returns_table.select().where(
            returns_table.c.id == return_id,
            returns_table.c.org_id == current_user.org_id,
        )
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Return not found.",
        )

    values: dict[str, Any] = {}
    if req.status is not None:
        values["status"] = req.status
    if req.refund_amount is not None:
        values["refund_amount"] = str(req.refund_amount)
    if req.reason is not None:
        values["reason"] = req.reason

    if req.status in ("approved", "rejected", "completed"):
        values["resolved_at"] = datetime.now()

    async with database.transaction():
        if values:
            update_query = (
                returns_table.update()
                .where(
                    returns_table.c.id == return_id,
                    returns_table.c.org_id == current_user.org_id,
                )
                .values(**values)
            )
            await database.execute(update_query)

        if req.items is not None:
            await database.execute(
                return_items_table.delete().where(
                    return_items_table.c.return_id == return_id,
                )
            )
            for item in req.items:
                if item.product_id is None:
                    continue
                qty = item.quantity or 1
                item_query = return_items_table.insert().values(
                    return_id=return_id,
                    product_id=item.product_id,
                    quantity=qty,
                    inspection_status=item.inspection_status,
                    refund_method=item.refund_method,
                )
                await database.execute(item_query)

    full = await _get_return_with_items(current_user.org_id, return_id)

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="updated",
        entity_type="return",
        entity_id=return_id,
        old_value={k: str(existing[k]) for k in values if k in existing},
        new_value={k: str(v) for k, v in values.items()},
    )

    return ReturnResponse.model_validate(full)


@return_router.delete(
    "/{return_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Return",
    description="Deletes a return and its items. Requires write access.",
)
async def delete_return(
    return_id: Annotated[int, Path(description="ID of the return.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, str]:
    """Delete a return and its items."""
    require_write_access(current_user, "returns")

    existing = await database.fetch_one(
        returns_table.select().where(
            returns_table.c.id == return_id,
            returns_table.c.org_id == current_user.org_id,
        )
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Return not found.",
        )

    async with database.transaction():
        await database.execute(
            return_items_table.delete().where(
                return_items_table.c.return_id == return_id,
            )
        )
        await database.execute(
            returns_table.delete().where(
                returns_table.c.id == return_id,
                returns_table.c.org_id == current_user.org_id,
            )
        )

    await log_activity(
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="deleted",
        entity_type="return",
        entity_id=return_id,
    )

    return {"message": f"Return {return_id} deleted."}


async def _get_return_with_items(org_id: int, return_id: int) -> dict[str, Any] | None:
    """Fetch a return and its items, return a combined dict."""
    record = await database.fetch_one(
        returns_table.select().where(
            returns_table.c.id == return_id,
            returns_table.c.org_id == org_id,
        )
    )
    if not record:
        return None

    record = dict(record)

    items = await database.fetch_all(
        return_items_table.select().where(
            return_items_table.c.return_id == return_id,
        ).order_by(return_items_table.c.id)
    )
    record["items"] = [dict(i) for i in items]

    return record
 
router = APIRouter()

router.include_router(customer_router)
router.include_router(order_router)
router.include_router(return_router)



