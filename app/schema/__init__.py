"""Models package - re-exports all tables for convenience."""

from app.schema.auth import (
    organizations,
    users,
    activity_logs,
)
from app.schema.inventory import (
    product_categories,
    products,
    inventory_stock,
    suppliers,
    supplier_products,
    purchase_orders,
    purchase_order_items,
)
from app.schema.sales import (
    customers,
    sales_orders,
    sales_order_items,
    returns,
    return_items,
)
from app.schema.hr import (
    departments,
    employees,
    employee_attachments,
    attendance,
    leave_requests,
    payroll,
)

__all__ = [
    # Auth
    "organizations",
    "users",
    "activity_logs",
    # Inventory
    "product_categories",
    "products",
    "inventory_stock",
    "suppliers",
    "supplier_products",
    "purchase_orders",
    "purchase_order_items",
    # Sales
    "customers",
    "sales_orders",
    "sales_order_items",
    "returns",
    "return_items",
    # HR
    "departments",
    "employees",
    "employee_attachments",
    "attendance",
    "leave_requests",
    "payroll",
]