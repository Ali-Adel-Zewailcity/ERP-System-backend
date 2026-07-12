"""
Inventory utility — CRUD helper functions for inventory management.

All functions accept explicit parameters so they remain testable without
depending on FastAPI request objects (mirrors app.utils.employees).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from app.db.database import database
from app.schema.inventory import (
    products,
    product_categories,
    inventory_stock,
    suppliers,
    supplier_products,
    purchase_orders,
    purchase_order_items,
)


# ─────────────────────────────────────────────────────────────────────────────
# Shared column selectors
# ─────────────────────────────────────────────────────────────────────────────

_PRODUCT_SELECT = """
    SELECT
        products.id,
        products.org_id,
        products.category_id,
        products.sku,
        products.name,
        products.description,
        products.unit_price,
        products.cost_price,
        products.image_url,
        products.is_active,
        products.created_at,
        products.updated_at,
        product_categories.name                AS category_name,
        COALESCE(inventory_stock.quantity_available, 0) AS quantity_available,
        COALESCE(inventory_stock.quantity_reserved, 0)  AS quantity_reserved,
        COALESCE(inventory_stock.reorder_threshold, 0)  AS reorder_threshold,
        CASE
            WHEN COALESCE(inventory_stock.quantity_available, 0)
                 <= COALESCE(inventory_stock.reorder_threshold, 0)
            THEN 1 ELSE 0
        END AS is_low_stock
    FROM products
    LEFT JOIN product_categories ON product_categories.id = products.category_id
    LEFT JOIN inventory_stock ON inventory_stock.product_id = products.id
"""

_STOCK_SELECT = """
    SELECT
        inventory_stock.id,
        inventory_stock.product_id,
        inventory_stock.quantity_available,
        inventory_stock.quantity_reserved,
        inventory_stock.reorder_threshold,
        inventory_stock.updated_at,
        products.sku   AS sku,
        products.name  AS name,
        products.unit_price AS unit_price,
        ROUND(COALESCE(inventory_stock.quantity_available, 0)
            * products.unit_price, 2) AS inventory_value,
        CASE
            WHEN inventory_stock.quantity_available
                 <= inventory_stock.reorder_threshold
            THEN 1 ELSE 0
        END AS is_low_stock
    FROM inventory_stock
    JOIN products ON products.id = inventory_stock.product_id
