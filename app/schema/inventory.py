"""
Inventory Module - SQLAlchemy Core table definitions.

Tables
------
  product_categories   - organisational grouping for products
  products             - full product catalog (SKU, price, cost, image …)
  inventory_stock      - real-time stock levels per product (1-to-1 with products)
  suppliers            - supplier master data
  supplier_products    - M2M: which suppliers provide which products
  purchase_orders      - inbound orders placed with suppliers
  purchase_order_items - line items on a purchase order
"""

import sqlalchemy as sa
from app.db.metadata import metadata

# ─────────────────────────────────────────────────────────────────────────────
# product_categories
# ─────────────────────────────────────────────────────────────────────────────
product_categories = sa.Table(
    "product_categories",
    metadata,
    sa.Column("id",          sa.Integer,     primary_key=True, autoincrement=True),
    sa.Column("org_id",      sa.Integer,     sa.ForeignKey("organizations.id", ondelete="CASCADE"),
              nullable=False, index=True),
    sa.Column("name",        sa.String(100), nullable=False),
    sa.Column("description", sa.Text,        nullable=True),
    sa.Column("created_at",  sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.UniqueConstraint("org_id", "name", name="uq_product_categories_org_id_name"),
)

# ─────────────────────────────────────────────────────────────────────────────
# products
# ─────────────────────────────────────────────────────────────────────────────
products = sa.Table(
    "products",
    metadata,
    sa.Column("id",          sa.Integer,       primary_key=True, autoincrement=True),
    sa.Column("org_id",      sa.Integer,       sa.ForeignKey("organizations.id", ondelete="CASCADE"),
              nullable=False, index=True),
    sa.Column("category_id", sa.Integer,       sa.ForeignKey("product_categories.id", ondelete="SET NULL"),
              nullable=True, index=True),
    # SKU must be unique within an organisation.
    sa.Column("sku",         sa.String(50),    nullable=False),
    sa.Column("name",        sa.String(200),   nullable=False),
    sa.Column("description", sa.Text,          nullable=True),
    sa.Column("unit_price",  sa.Numeric(12, 2), nullable=False),
    sa.Column("cost_price",  sa.Numeric(12, 2), nullable=False),
    sa.Column("is_active",  sa.Boolean,      nullable=False, server_default=sa.text("true")),
    sa.UniqueConstraint("org_id", "sku", name="uq_products_org_id_sku"),
    sa.CheckConstraint("unit_price >= 0", name="ck_products_unit_price_non_negative"),
    sa.CheckConstraint("cost_price >= 0", name="ck_products_cost_price_non_negative"),
)

# ─────────────────────────────────────────────────────────────────────────────
# inventory_stock  (1-to-1 with products)
# ─────────────────────────────────────────────────────────────────────────────
inventory_stock = sa.Table(
    "inventory_stock",
    metadata,
    sa.Column("id",                  sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("product_id",          sa.Integer, sa.ForeignKey("products.id", ondelete="CASCADE"),
              nullable=False, unique=True, index=True),
    # quantity_available: physical units ready to sell
    sa.Column("quantity_available",  sa.Integer, nullable=False, server_default=sa.text("0")),
    # quantity_reserved:  units earmarked for confirmed / processing orders
    sa.Column("quantity_reserved",   sa.Integer, nullable=False, server_default=sa.text("0")),
    # reorder_threshold:  triggers a low-stock alert when available ≤ this value
    sa.Column("reorder_threshold",   sa.Integer, nullable=False, server_default=sa.text("0")),
    sa.Column("updated_at",          sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now(), onupdate=sa.func.now()),
    sa.CheckConstraint("quantity_available >= 0", name="ck_inventory_stock_available_non_negative"),
    sa.CheckConstraint("quantity_reserved  >= 0", name="ck_inventory_stock_reserved_non_negative"),
    sa.CheckConstraint("reorder_threshold  >= 0", name="ck_inventory_stock_threshold_non_negative"),
)

# ─────────────────────────────────────────────────────────────────────────────
# suppliers
# ─────────────────────────────────────────────────────────────────────────────
suppliers = sa.Table(
    "suppliers",
    metadata,
    sa.Column("id",            sa.Integer,    primary_key=True, autoincrement=True),
    sa.Column("org_id",        sa.Integer,    sa.ForeignKey("organizations.id", ondelete="CASCADE"),
              nullable=False, index=True),
    sa.Column("name",          sa.String(150), nullable=False),
    sa.Column("contact_name",  sa.String(100), nullable=True),
    sa.Column("email",         sa.String(255), nullable=True),
    sa.Column("phone",         sa.String(20),  nullable=True),
    sa.Column("address",       sa.Text,        nullable=True),
    # e.g. "Net 30", "Net 60", "COD"
    sa.Column("is_active",    sa.Boolean,      nullable=False, server_default=sa.text("true")),
    sa.Column("updated_at",    sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
)

# ─────────────────────────────────────────────────────────────────────────────
# supplier_products  (M2M junction)
# ─────────────────────────────────────────────────────────────────────────────
supplier_products = sa.Table(
    "supplier_products",
    metadata,
    sa.Column("supplier_id", sa.Integer, sa.ForeignKey("suppliers.id", ondelete="CASCADE"),
              primary_key=True, nullable=False),
    sa.Column("product_id",  sa.Integer, sa.ForeignKey("products.id",  ondelete="CASCADE"),
              primary_key=True, nullable=False),
    # Supplier's quoted price for this specific product.
    sa.Column("supplier_sku",   sa.String(50),     nullable=True),
    sa.Column("supplier_price", sa.Numeric(12, 2), nullable=True),
    sa.Column("lead_time_days", sa.Integer,        nullable=True),
sa.Column("is_preferred",   sa.Boolean,        nullable=False, server_default=sa.text("false"))
)

# ─────────────────────────────────────────────────────────────────────────────
# purchase_orders
# ─────────────────────────────────────────────────────────────────────────────
_PO_STATUSES = "('draft','ordered','partially_received','received','cancelled')"

purchase_orders = sa.Table(
    "purchase_orders",
    metadata,
    sa.Column("id",           sa.Integer,       primary_key=True, autoincrement=True),
    sa.Column("org_id",       sa.Integer,       sa.ForeignKey("organizations.id", ondelete="CASCADE"),
              nullable=False, index=True),
    sa.Column("supplier_id",  sa.Integer,       sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
              nullable=False, index=True),
    sa.Column("created_by",   sa.Integer,       sa.ForeignKey("users.id", ondelete="SET NULL"),
              nullable=True),
    sa.Column("status",       sa.String(25),    nullable=False, server_default=sa.text("'draft'")),
    sa.Column("total_amount", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
    sa.Column("notes",        sa.Text,           nullable=True),
    sa.Column("ordered_at",   sa.DateTime(timezone=True), nullable=True),
    sa.Column("received_at",  sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at",   sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.Column("updated_at",   sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now(), onupdate=sa.func.now()),
    sa.CheckConstraint(
        f"status IN {_PO_STATUSES}",
        name="ck_purchase_orders_valid_status",
    ),
    sa.CheckConstraint("total_amount >= 0", name="ck_purchase_orders_total_non_negative"),
)

# ─────────────────────────────────────────────────────────────────────────────
# purchase_order_items
# ─────────────────────────────────────────────────────────────────────────────
purchase_order_items = sa.Table(
    "purchase_order_items",
    metadata,
    sa.Column("id",               sa.Integer,       primary_key=True, autoincrement=True),
    sa.Column("order_id",         sa.Integer,       sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
              nullable=False, index=True),
    sa.Column("product_id",       sa.Integer,       sa.ForeignKey("products.id", ondelete="RESTRICT"),
              nullable=False),
    sa.Column("quantity_ordered",  sa.Integer,       nullable=False),
    sa.Column("quantity_received", sa.Integer,       nullable=False, server_default=sa.text("0")),
    sa.Column("unit_cost",         sa.Numeric(12, 2), nullable=False),
    sa.CheckConstraint("quantity_ordered  > 0",  name="ck_po_items_quantity_ordered_positive"),
    sa.CheckConstraint("quantity_received >= 0", name="ck_po_items_quantity_received_non_negative"),
    sa.CheckConstraint("unit_cost >= 0",         name="ck_po_items_unit_cost_non_negative"),
)





