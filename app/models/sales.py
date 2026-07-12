from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

# ─────────────────────────────────────────────────────────────────────────────
# Literal types
# ─────────────────────────────────────────────────────────────────────────────

OrderStatusLiteral = Literal["draft", "confirmed", "processing", "shipped", "delivered", "cancelled"]
ReturnStatusLiteral = Literal["pending", "approved", "rejected", "completed"]
InspectionStatusLiteral = Literal["pass", "fail"]
RefundMethodLiteral = Literal["cash", "bank_transfer", "credit_note", "replace"]

# ─────────────────────────────────────────────────────────────────────────────
# Customer
# ─────────────────────────────────────────────────────────────────────────────


class CustomerCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Ahmed Ali",
                "email": "ahmed@example.com",
                "phone": "1012345678",
                "address": "15 Tahrir St, Cairo",
                "credit_limit": 50000.00,
                "notes": "VIP customer",
            }
        }
    )

    name: Annotated[str, Field(min_length=1, max_length=150)]
    email: Annotated[str | None, Field(max_length=255)] = None
    phone: Annotated[str | None, Field(max_length=20)] = None
    address: str | None = None
    credit_limit: Annotated[Decimal, Field(max_digits=14, decimal_places=2, ge=0)] = Decimal("0")
    notes: str | None = None
    is_active: bool = True


class CustomerUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Ahmed Ali Updated",
                "email": "ahmed.new@example.com",
                "credit_limit": 75000.00,
            }
        }
    )

    name: Annotated[str | None, Field(min_length=1, max_length=150)] = None
    email: Annotated[str | None, Field(max_length=255)] = None
    phone: Annotated[str | None, Field(max_length=20)] = None
    address: str | None = None
    credit_limit: Annotated[Decimal | None, Field(max_digits=14, decimal_places=2, ge=0)] = None
    notes: str | None = None
    is_active: bool | None = None


class CustomerResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "org_id": 1,
                "name": "Ahmed Ali",
                "email": "ahmed@example.com",
                "phone": "1012345678",
                "address": "15 Tahrir St, Cairo",
                "credit_limit": 50000.00,
                "notes": "VIP customer",
                "is_active": True,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        },
    )

    id: int
    org_id: int
    name: str
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    credit_limit: Decimal
    notes: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Sales Order + Order Items
# ─────────────────────────────────────────────────────────────────────────────


class SalesOrderItemCreate(BaseModel):
    product_id: int
    quantity: Annotated[int, Field(gt=0)]
    unit_price: Annotated[Decimal, Field(max_digits=12, decimal_places=2, gt=0)]


class SalesOrderCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "customer_id": 1,
                "notes": "Urgent delivery",
                "items": [
                    {"product_id": 1, "quantity": 2, "unit_price": 150.00},
                    {"product_id": 3, "quantity": 1, "unit_price": 250.00},
                ],
            }
        }
    )

    customer_id: int
    notes: str | None = None
    items: list[SalesOrderItemCreate]


class SalesOrderItemUpdate(BaseModel):
    product_id: int | None = None
    quantity: Annotated[int | None, Field(gt=0)] = None
    unit_price: Annotated[Decimal | None, Field(max_digits=12, decimal_places=2, gt=0)] = None


class SalesOrderUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "confirmed",
                "notes": "Confirmed by manager",
            }
        }
    )

    customer_id: int | None = None
    status: OrderStatusLiteral | None = None
    notes: str | None = None
    items: list[SalesOrderItemUpdate] | None = None


class SalesOrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    product_id: int
    quantity: int
    unit_price: Decimal


class SalesOrderResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "org_id": 1,
                "customer_id": 1,
                "customer_name": "Ahmed Ali",
                "created_by": 1,
                "status": "draft",
                "total_amount": 550.00,
                "notes": "Urgent delivery",
                "confirmed_at": None,
                "shipped_at": None,
                "delivered_at": None,
                "cancelled_at": None,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "items": [],
            }
        },
    )

    id: int
    org_id: int
    customer_id: int
    customer_name: str | None = None
    created_by: int | None = None
    status: str
    total_amount: Decimal
    notes: str | None = None
    confirmed_at: datetime | None = None
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    items: list[SalesOrderItemResponse] = []


class CustomerListResponse(BaseModel):
    items: list[CustomerResponse]
    total: int
    page: int
    page_size: int
    pages: int


class SalesOrderListResponse(BaseModel):
    items: list[SalesOrderResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ─────────────────────────────────────────────────────────────────────────────
# Return + Return Items
# ─────────────────────────────────────────────────────────────────────────────


class ReturnItemCreate(BaseModel):
    product_id: int
    quantity: Annotated[int, Field(gt=0)]
    inspection_status: InspectionStatusLiteral | None = None
    refund_method: RefundMethodLiteral | None = None


class ReturnCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "order_id": 1,
                "reason": "Damaged goods",
                "items": [
                    {"product_id": 1, "quantity": 1, "inspection_status": "fail", "refund_method": "cash"},
                ],
            }
        }
    )

    order_id: int
    reason: str | None = None
    items: list[ReturnItemCreate]


class ReturnItemUpdate(BaseModel):
    product_id: int | None = None
    quantity: Annotated[int | None, Field(gt=0)] = None
    inspection_status: InspectionStatusLiteral | None = None
    refund_method: RefundMethodLiteral | None = None


class ReturnUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "approved",
                "refund_amount": 150.00,
                "reason": "Approved after inspection",
            }
        }
    )

    status: ReturnStatusLiteral | None = None
    refund_amount: Annotated[Decimal | None, Field(max_digits=14, decimal_places=2, ge=0)] = None
    reason: str | None = None
    items: list[ReturnItemUpdate] | None = None


class ReturnItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    return_id: int
    product_id: int
    quantity: int
    inspection_status: str | None = None
    refund_method: str | None = None


class ReturnResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "org_id": 1,
                "order_id": 1,
                "processed_by": 1,
                "reason": "Damaged goods",
                "status": "pending",
                "refund_amount": 150.00,
                "created_at": "2026-01-01T00:00:00Z",
                "resolved_at": None,
                "items": [],
            }
        },
    )

    id: int
    org_id: int
    order_id: int
    processed_by: int | None = None
    reason: str | None = None
    status: str
    refund_amount: Decimal
    created_at: datetime
    resolved_at: datetime | None = None
    items: list[ReturnItemResponse] = []


class ReturnListResponse(BaseModel):
    items: list[ReturnResponse]
    total: int
    page: int
    page_size: int
    pages: int
