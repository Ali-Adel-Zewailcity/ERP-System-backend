"""
Inventory Module — Pydantic request/response models.

Covers product categories, products, inventory stock levels, suppliers,
supplier→product relationships, and purchase orders with their line items.
"""

from typing import Annotated, Literal
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# Product Categories
# ─────────────────────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    description: Annotated[str | None, Field(max_length=1000)] = None


class CategoryUpdate(BaseModel):
    name: Annotated[str | None, Field(min_length=1, max_length=100)] = None
    description: Annotated[str | None, Field(max_length=1000)] = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    org_id: int
    name: str
    description: str | None = None
    created_at: datetime
    product_count: int = 0


class CategoryListResponse(BaseModel):
    items: list[CategoryResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ─────────────────────────────────────────────────────────────────────────────
# Products
# ─────────────────────────────────────────────────────────────────────────────

class ProductCreate(BaseModel):
    sku: Annotated[str, Field(min_length=1, max_length=50)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str | None, Field(max_length=2000)] = None
    category_id: Annotated[int | None, Field(ge=1)] = None
    unit_price: Annotated[Decimal, Field(ge=0)]
    cost_price: Annotated[Decimal, Field(ge=0)]
    image_url: Annotated[str | None, Field(max_length=500)] = None
    is_active: bool = True

    @field_validator("unit_price", "cost_price", mode="before")
    @classmethod
    def _coerce_decimal(cls, value):
        if value is None:
            return value
        return Decimal(str(value))


class ProductUpdate(BaseModel):
    sku: Annotated[str | None, Field(min_length=1, max_length=50)] = None
    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    description: Annotated[str | None, Field(max_length=2000)] = None
    category_id: Annotated[int | None, Field(ge=1)] = None
    unit_price: Annotated[Decimal | None, Field(ge=0)] = None
    cost_price: Annotated[Decimal | None, Field(ge=0)] = None
    image_url: Annotated[str | None, Field(max_length=500)] = None
    is_active: bool | None = None

    @field_validator("unit_price", "cost_price", mode="before")
    @classmethod
    def _coerce_decimal(cls, value):
        if value is None:
            return value
        return Decimal(str(value))


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    org_id: int
    category_id: int | None = None
    sku: str
    name: str
    description: str | None = None
    unit_price: Decimal
    cost_price: Decimal
    image_url: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    category_name: str | None = None

    # Joined stock snapshot (always present — one inventory_stock row per product)
    quantity_available: int = 0
    quantity_reserved: int = 0
    reorder_threshold: int = 0
    is_low_stock: bool = False


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int
    page: int
    page_size: int
    pages: int


class ProductStatsResponse(BaseModel):
    total: int
    active: int
    inactive: int
    low_stock: int
    out_of_stock: int
    total_inventory_value: Decimal = Decimal("0")
    total_stock_units: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Inventory Stock
# ─────────────────────────────────────────────────────────────────────────────

class StockAdjustRequest(BaseModel):
    """Adjust stock for a product.

    - `quantity_available` / `quantity_reserved` / `reorder_threshold`:
      when provided, set the value explicitly.
    - `delta_available` / `delta_reserved`: when provided, add to the
      current value (supports positive or negative movement).
    Only one style should be used per field per call.
    """

    quantity_available: Annotated[int | None, Field(ge=0)] = None
    quantity_reserved: Annotated[int | None, Field(ge=0)] = None
    reorder_threshold: Annotated[int | None, Field(ge=0)] = None
    delta_available: int | None = None
    delta_reserved: int | None = None
    reason: Annotated[str | None, Field(max_length=500)] = None

    @model_validator(mode="after")
    def _check_no_conflict(self):
        if self.quantity_available is not None and self.delta_available is not None:
            raise ValueError("Provide either 'quantity_available' or 'delta_available', not both.")
        if self.quantity_reserved is not None and self.delta_reserved is not None:
            raise ValueError("Provide either 'quantity_reserved' or 'delta_reserved', not both.")
        return self


class StockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity_available: int
    quantity_reserved: int
    reorder_threshold: int
    updated_at: datetime
    # Joined product snapshot
    sku: str | None = None
    name: str | None = None
    unit_price: Decimal | None = None
    is_low_stock: bool = False
    inventory_value: Decimal = Decimal("0")


class StockListResponse(BaseModel):
    items: list[StockResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ─────────────────────────────────────────────────────────────────────────────
# Suppliers
# ─────────────────────────────────────────────────────────────────────────────

class SupplierCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=150)]
    contact_name: Annotated[str | None, Field(max_length=100)] = None
    email: Annotated[str | None, Field(max_length=255)] = None
    phone: Annotated[str | None, Field(max_length=20)] = None
    address: Annotated[str | None, Field(max_length=1000)] = None
    payment_terms: Annotated[str | None, Field(max_length=100)] = None
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value):
        if value in (None, ""):
            return value
        from email_validator import validate_email, EmailNotValidError
        try:
            return validate_email(value, check_deliverability=False).normalized
        except EmailNotValidError:
            raise ValueError("Please provide a valid email address.")