"""


# ─────────────────────────────────────────────────────────────────────────────
# Product Categories
# ─────────────────────────────────────────────────────────────────────────────

async def create_category(org_id: int, name: str, description: str | None) -> dict[str, Any]:
    query = """
        INSERT INTO product_categories (org_id, name, description)
        VALUES (:org_id, :name, :description)
        RETURNING id, org_id, name, description, created_at
    """
    row = await database.fetch_one(query, {
        "org_id": org_id, "name": name, "description": description,
    })
    result = dict(row)
    result["product_count"] = 0
    return result


async def get_category(org_id: int, category_id: int) -> dict[str, Any] | None:
    query = """
        SELECT
            product_categories.id,
            product_categories.org_id,
            product_categories.name,
            product_categories.description,
            product_categories.created_at,
            COUNT(products.id) AS product_count
        FROM product_categories
        LEFT JOIN products ON products.category_id = product_categories.id
        WHERE product_categories.id = :id AND product_categories.org_id = :org_id
        GROUP BY product_categories.id
    """
    row = await database.fetch_one(query, {"id": category_id, "org_id": org_id})
    return dict(row) if row else None


async def list_categories(org_id: int, search: str | None = None) -> list[dict[str, Any]]:
    conditions = ["product_categories.org_id = :org_id"]
    params: dict[str, Any] = {"org_id": org_id}
    if search:
        conditions.append("product_categories.name LIKE :search")
        params["search"] = f"%{search}%"
    where = " AND ".join(conditions)
    query = f"""
        SELECT
            product_categories.id,
            product_categories.org_id,
            product_categories.name,
            product_categories.description,
            product_categories.created_at,
            COUNT(products.id) AS product_count
        FROM product_categories
        LEFT JOIN products ON products.category_id = product_categories.id
        WHERE {where}
        GROUP BY product_categories.id
        ORDER BY product_categories.name ASC
    """
    rows = await database.fetch_all(query, params)
    return [dict(r) for r in rows]


async def update_category(
    org_id: int, category_id: int, values: dict[str, Any]
) -> dict[str, Any] | None:
    if not values:
        return await get_category(org_id, category_id)
    set_clause = ", ".join(f"{k} = :{k}" for k in values)
    values["id"] = category_id
    values["org_id"] = org_id
    query = f"""
        UPDATE product_categories
        SET {set_clause}
        WHERE id = :id AND org_id = :org_id
        RETURNING id, org_id, name, description, created_at
    """
    row = await database.fetch_one(query, values)
    if not row:
        return None
    return await get_category(org_id, category_id)


async def delete_category(org_id: int, category_id: int) -> bool:
    query = "DELETE FROM product_categories WHERE id = :id AND org_id = :org_id"
    result = await database.execute(query, {"id": category_id, "org_id": org_id})
    return bool(result)


# ─────────────────────────────────────────────────────────────────────────────
# Products
# ─────────────────────────────────────────────────────────────────────────────

PRODUCT_SORTABLE = frozenset({
    "sku", "name", "unit_price", "cost_price", "created_at", "updated_at",
})


async def _ensure_stock_row(product_id: int) -> None:
    """Ensure a 1:1 inventory_stock row exists for a product."""
    await database.execute(
        "INSERT OR IGNORE INTO inventory_stock (product_id) VALUES (:product_id)",
        {"product_id": product_id},
    )


async def create_product(
    org_id: int,
    sku: str,
    name: str,
    description: str | None,
    category_id: int | None,
    unit_price: Decimal,
    cost_price: Decimal,
    image_url: str | None,
    is_active: bool,
) -> dict[str, Any]:
    async with database.transaction():
        query = """
            INSERT INTO products
                (org_id, category_id, sku, name, description,
                 unit_price, cost_price, image_url, is_active)
            VALUES
                (:org_id, :category_id, :sku, :name, :description,
                 :unit_price, :cost_price, :image_url, :is_active)
            RETURNING id
        """
        row = await database.fetch_one(query, {
            "org_id": org_id,
            "category_id": category_id,
            "sku": sku,
            "name": name,
            "description": description,
            "unit_price": str(unit_price),
            "cost_price": str(cost_price),
            "image_url": image_url,
            "is_active": is_active,
        })
        await _ensure_stock_row(row["id"])
    return await get_product(org_id, row["id"])


async def get_product(org_id: int, product_id: int) -> dict[str, Any] | None:
    query = _PRODUCT_SELECT + """
        WHERE products.id = :id AND products.org_id = :org_id
    """
    row = await database.fetch_one(query, {"id": product_id, "org_id": org_id})
    return dict(row) if row else None


async def list_products(
    org_id: int,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    category_id: int | None = None,
    is_active: bool | None = None,
    low_stock: bool = False,
    sort_by: str = "id",
    sort_order: str = "asc",
) -> tuple[list[dict[str, Any]], int]:
    conditions = ["products.org_id = :org_id"]
    params: dict[str, Any] = {"org_id": org_id}

    if search:
        conditions.append("(products.name LIKE :search OR products.sku LIKE :search)")
        params["search"] = f"%{search}%"
    if category_id is not None:
        conditions.append("products.category_id = :category_id")
        params["category_id"] = category_id
    if is_active is not None:
        conditions.append("products.is_active = :is_active")
        params["is_active"] = is_active
    if low_stock:
        conditions.append(
            "COALESCE(inventory_stock.quantity_available, 0) "
            "<= COALESCE(inventory_stock.reorder_threshold, 0)"
        )

    where = " AND ".join(conditions)

    count_query = f"""
        SELECT COUNT(*) FROM products
        LEFT JOIN inventory_stock ON inventory_stock.product_id = products.id
        WHERE {where}
    """
    total = (await database.fetch_val(count_query, params)) or 0

    if sort_by not in PRODUCT_SORTABLE:
        sort_by = "id"
    order_dir = "DESC" if sort_order.lower() == "desc" else "ASC"
    sort_col = f"products.{sort_by}"

    offset = (page - 1) * page_size
    data_query = f"""
        {_PRODUCT_SELECT}
        WHERE {where}
        ORDER BY {sort_col} {order_dir}, products.id
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = page_size
    params["offset"] = offset
    rows = await database.fetch_all(data_query, params)
    return [dict(r) for r in rows], total


