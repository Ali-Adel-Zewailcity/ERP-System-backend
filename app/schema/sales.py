"""
Sales Module - SQLAlchemy Core table definitions.

Tables
------
  customers          - customer master data and credit limits
  sales_orders       - order header (state machine: Draft → … → Delivered)
  sales_order_items  - line items on a sales order
  returns            - customer return requests
  return_items       - products included in a return
"""

import sqlalchemy as sa
from app.db.metadata import metadata

# ─────────────────────────────────────────────────────────────────────────────
# customers
# ─────────────────────────────────────────────────────────────────────────────
customers = sa.Table(
    "customers",
    metadata,
    sa.Column("id",           sa.Integer,        primary_key=True, autoincrement=True),
    sa.Column("org_id",       sa.Integer,        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
              nullable=False, index=True),
    sa.Column("name",         sa.String(150),    nullable=False),
    sa.Column("email",        sa.String(255),    nullable=True),
    sa.Column("phone",        sa.String(20),     nullable=True),
    sa.Column("address",      sa.Text,           nullable=True),
    # Maximum outstanding balance allowed for this customer.
    sa.Column("credit_limit", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
    sa.Column("notes",        sa.Text,           nullable=True),
    sa.Column("created_at",   sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.Column("updated_at",   sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now(), onupdate=sa.func.now()),
    sa.CheckConstraint("credit_limit >= 0", name="ck_customers_credit_limit_non_negative"),
    sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true"))
)

# ─────────────────────────────────────────────────────────────────────────────
# sales_orders
# State machine (SRS §2.2 Function 5):
#   Draft → Confirmed → Processing → Shipped → Delivered
#                     ↘ Cancelled (from any active state)
# ─────────────────────────────────────────────────────────────────────────────
_ORDER_STATUSES = "('draft','confirmed','processing','shipped','delivered','cancelled')"

sales_orders = sa.Table(
    "sales_orders",
    metadata,
    sa.Column("id",           sa.Integer,        primary_key=True, autoincrement=True),
    sa.Column("org_id",       sa.Integer,        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
              nullable=False, index=True),
    sa.Column("customer_id",  sa.Integer,        sa.ForeignKey("customers.id", ondelete="RESTRICT"),
              nullable=False, index=True),
    sa.Column("created_by",   sa.Integer,        sa.ForeignKey("users.id", ondelete="SET NULL"),
              nullable=True),
    sa.Column("status",       sa.String(20),     nullable=False, server_default=sa.text("'draft'")),
    sa.Column("total_amount", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
    sa.Column("notes",        sa.Text,           nullable=True),
    sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("shipped_at",   sa.DateTime(timezone=True), nullable=True),
    sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at",   sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.Column("updated_at",   sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now(), onupdate=sa.func.now()),
    sa.CheckConstraint(
        f"status IN {_ORDER_STATUSES}",
        name="ck_sales_orders_valid_status",
    ),
    sa.CheckConstraint("total_amount >= 0", name="ck_sales_orders_total_non_negative"),
)

# ─────────────────────────────────────────────────────────────────────────────
# sales_order_items
# ─────────────────────────────────────────────────────────────────────────────
sales_order_items = sa.Table(
    "sales_order_items",
    metadata,
    sa.Column("id",         sa.Integer,        primary_key=True, autoincrement=True),
    sa.Column("order_id",   sa.Integer,        sa.ForeignKey("sales_orders.id", ondelete="CASCADE"),
              nullable=False, index=True),
    sa.Column("product_id", sa.Integer,        sa.ForeignKey("products.id", ondelete="RESTRICT"),
              nullable=False),
    sa.Column("quantity",   sa.Integer,        nullable=False),
    # Price locked at the time the order was created.
    sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
    sa.CheckConstraint("quantity   > 0", name="ck_sales_order_items_quantity_positive"),
    sa.CheckConstraint("unit_price > 0", name="ck_sales_order_items_unit_price_positive"),
)

# ─────────────────────────────────────────────────────────────────────────────
# returns
# ─────────────────────────────────────────────────────────────────────────────
_RETURN_STATUSES = "('pending','approved','rejected','completed')"

returns = sa.Table(
    "returns",
    metadata,
    sa.Column("id",             sa.Integer,        primary_key=True, autoincrement=True),
    sa.Column("org_id",         sa.Integer,        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
              nullable=False, index=True),
    sa.Column("order_id",       sa.Integer,        sa.ForeignKey("sales_orders.id", ondelete="RESTRICT"),
              nullable=False, index=True),
    sa.Column("processed_by",   sa.Integer,        sa.ForeignKey("users.id", ondelete="SET NULL"),
              nullable=True),
    sa.Column("reason",         sa.Text,           nullable=True),
    sa.Column("status",         sa.String(15),     nullable=False, server_default=sa.text("'pending'")),
    sa.Column("refund_amount",  sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
    sa.Column("created_at",     sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.Column("resolved_at",    sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint(
        f"status IN {_RETURN_STATUSES}",
        name="ck_returns_valid_status",
    ),
    sa.CheckConstraint("refund_amount >= 0", name="ck_returns_refund_non_negative"),
)

# ─────────────────────────────────────────────────────────────────────────────
# return_items
# ─────────────────────────────────────────────────────────────────────────────
return_items = sa.Table(
    "return_items",
    metadata,
    sa.Column("id",         sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("return_id",  sa.Integer, sa.ForeignKey("returns.id", ondelete="CASCADE"),
              nullable=False, index=True),
    sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="RESTRICT"),
              nullable=False),
    sa.Column("quantity",   sa.Integer, nullable=False),
    sa.Column("inspection_status", sa.String(10), nullable=True,
              comment="pass = قابل للبيع, fail = تالف"),
    sa.Column("refund_method",    sa.String(20), nullable=True,
              comment="cash, bank_transfer, credit_note, replace"),
    sa.CheckConstraint("quantity > 0", name="ck_return_items_quantity_positive"),
    sa.CheckConstraint(
        "inspection_status IS NULL OR inspection_status IN ('pass','fail')",
        name="ck_return_items_inspection_status",
    ),
    sa.CheckConstraint(
        "refund_method IS NULL OR refund_method IN ('cash','bank_transfer','credit_note','replace')",
        name="ck_return_items_refund_method",
    ),
)