class SupplierUpdate(BaseModel):
    name: Annotated[str | None, Field(min_length=1, max_length=150)] = None
    contact_name: Annotated[str | None, Field(max_length=100)] = None
    email: Annotated[str | None, Field(max_length=255)] = None
    phone: Annotated[str | None, Field(max_length=20)] = None
    address: Annotated[str | None, Field(max_length=1000)] = None
    payment_terms: Annotated[str | None, Field(max_length=100)] = None
    is_active: bool | None = None

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value):
        if value in (None, ""):
            return value
        from email_validator import validate_email, EmailNotValidError
        try:
            return validate_email(value, check_deliverability=False).normalized
        except EmailNotValidError:
            raise ValueError("Please provide a valid email address.")


class SupplierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    org_id: int
    name: str
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    payment_terms: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    product_count: int = 0


class SupplierListResponse(BaseModel):
    items: list[SupplierResponse]
    total: int
    page: int
    page_size: int
    pages: int


class SupplierStatsResponse(BaseModel):
    total: int
    active: int
    inactive: int
    with_products: int


# ─────────────────────────────────────────────────────────────────────────────
# Supplier Products (M2M)
# ─────────────────────────────────────────────────────────────────────────────

class SupplierProductCreate(BaseModel):
    product_id: Annotated[int, Field(ge=1)]
    supplier_sku: Annotated[str | None, Field(max_length=50)] = None
    supplier_price: Annotated[Decimal | None, Field(ge=0)] = None
    lead_time_days: Annotated[int | None, Field(ge=0)] = None
    is_preferred: bool = False

    @field_validator("supplier_price", mode="before")
    @classmethod
    def _coerce_decimal(cls, value):
        if value is None:
            return value
        return Decimal(str(value))


class SupplierProductUpdate(BaseModel):
    supplier_sku: Annotated[str | None, Field(max_length=50)] = None
    supplier_price: Annotated[Decimal | None, Field(ge=0)] = None
    lead_time_days: Annotated[int | None, Field(ge=0)] = None
    is_preferred: bool | None = None

    @field_validator("supplier_price", mode="before")
    @classmethod
    def _coerce_decimal(cls, value):
        if value is None:
            return value
        return Decimal(str(value))


class SupplierProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    supplier_id: int
    product_id: int
    supplier_sku: str | None = None
    supplier_price: Decimal | None = None
    lead_time_days: int | None = None
    is_preferred: bool
    # Joined product snapshot
    sku: str | None = None
    name: str | None = None
    unit_price: Decimal | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Purchase Orders
# ─────────────────────────────────────────────────────────────────────────────

POStatus = Literal["draft", "ordered", "partially_received", "received", "cancelled"]


class PurchaseOrderItemCreate(BaseModel):
    product_id: Annotated[int, Field(ge=1)]
    quantity_ordered: Annotated[int, Field(ge=1)]
    unit_cost: Annotated[Decimal, Field(ge=0)]

    @field_validator("unit_cost", mode="before")
    @classmethod
    def _coerce_decimal(cls, value):
        if value is None:
            return value
        return Decimal(str(value))


class PurchaseOrderItemUpdate(BaseModel):
    product_id: Annotated[int | None, Field(ge=1)] = None
    quantity_ordered: Annotated[int | None, Field(ge=1)] = None
    unit_cost: Annotated[Decimal | None, Field(ge=0)] = None

    @field_validator("unit_cost", mode="before")
    @classmethod
    def _coerce_decimal(cls, value):
        if value is None:
            return value
        return Decimal(str(value))


class PurchaseOrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    product_id: int
    quantity_ordered: int
    quantity_received: int
    unit_cost: Decimal
    # Joined product snapshot
    sku: str | None = None
    name: str | None = None


class PurchaseOrderCreate(BaseModel):
    supplier_id: Annotated[int, Field(ge=1)]
    notes: Annotated[str | None, Field(max_length=2000)] = None
    items: Annotated[list[PurchaseOrderItemCreate], Field(min_length=1)]


class PurchaseOrderUpdate(BaseModel):
    supplier_id: Annotated[int | None, Field(ge=1)] = None
    notes: Annotated[str | None, Field(max_length=2000)] = None


class PurchaseOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    org_id: int
    supplier_id: int
    created_by: int | None = None
    status: str
    total_amount: Decimal
    notes: str | None = None
    ordered_at: datetime | None = None
    received_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    supplier_name: str | None = None
    item_count: int = 0
    received_count: int = 0
    items: list[PurchaseOrderItemResponse] = []


class PurchaseOrderListResponse(BaseModel):
    items: list[PurchaseOrderResponse]
    total: int
    page: int
    page_size: int
    pages: int


class PurchaseOrderStatsResponse(BaseModel):
    total: int
    draft: int
    ordered: int
    partially_received: int
    received: int
    cancelled: int
    open_value: Decimal = Decimal("0")


class ReceiveItemRequest(BaseModel):
    product_id: Annotated[int, Field(ge=1)]
    quantity: Annotated[int, Field(ge=1)]


class ReceiveRequest(BaseModel):
    """Receive goods against a purchase order.

    If `items` is omitted, all unreceived quantities are received.
    Otherwise only the specified items/quantities are received.
    """

    items: list[ReceiveItemRequest] | None = None
    notes: Annotated[str | None, Field(max_length=2000)] = None