async def get_product_stats(org_id: int) -> dict[str, Any]:
    query = """
        SELECT
            COUNT(*)                                                       AS total,
            SUM(CASE WHEN products.is_active = 1 THEN 1 ELSE 0 END)       AS active,
            SUM(CASE WHEN products.is_active = 0 THEN 1 ELSE 0 END)       AS inactive,
            SUM(CASE WHEN COALESCE(inventory_stock.quantity_available, 0)
                          <= COALESCE(inventory_stock.reorder_threshold, 0)
                     THEN 1 ELSE 0 END)                                   AS low_stock,
            SUM(CASE WHEN COALESCE(inventory_stock.quantity_available, 0) = 0
                     THEN 1 ELSE 0 END)                                   AS out_of_stock,
            COALESCE(SUM(COALESCE(inventory_stock.quantity_available, 0)), 0) AS total_stock_units,
            ROUND(COALESCE(SUM(COALESCE(inventory_stock.quantity_available, 0)
                          * products.unit_price), 0), 2)                  AS total_inventory_value
        FROM products
        LEFT JOIN inventory_stock ON inventory_stock.product_id = products.id
        WHERE products.org_id = :org_id
    """
    row = await database.fetch_one(query, {"org_id": org_id})
    return {
        "total": row["total"] or 0,
        "active": row["active"] or 0,
        "inactive": row["inactive"] or 0,
        "low_stock": row["low_stock"] or 0,
        "out_of_stock": row["out_of_stock"] or 0,
        "total_stock_units": int(row["total_stock_units"] or 0),
        "total_inventory_value": Decimal(str(row["total_inventory_value"] or 0)),
    }


async def update_product(
    org_id: int, product_id: int, values: dict[str, Any]
) -> dict[str, Any] | None:
    if not values:
        return await get_product(org_id, product_id)
    set_clause = ", ".join(f"{k} = :{k}" for k in values)
    values["id"] = product_id
    values["org_id"] = org_id
    query = f"""
        UPDATE products
        SET {set_clause}
        WHERE id = :id AND org_id = :org_id
        RETURNING id
    """
    row = await database.fetch_one(query, values)
    if not row:
        return None
    await _ensure_stock_row(product_id)
    return await get_product(org_id, product_id)


async def delete_product(org_id: int, product_id: int) -> bool:
    query = "DELETE FROM products WHERE id = :id AND org_id = :org_id"
    result = await database.execute(query, {"id": product_id, "org_id": org_id})
    return bool(result)


# ─────────────────────────────────────────────────────────────────────────────
# Inventory Stock
# ─────────────────────────────────────────────────────────────────────────────

async def get_stock_for_product(org_id: int, product_id: int) -> dict[str, Any] | None:
    query = _STOCK_SELECT + """
        WHERE inventory_stock.product_id = :product_id
          AND products.org_id = :org_id
    """
    row = await database.fetch_one(query, {"product_id": product_id, "org_id": org_id})
    return dict(row) if row else None


async def list_stock(
    org_id: int,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    low_stock: bool = False,
    sort_by: str = "product_id",
    sort_order: str = "asc",
) -> tuple[list[dict[str, Any]], int]:
    conditions = ["products.org_id = :org_id"]
    params: dict[str, Any] = {"org_id": org_id}
    if search:
        conditions.append("(products.name LIKE :search OR products.sku LIKE :search)")
        params["search"] = f"%{search}%"
    if low_stock:
        conditions.append(
            "inventory_stock.quantity_available <= inventory_stock.reorder_threshold"
        )
    where = " AND ".join(conditions)

    count_query = f"""
        SELECT COUNT(*) FROM inventory_stock
        JOIN products ON products.id = inventory_stock.product_id
        WHERE {where}
    """
    total = (await database.fetch_val(count_query, params)) or 0

    allowed = {"product_id", "quantity_available", "quantity_reserved",
               "reorder_threshold", "name", "sku"}
    if sort_by not in allowed:
        sort_by = "product_id"
    order_dir = "DESC" if sort_order.lower() == "desc" else "ASC"

    offset = (page - 1) * page_size
    data_query = f"""
        {_STOCK_SELECT}
        WHERE {where}
        ORDER BY {sort_by} {order_dir}, inventory_stock.product_id
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = page_size
    params["offset"] = offset
    rows = await database.fetch_all(data_query, params)
    return [dict(r) for r in rows], total


async def list_low_stock(org_id: int) -> list[dict[str, Any]]:
    query = _STOCK_SELECT + """
        WHERE products.org_id = :org_id
          AND inventory_stock.quantity_available <= inventory_stock.reorder_threshold
        ORDER BY inventory_stock.quantity_available ASC
    """
    rows = await database.fetch_all(query, {"org_id": org_id})
    return [dict(r) for r in rows]


async def adjust_stock(
    org_id: int,
    product_id: int,
    values: dict[str, Any],
) -> dict[str, Any] | None:
    """Apply a validated stock adjustment.

    `values` must already contain only safe SET expressions (keys in the
    whitelist). Numeric deltas are applied in SQL.
    """
    if not values:
        return await get_stock_for_product(org_id, product_id)
    set_clause = ", ".join(f"{k} = :{k}" for k in values)
    values["product_id"] = product_id
    query = f"""
        UPDATE inventory_stock
        SET {set_clause}
        WHERE product_id = :product_id
        RETURNING id
    """
    row = await database.fetch_one(query, values)
    if not row:
        return None
    return await get_stock_for_product(org_id, product_id)


# ─────────────────────────────────────────────────────────────────────────────
# Suppliers
# ─────────────────────────────────────────────────────────────────────────────

async def create_supplier(
    org_id: int,
    name: str,
    contact_name: str | None,
    email: str | None,
    phone: str | None,
    address: str | None,
    payment_terms: str | None,
    is_active: bool,
) -> dict[str, Any]:
    query = """
        INSERT INTO suppliers
            (org_id, name, contact_name, email, phone, address, payment_terms, is_active)
        VALUES
            (:org_id, :name, :contact_name, :email, :phone, :address, :payment_terms, :is_active)
        RETURNING id, org_id, name, contact_name, email, phone, address,
                  payment_terms, is_active, created_at, updated_at
    """
    row = await database.fetch_one(query, {
        "org_id": org_id, "name": name, "contact_name": contact_name,
        "email": email, "phone": phone, "address": address,
        "payment_terms": payment_terms, "is_active": is_active,
    })
    result = dict(row)
    result["product_count"] = 0
    return result


async def get_supplier(org_id: int, supplier_id: int) -> dict[str, Any] | None:
    query = """
        SELECT
            suppliers.id, suppliers.org_id, suppliers.name, suppliers.contact_name,
            suppliers.email, suppliers.phone, suppliers.address, suppliers.payment_terms,
            suppliers.is_active, suppliers.created_at, suppliers.updated_at,
            COUNT(supplier_products.product_id) AS product_count
        FROM suppliers
        LEFT JOIN supplier_products ON supplier_products.supplier_id = suppliers.id
        WHERE suppliers.id = :id AND suppliers.org_id = :org_id
        GROUP BY suppliers.id
    """
    row = await database.fetch_one(query, {"id": supplier_id, "org_id": org_id})
    return dict(row) if row else None


async def list_suppliers(
    org_id: int,
    search: str | None = None,
    is_active: bool | None = None,
) -> list[dict[str, Any]]:
    conditions = ["suppliers.org_id = :org_id"]
    params: dict[str, Any] = {"org_id": org_id}
    if search:
        conditions.append("(suppliers.name LIKE :search OR suppliers.email LIKE :search)")
        params["search"] = f"%{search}%"
    if is_active is not None:
        conditions.append("suppliers.is_active = :is_active")
        params["is_active"] = is_active
    where = " AND ".join(conditions)
    query = f"""
        SELECT
            suppliers.id, suppliers.org_id, suppliers.name, suppliers.contact_name,
            suppliers.email, suppliers.phone, suppliers.address, suppliers.payment_terms,
            suppliers.is_active, suppliers.created_at, suppliers.updated_at,
            COUNT(supplier_products.product_id) AS product_count
        FROM suppliers
        LEFT JOIN supplier_products ON supplier_products.supplier_id = suppliers.id
        WHERE {where}
        GROUP BY suppliers.id
        ORDER BY suppliers.name ASC
    """
    rows = await database.fetch_all(query, params)
    return [dict(r) for r in rows]


async def get_supplier_stats(org_id: int) -> dict[str, Any]:
    query = """
        SELECT
            COUNT(*)                                                 AS total,
            SUM(CASE WHEN suppliers.is_active = 1 THEN 1 ELSE 0 END) AS active,
            SUM(CASE WHEN suppliers.is_active = 0 THEN 1 ELSE 0 END) AS inactive,
            COUNT(DISTINCT supplier_products.product_id)             AS with_products
        FROM suppliers
        LEFT JOIN supplier_products ON supplier_products.supplier_id = suppliers.id
        WHERE suppliers.org_id = :org_id
    """
    row = await database.fetch_one(query, {"org_id": org_id})
    return {
        "total": row["total"] or 0,
        "active": row["active"] or 0,
        "inactive": row["inactive"] or 0,
        "with_products": row["with_products"] or 0,
    }


async def update_supplier(
    org_id: int, supplier_id: int, values: dict[str, Any]
) -> dict[str, Any] | None:
    if not values:
        return await get_supplier(org_id, supplier_id)
    set_clause = ", ".join(f"{k} = :{k}" for k in values)
    values["id"] = supplier_id
    values["org_id"] = org_id
    query = f"""
        UPDATE suppliers
        SET {set_clause}
        WHERE id = :id AND org_id = :org_id
        RETURNING id
    """
    row = await database.fetch_one(query, values)
    if not row:
        return None
    return await get_supplier(org_id, supplier_id)


async def delete_supplier(org_id: int, supplier_id: int) -> bool:
    query = "DELETE FROM suppliers WHERE id = :id AND org_id = :org_id"
    result = await database.execute(query, {"id": supplier_id, "org_id": org_id})
    return bool(result)


# ─────────────────────────────────────────────────────────────────────────────
# Supplier Products (M2M)
# ─────────────────────────────────────────────────────────────────────────────

_SUPPLIER_PRODUCT_SELECT = """
    SELECT
        supplier_products.supplier_id,
        supplier_products.product_id,
        supplier_products.supplier_sku,
        supplier_products.supplier_price,
        supplier_products.lead_time_days,
        supplier_products.is_preferred,
        products.sku        AS sku,
        products.name       AS name,
        products.unit_price AS unit_price
    FROM supplier_products
    JOIN products ON products.id = supplier_products.product_id
"""


async def list_supplier_products(supplier_id: int) -> list[dict[str, Any]]:
    query = _SUPPLIER_PRODUCT_SELECT + """
        WHERE supplier_products.supplier_id = :supplier_id
        ORDER BY products.name ASC
    """
    rows = await database.fetch_all(query, {"supplier_id": supplier_id})
    return [dict(r) for r in rows]


async def list_product_suppliers(org_id: int, product_id: int) -> list[dict[str, Any]]:
    query = _SUPPLIER_PRODUCT_SELECT + """
        JOIN suppliers ON suppliers.id = supplier_products.supplier_id
        WHERE supplier_products.product_id = :product_id
          AND suppliers.org_id = :org_id
        ORDER BY supplier_products.is_preferred DESC, suppliers.name ASC
    """
    rows = await database.fetch_all(query, {"product_id": product_id, "org_id": org_id})
    return [dict(r) for r in rows]


async def get_supplier_product(
    supplier_id: int, product_id: int
) -> dict[str, Any] | None:
    query = _SUPPLIER_PRODUCT_SELECT + """
        WHERE supplier_products.supplier_id = :supplier_id
          AND supplier_products.product_id = :product_id
    """
    row = await database.fetch_one(query, {"supplier_id": supplier_id, "product_id": product_id})
    return dict(row) if row else None


async def add_supplier_product(
    supplier_id: int,
    product_id: int,
    supplier_sku: str | None,
    supplier_price: Decimal | None,
    lead_time_days: int | None,
    is_preferred: bool,
) -> dict[str, Any]:
    query = """
        INSERT INTO supplier_products
            (supplier_id, product_id, supplier_sku, supplier_price, lead_time_days, is_preferred)
        VALUES
            (:supplier_id, :product_id, :supplier_sku, :supplier_price, :lead_time_days, :is_preferred)
        ON CONFLICT (supplier_id, product_id) DO UPDATE SET
            supplier_sku    = COALESCE(:supplier_sku, supplier_products.supplier_sku),
            supplier_price  = COALESCE(:supplier_price, supplier_products.supplier_price),
            lead_time_days  = COALESCE(:lead_time_days, supplier_products.lead_time_days),
            is_preferred    = :is_preferred
        RETURNING supplier_id, product_id
    """
    await database.fetch_one(query, {
        "supplier_id": supplier_id,
        "product_id": product_id,
        "supplier_sku": supplier_sku,
        "supplier_price": str(supplier_price) if supplier_price is not None else None,
        "lead_time_days": lead_time_days,
        "is_preferred": is_preferred,
    })
    return await get_supplier_product(supplier_id, product_id)


async def update_supplier_product(
    supplier_id: int,
    product_id: int,
    values: dict[str, Any],
) -> dict[str, Any] | None:
    if not values:
        return await get_supplier_product(supplier_id, product_id)
    set_clause = ", ".join(f"{k} = :{k}" for k in values)
    values["supplier_id"] = supplier_id
    values["product_id"] = product_id
    query = f"""
        UPDATE supplier_products
        SET {set_clause}
        WHERE supplier_id = :supplier_id AND product_id = :product_id
        RETURNING supplier_id, product_id
    """
    row = await database.fetch_one(query, values)
    if not row:
        return None
    return await get_supplier_product(supplier_id, product_id)


async def remove_supplier_product(supplier_id: int, product_id: int) -> bool:
    query = """
        DELETE FROM supplier_products
        WHERE supplier_id = :supplier_id AND product_id = :product_id
    """
    result = await database.execute(query, {"supplier_id": supplier_id, "product_id": product_id})
    return bool(result)


async def supplier_has_orders(org_id: int, supplier_id: int) -> bool:
    query = """
        SELECT 1 FROM purchase_orders
        WHERE supplier_id = :supplier_id AND org_id = :org_id
        LIMIT 1
    """
    row = await database.fetch_one(query, {"supplier_id": supplier_id, "org_id": org_id})
    return row is not None


# ─────────────────────────────────────────────────────────────────────────────
# Purchase Orders
# ─────────────────────────────────────────────────────────────────────────────

_PO_SELECT = """
    SELECT
        purchase_orders.id,
        purchase_orders.org_id,
        purchase_orders.supplier_id,
        purchase_orders.created_by,
        purchase_orders.status,
        purchase_orders.total_amount,
        purchase_orders.notes,
        purchase_orders.ordered_at,
        purchase_orders.received_at,
        purchase_orders.created_at,
        purchase_orders.updated_at,
        suppliers.name AS supplier_name,
        COUNT(purchase_order_items.id) AS item_count,
        COALESCE(SUM(purchase_order_items.quantity_received), 0) AS received_count
    FROM purchase_orders
    JOIN suppliers ON suppliers.id = purchase_orders.supplier_id
    LEFT JOIN purchase_order_items ON purchase_order_items.order_id = purchase_orders.id
"""

_PO_ITEM_SELECT = """
    SELECT
        purchase_order_items.id,
        purchase_order_items.order_id,
        purchase_order_items.product_id,
        purchase_order_items.quantity_ordered,
        purchase_order_items.quantity_received,
        purchase_order_items.unit_cost,
        products.sku  AS sku,
        products.name AS name
    FROM purchase_order_items
    JOIN products ON products.id = purchase_order_items.product_id
"""


async def _recalc_po_total(order_id: int) -> Decimal:
    query = """
        SELECT COALESCE(SUM(quantity_ordered * unit_cost), 0) AS total
        FROM purchase_order_items
        WHERE order_id = :order_id
    """
    row = await database.fetch_one(query, {"order_id": order_id})
    total = Decimal(str(row["total"] or 0))
    await database.execute(
        "UPDATE purchase_orders SET total_amount = :total WHERE id = :order_id",
        {"total": str(total), "order_id": order_id},
    )
    return total


async def create_purchase_order(
    org_id: int,
    supplier_id: int,
    created_by: int | None,
    notes: str | None,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    async with database.transaction():
        po_query = """
            INSERT INTO purchase_orders (org_id, supplier_id, created_by, status, notes, total_amount)
            VALUES (:org_id, :supplier_id, :created_by, 'draft', :notes, 0)
            RETURNING id
        """
        po = await database.fetch_one(po_query, {
            "org_id": org_id, "supplier_id": supplier_id,
            "created_by": created_by, "notes": notes,
        })
        order_id = po["id"]
        for item in items:
            await database.execute(
                """
                INSERT INTO purchase_order_items
                    (order_id, product_id, quantity_ordered, quantity_received, unit_cost)
                VALUES
                    (:order_id, :product_id, :quantity_ordered, 0, :unit_cost)
                """,
                {
                    "order_id": order_id,
                    "product_id": item["product_id"],
                    "quantity_ordered": item["quantity_ordered"],
                    "unit_cost": str(item["unit_cost"]),
                },
            )
        await _recalc_po_total(order_id)
    return await get_purchase_order(org_id, order_id)


async def get_purchase_order(org_id: int, order_id: int) -> dict[str, Any] | None:
    query = _PO_SELECT + """
        WHERE purchase_orders.id = :id AND purchase_orders.org_id = :org_id
        GROUP BY purchase_orders.id
    """
    row = await database.fetch_one(query, {"id": order_id, "org_id": org_id})
    if not row:
        return None
    result = dict(row)
    item_query = _PO_ITEM_SELECT + """
        WHERE purchase_order_items.order_id = :order_id
        ORDER BY purchase_order_items.id ASC
    """
    items = await database.fetch_all(item_query, {"order_id": order_id})
    result["items"] = [dict(i) for i in items]
    return result


async def list_purchase_orders(
    org_id: int,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    supplier_id: int | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[dict[str, Any]], int]:
    conditions = ["purchase_orders.org_id = :org_id"]
    params: dict[str, Any] = {"org_id": org_id}
    if status:
        conditions.append("purchase_orders.status = :status")
        params["status"] = status
    if supplier_id is not None:
        conditions.append("purchase_orders.supplier_id = :supplier_id")
        params["supplier_id"] = supplier_id
    where = " AND ".join(conditions)

    count_query = f"""
        SELECT COUNT(*) FROM purchase_orders WHERE {where}
    """
    total = (await database.fetch_val(count_query, params)) or 0

    allowed = {"created_at", "updated_at", "status", "total_amount", "id"}
    if sort_by not in allowed:
        sort_by = "created_at"
    order_dir = "DESC" if sort_order.lower() == "desc" else "ASC"

    offset = (page - 1) * page_size
    data_query = f"""
        {_PO_SELECT}
        WHERE {where}
        GROUP BY purchase_orders.id
        ORDER BY purchase_orders.{sort_by} {order_dir}, purchase_orders.id
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = page_size
    params["offset"] = offset
    rows = await database.fetch_all(data_query, params)
    return [dict(r) for r in rows], total


async def get_po_stats(org_id: int) -> dict[str, Any]:
    query = """
        SELECT
            COUNT(*)                                                          AS total,
            SUM(CASE WHEN status = 'draft'             THEN 1 ELSE 0 END)     AS draft,
            SUM(CASE WHEN status = 'ordered'           THEN 1 ELSE 0 END)     AS ordered,
            SUM(CASE WHEN status = 'partially_received' THEN 1 ELSE 0 END)    AS partially_received,
            SUM(CASE WHEN status = 'received'          THEN 1 ELSE 0 END)     AS received,
            SUM(CASE WHEN status = 'cancelled'         THEN 1 ELSE 0 END)     AS cancelled,
            COALESCE(SUM(CASE WHEN status IN ('draft','ordered','partially_received')
                              THEN total_amount ELSE 0 END), 0)                AS open_value
        FROM purchase_orders
        WHERE org_id = :org_id
    """
    row = await database.fetch_one(query, {"org_id": org_id})
    return {
        "total": row["total"] or 0,
        "draft": row["draft"] or 0,
        "ordered": row["ordered"] or 0,
        "partially_received": row["partially_received"] or 0,
        "received": row["received"] or 0,
        "cancelled": row["cancelled"] or 0,
        "open_value": Decimal(str(row["open_value"] or 0)),
    }


async def update_purchase_order(
    org_id: int, order_id: int, values: dict[str, Any]
) -> dict[str, Any] | None:
    if not values:
        return await get_purchase_order(org_id, order_id)
    set_clause = ", ".join(f"{k} = :{k}" for k in values)
    values["id"] = order_id
    values["org_id"] = org_id
    query = f"""
        UPDATE purchase_orders
        SET {set_clause}
        WHERE id = :id AND org_id = :org_id
        RETURNING id
    """
    row = await database.fetch_one(query, values)
    if not row:
        return None
    return await get_purchase_order(org_id, order_id)


async def delete_purchase_order(org_id: int, order_id: int) -> bool:
    query = "DELETE FROM purchase_orders WHERE id = :id AND org_id = :org_id"
    result = await database.execute(query, {"id": order_id, "org_id": org_id})
    return bool(result)


async def add_po_item(
    org_id: int, order_id: int, product_id: int,
    quantity_ordered: int, unit_cost: Decimal,
) -> dict[str, Any] | None:
    async with database.transaction():
        await database.execute(
            """
            INSERT INTO purchase_order_items
                (order_id, product_id, quantity_ordered, quantity_received, unit_cost)
            VALUES (:order_id, :product_id, :quantity_ordered, 0, :unit_cost)
            """,
            {
                "order_id": order_id, "product_id": product_id,
                "quantity_ordered": quantity_ordered, "unit_cost": str(unit_cost),
            },
        )
        await _recalc_po_total(order_id)
    return await get_purchase_order(org_id, order_id)


async def update_po_item(
    org_id: int, order_id: int, item_id: int, values: dict[str, Any],
) -> dict[str, Any] | None:
    async with database.transaction():
        set_clause = ", ".join(f"{k} = :{k}" for k in values)
        values["item_id"] = item_id
        values["order_id"] = order_id
        query = f"""
            UPDATE purchase_order_items
            SET {set_clause}
            WHERE id = :item_id AND order_id = :order_id
            RETURNING id
        """
        row = await database.fetch_one(query, values)
        if not row:
            return None
        await _recalc_po_total(order_id)
    return await get_purchase_order(org_id, order_id)


async def delete_po_item(org_id: int, order_id: int, item_id: int) -> bool:
    async with database.transaction():
        query = """
            DELETE FROM purchase_order_items WHERE id = :item_id AND order_id = :order_id
        """
        result = await database.execute(query, {"item_id": item_id, "order_id": order_id})
        await _recalc_po_total(order_id)
        return bool(result)


async def get_po_item(order_id: int, item_id: int) -> dict[str, Any] | None:
    query = _PO_ITEM_SELECT + """
        WHERE purchase_order_items.id = :item_id
          AND purchase_order_items.order_id = :order_id
    """
    row = await database.fetch_one(query, {"item_id": item_id, "order_id": order_id})
    return dict(row) if row else None


async def set_po_status(
    order_id: int, status: str, ordered_at: datetime | None = None,
    received_at: datetime | None = None,
) -> None:
    query = """
        UPDATE purchase_orders
        SET status = :status,
            ordered_at = COALESCE(:ordered_at, ordered_at),
            received_at = COALESCE(:received_at, received_at)
        WHERE id = :order_id
    """
    await database.execute(query, {
        "status": status, "ordered_at": ordered_at,
        "received_at": received_at, "order_id": order_id,
    })


async def increment_stock(
    product_id: int, delta_available: int,
) -> None:
    """Atomically increase available stock for a product."""
    await _ensure_stock_row(product_id)
    await database.execute(
        """
        UPDATE inventory_stock
        SET quantity_available = quantity_available + :delta
        WHERE product_id = :product_id
        """,
        {"delta": delta_available, "product_id": product_id},
    )
