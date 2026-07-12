"""
Inventory Router — Endpoints for the Inventory Management module.

Endpoints
---------
  Categories:        /inventory/categories[/…]
  Products:          /inventory/products[/…]
  Stock:             /inventory/stock[/…]
  Suppliers:         /inventory/suppliers[/…]
  Supplier Products: /inventory/suppliers/{id}/products[/…]
  Purchase Orders:   /inventory/purchase-orders[/…]
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.db.database import database
from app.models.auth import UserResponse
from app.models.inventory import (
    CategoryCreate,
    CategoryUpdate,
    CategoryResponse,
    CategoryListResponse,
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductListResponse,
    ProductStatsResponse,
    StockAdjustRequest,
    StockResponse,
    StockListResponse,
    SupplierCreate,
    SupplierUpdate,
    SupplierResponse,
    SupplierListResponse,
    SupplierStatsResponse,
    SupplierProductCreate,
    SupplierProductUpdate,
    SupplierProductResponse,
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
    PurchaseOrderResponse,
    PurchaseOrderListResponse,
    PurchaseOrderStatsResponse,
    PurchaseOrderItemCreate,
    PurchaseOrderItemUpdate,
    ReceiveRequest,
)
from app.utils.dependency import get_current_user, require_organization_member
from app.utils.roles import require_table_access, require_write_access
from app.utils.inventory import (
    create_category,
    get_category,
    list_categories,
    update_category,
    delete_category,
    create_product,
    get_product,
    list_products,
    get_product_stats,
    update_product,
    delete_product,
    get_stock_for_product,
    list_stock,
    list_low_stock,
    adjust_stock,
    create_supplier,
    get_supplier,
    list_suppliers,
    get_supplier_stats,
    update_supplier,
    delete_supplier,
    supplier_has_orders,
    list_supplier_products,
    get_supplier_product,
    add_supplier_product,
    update_supplier_product,
    remove_supplier_product,
    create_purchase_order,
    get_purchase_order,
    list_purchase_orders,
    get_po_stats,
    update_purchase_order,
    delete_purchase_order,
    add_po_item,
    update_po_item,
    delete_po_item,
    get_po_item,
    set_po_status,
    increment_stock,
)
from app.utils.activity_log import log_activity
from app.schema.inventory import products as products_table


router = APIRouter(prefix="/inventory", tags=["Inventory"])


# ═══════════════════════════════════════════════════════════════════════════
# Product Categories
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/categories",
    status_code=status.HTTP_201_CREATED,
    response_model=CategoryResponse,
    summary="Create Product Category",
)
async def create_category_endpoint(
    req: CategoryCreate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> CategoryResponse:
    require_write_access(current_user, "product_categories")
    existing = await database.fetch_one(
        "SELECT id FROM product_categories WHERE org_id = :org_id AND name = :name",
        {"org_id": current_user.org_id, "name": req.name},
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="A category with this name already exists.")
    row = await create_category(current_user.org_id, req.name, req.description)
    await log_activity(current_user.org_id, current_user.id, "created",
                       "product_category", row["id"], new_value={"name": req.name})
    return CategoryResponse.model_validate(row)


@router.get(
    "/categories",
    response_model=CategoryListResponse,
    summary="List Product Categories",
)
async def list_categories_endpoint(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> CategoryListResponse:
    require_table_access(current_user, "product_categories")
    rows = await list_categories(current_user.org_id, search)
    items = [CategoryResponse.model_validate(r) for r in rows]
    return CategoryListResponse(items=items, total=len(items),
                                page=1, page_size=len(items), pages=1)


@router.get(
    "/categories/{category_id}",
    response_model=CategoryResponse,
    summary="Get Product Category",
)
async def get_category_endpoint(
    category_id: Annotated[int, Path(description="Category ID.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> CategoryResponse:
    require_table_access(current_user, "product_categories")
    row = await get_category(current_user.org_id, category_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Category not found.")
    return CategoryResponse.model_validate(row)


@router.put(
    "/categories/{category_id}",
    response_model=CategoryResponse,
    summary="Update Product Category",
)
async def update_category_endpoint(
    category_id: Annotated[int, Path(description="Category ID.")],
    req: CategoryUpdate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> CategoryResponse:
    require_write_access(current_user, "product_categories")
    existing = await get_category(current_user.org_id, category_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Category not found.")
    values = {k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None}
    if "name" in values and values["name"] != existing["name"]:
        dup = await database.fetch_one(
            "SELECT id FROM product_categories WHERE org_id = :org_id AND name = :name AND id != :id",
            {"org_id": current_user.org_id, "name": values["name"], "id": category_id},
        )
        if dup:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="A category with this name already exists.")
    row = await update_category(current_user.org_id, category_id, values)
    await log_activity(current_user.org_id, current_user.id, "updated",
                       "product_category", category_id, new_value=values)
    return CategoryResponse.model_validate(row)


@router.delete(
    "/categories/{category_id}",
    summary="Delete Product Category",
)
async def delete_category_endpoint(
    category_id: Annotated[int, Path(description="Category ID.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, str]:
    require_write_access(current_user, "product_categories")
    existing = await get_category(current_user.org_id, category_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Category not found.")
    await delete_category(current_user.org_id, category_id)
    await log_activity(current_user.org_id, current_user.id, "deleted",
                       "product_category", category_id, old_value={"name": existing["name"]})
    return {"message": "Category deleted successfully."}


# ═══════════════════════════════════════════════════════════════════════════
# Products
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/products",
    status_code=status.HTTP_201_CREATED,
    response_model=ProductResponse,
    summary="Create Product",
)
async def create_product_endpoint(
    req: ProductCreate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> ProductResponse:
    require_write_access(current_user, "products")
    existing = await database.fetch_one(
        "SELECT id FROM products WHERE org_id = :org_id AND sku = :sku",
        {"org_id": current_user.org_id, "sku": req.sku},
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="A product with this SKU already exists.")
    if req.category_id is not None:
        cat = await get_category(current_user.org_id, req.category_id)
        if not cat:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Category not found.")
    row = await create_product(
        org_id=current_user.org_id,
        sku=req.sku,
        name=req.name,
        description=req.description,
        category_id=req.category_id,
        unit_price=req.unit_price,
        cost_price=req.cost_price,
        image_url=req.image_url,
        is_active=req.is_active,
    )
    await log_activity(current_user.org_id, current_user.id, "created",
                       "product", row["id"], new_value={"sku": req.sku, "name": req.name})
    return ProductResponse.model_validate(row)


@router.get(
    "/products/stats",
    response_model=ProductStatsResponse,
    summary="Product Statistics",
)
async def product_stats_endpoint(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> ProductStatsResponse:
    require_table_access(current_user, "products")
    stats = await get_product_stats(current_user.org_id)
    return ProductStatsResponse(
        total=stats["total"],
        active=stats["active"],
        inactive=stats["inactive"],
        low_stock=stats["low_stock"],
        out_of_stock=stats["out_of_stock"],
        total_inventory_value=stats["total_inventory_value"],
        total_stock_units=stats["total_stock_units"],
    )


@router.get(
    "/products",
    response_model=ProductListResponse,
    summary="List Products",
)
async def list_products_endpoint(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    category_id: Annotated[int | None, Query(ge=1)] = None,
    is_active: Annotated[bool | None, Query()] = None,
    low_stock: Annotated[bool, Query()] = False,
    sort_by: Annotated[str | None, Query()] = None,
    sort_order: Annotated[str | None, Query(pattern="^(asc|desc)?$")] = None,
) -> ProductListResponse:
    require_table_access(current_user, "products")
    rows, total = await list_products(
        org_id=current_user.org_id,
        page=page,
        page_size=page_size,
        search=search,
        category_id=category_id,
        is_active=is_active,
        low_stock=low_stock,
        sort_by=sort_by or "id",
        sort_order=sort_order or "asc",
    )
    items = [ProductResponse.model_validate(r) for r in rows]
    pages = (total + page_size - 1) // page_size if total else 0
    return ProductListResponse(items=items, total=total, page=page,
                               page_size=page_size, pages=pages)


@router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    summary="Get Product",
)
async def get_product_endpoint(
    product_id: Annotated[int, Path(description="Product ID.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> ProductResponse:
    require_table_access(current_user, "products")
    row = await get_product(current_user.org_id, product_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Product not found.")
    return ProductResponse.model_validate(row)


@router.put(
    "/products/{product_id}",
    response_model=ProductResponse,
    summary="Update Product",
)
async def update_product_endpoint(
    product_id: Annotated[int, Path(description="Product ID.")],
    req: ProductUpdate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> ProductResponse:
    require_write_access(current_user, "products")
    existing = await get_product(current_user.org_id, product_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Product not found.")
    values = {k: v for k, v in req.model_dump(exclude_unset=True).items()}
    if not values:
        return ProductResponse.model_validate(existing)
    if "sku" in values and values["sku"] != existing["sku"]:
        dup = await database.fetch_one(
            "SELECT id FROM products WHERE org_id = :org_id AND sku = :sku AND id != :id",
            {"org_id": current_user.org_id, "sku": values["sku"], "id": product_id},
        )
        if dup:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="A product with this SKU already exists.")
    if "category_id" in values and values["category_id"] is not None:
        cat = await get_category(current_user.org_id, values["category_id"])
        if not cat:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Category not found.")
    row = await update_product(current_user.org_id, product_id, values)
    await log_activity(current_user.org_id, current_user.id, "updated",
                       "product", product_id, old_value={"sku": existing["sku"]},
                       new_value=values)
    return ProductResponse.model_validate(row)


@router.delete(
    "/products/{product_id}",
    summary="Delete Product",
)
async def delete_product_endpoint(
    product_id: Annotated[int, Path(description="Product ID.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, str]:
    require_write_access(current_user, "products")
    existing = await get_product(current_user.org_id, product_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Product not found.")
    await delete_product(current_user.org_id, product_id)
    await log_activity(current_user.org_id, current_user.id, "deleted",
                       "product", product_id, old_value={"sku": existing["sku"]})
    return {"message": "Product deleted successfully."}


# ═══════════════════════════════════════════════════════════════════════════
# Inventory Stock
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/stock",
    response_model=StockListResponse,
    summary="List Stock Levels",
)
async def list_stock_endpoint(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    low_stock: Annotated[bool, Query()] = False,
    sort_by: Annotated[str | None, Query()] = None,
    sort_order: Annotated[str | None, Query(pattern="^(asc|desc)?$")] = None,
) -> StockListResponse:
    require_table_access(current_user, "inventory_stock")
    rows, total = await list_stock(
        org_id=current_user.org_id,
        page=page,
        page_size=page_size,
        search=search,
        low_stock=low_stock,
        sort_by=sort_by or "product_id",
        sort_order=sort_order or "asc",
    )
    items = [StockResponse.model_validate(r) for r in rows]
    pages = (total + page_size - 1) // page_size if total else 0
    return StockListResponse(items=items, total=total, page=page,
                             page_size=page_size, pages=pages)


@router.get(
    "/stock/low",
    response_model=list[StockResponse],
    summary="Low Stock Alerts",
)
async def low_stock_endpoint(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> list[StockResponse]:
    require_table_access(current_user, "inventory_stock")
    rows = await list_low_stock(current_user.org_id)
    return [StockResponse.model_validate(r) for r in rows]


@router.get(
    "/stock/{product_id}",
    response_model=StockResponse,
    summary="Get Stock for Product",
)
async def get_stock_endpoint(
    product_id: Annotated[int, Path(description="Product ID.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> StockResponse:
    require_table_access(current_user, "inventory_stock")
    row = await get_stock_for_product(current_user.org_id, product_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Stock record not found for this product.")
    return StockResponse.model_validate(row)


@router.patch(
    "/stock/{product_id}",
    response_model=StockResponse,
    summary="Adjust Stock",
)
async def adjust_stock_endpoint(
    product_id: Annotated[int, Path(description="Product ID.")],
    req: StockAdjustRequest,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> StockResponse:
    require_write_access(current_user, "inventory_stock")
    product = await get_product(current_user.org_id, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Product not found.")

    sets: list[str] = []
    params: dict = {"product_id": product_id}
    if req.delta_available is not None:
        sets.append("quantity_available = quantity_available + :delta_available")
        params["delta_available"] = req.delta_available
    elif req.quantity_available is not None:
        sets.append("quantity_available = :quantity_available")
        params["quantity_available"] = req.quantity_available
    if req.delta_reserved is not None:
        sets.append("quantity_reserved = quantity_reserved + :delta_reserved")
        params["delta_reserved"] = req.delta_reserved
    elif req.quantity_reserved is not None:
        sets.append("quantity_reserved = :quantity_reserved")
        params["quantity_reserved"] = req.quantity_reserved
    if req.reorder_threshold is not None:
        sets.append("reorder_threshold = :reorder_threshold")
        params["reorder_threshold"] = req.reorder_threshold

    if not sets:
        row = await get_stock_for_product(current_user.org_id, product_id)
        return StockResponse.model_validate(row)

    await database.execute(
        f"UPDATE inventory_stock SET {', '.join(sets)} WHERE product_id = :product_id",
        params,
    )
    row = await get_stock_for_product(current_user.org_id, product_id)
    await log_activity(current_user.org_id, current_user.id, "stock_adjusted",
                       "inventory_stock", product_id,
                       new_value={"reason": req.reason, "changes": sets})
    return StockResponse.model_validate(row)


# ═══════════════════════════════════════════════════════════════════════════
# Suppliers
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/suppliers",
    status_code=status.HTTP_201_CREATED,
    response_model=SupplierResponse,
    summary="Create Supplier",
)
async def create_supplier_endpoint(
    req: SupplierCreate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> SupplierResponse:
    require_write_access(current_user, "suppliers")
    row = await create_supplier(
        org_id=current_user.org_id,
        name=req.name,
        contact_name=req.contact_name,
        email=req.email,
        phone=req.phone,
        address=req.address,
        payment_terms=req.payment_terms,
        is_active=req.is_active,
    )
    await log_activity(current_user.org_id, current_user.id, "created",
                       "supplier", row["id"], new_value={"name": req.name})
    return SupplierResponse.model_validate(row)


@router.get(
    "/suppliers/stats",
    response_model=SupplierStatsResponse,
    summary="Supplier Statistics",
)
async def supplier_stats_endpoint(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> SupplierStatsResponse:
    require_table_access(current_user, "suppliers")
    stats = await get_supplier_stats(current_user.org_id)
    return SupplierStatsResponse(
        total=stats["total"], active=stats["active"], inactive=stats["inactive"],
        with_products=stats["with_products"],
    )


@router.get(
    "/suppliers",
    response_model=SupplierListResponse,
    summary="List Suppliers",
)
async def list_suppliers_endpoint(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    search: Annotated[str | None, Query(max_length=100)] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> SupplierListResponse:
    require_table_access(current_user, "suppliers")
    rows = await list_suppliers(current_user.org_id, search, is_active)
    items = [SupplierResponse.model_validate(r) for r in rows]
    return SupplierListResponse(items=items, total=len(items),
                                page=1, page_size=len(items), pages=1)


@router.get(
    "/suppliers/{supplier_id}",
    response_model=SupplierResponse,
    summary="Get Supplier",
)
async def get_supplier_endpoint(
    supplier_id: Annotated[int, Path(description="Supplier ID.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> SupplierResponse:
    require_table_access(current_user, "suppliers")
    row = await get_supplier(current_user.org_id, supplier_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Supplier not found.")
    return SupplierResponse.model_validate(row)


@router.put(
    "/suppliers/{supplier_id}",
    response_model=SupplierResponse,
    summary="Update Supplier",
)
async def update_supplier_endpoint(
    supplier_id: Annotated[int, Path(description="Supplier ID.")],
    req: SupplierUpdate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> SupplierResponse:
    require_write_access(current_user, "suppliers")
    existing = await get_supplier(current_user.org_id, supplier_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Supplier not found.")
    values = {k: v for k, v in req.model_dump(exclude_unset=True).items()}
    if not values:
        return SupplierResponse.model_validate(existing)
    row = await update_supplier(current_user.org_id, supplier_id, values)
    await log_activity(current_user.org_id, current_user.id, "updated",
                       "supplier", supplier_id, new_value=values)
    return SupplierResponse.model_validate(row)


@router.delete(
    "/suppliers/{supplier_id}",
    summary="Delete Supplier",
)
async def delete_supplier_endpoint(
    supplier_id: Annotated[int, Path(description="Supplier ID.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, str]:
    require_write_access(current_user, "suppliers")
    existing = await get_supplier(current_user.org_id, supplier_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Supplier not found.")
    if await supplier_has_orders(current_user.org_id, supplier_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a supplier with existing purchase orders.")
    await delete_supplier(current_user.org_id, supplier_id)
    await log_activity(current_user.org_id, current_user.id, "deleted",
                       "supplier", supplier_id, old_value={"name": existing["name"]})
    return {"message": "Supplier deleted successfully."}


# ═══════════════════════════════════════════════════════════════════════════
# Supplier Products (M2M)
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/suppliers/{supplier_id}/products",
    response_model=list[SupplierProductResponse],
    summary="List Supplier Products",
)
async def list_supplier_products_endpoint(
    supplier_id: Annotated[int, Path(description="Supplier ID.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> list[SupplierProductResponse]:
    require_table_access(current_user, "supplier_products")
    supplier = await get_supplier(current_user.org_id, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Supplier not found.")
    rows = await list_supplier_products(supplier_id)
    return [SupplierProductResponse.model_validate(r) for r in rows]


@router.post(
    "/suppliers/{supplier_id}/products",
    status_code=status.HTTP_201_CREATED,
    response_model=SupplierProductResponse,
    summary="Add Supplier Product",
)
async def add_supplier_product_endpoint(
    supplier_id: Annotated[int, Path(description="Supplier ID.")],
    req: SupplierProductCreate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> SupplierProductResponse:
    require_write_access(current_user, "supplier_products")
    supplier = await get_supplier(current_user.org_id, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Supplier not found.")
    product = await get_product(current_user.org_id, req.product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Product not found.")
    row = await add_supplier_product(
        supplier_id, req.product_id, req.supplier_sku,
        req.supplier_price, req.lead_time_days, req.is_preferred,
    )
    await log_activity(current_user.org_id, current_user.id, "created",
                       "supplier_product", supplier_id,
                       new_value={"product_id": req.product_id})
    return SupplierProductResponse.model_validate(row)


@router.put(
    "/suppliers/{supplier_id}/products/{product_id}",
    response_model=SupplierProductResponse,
    summary="Update Supplier Product",
)
async def update_supplier_product_endpoint(
    supplier_id: Annotated[int, Path(description="Supplier ID.")],
    product_id: Annotated[int, Path(description="Product ID.")],
    req: SupplierProductUpdate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> SupplierProductResponse:
    require_write_access(current_user, "supplier_products")
    existing = await get_supplier_product(supplier_id, product_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Supplier product mapping not found.")
    values = {k: v for k, v in req.model_dump(exclude_unset=True).items()}
    row = await update_supplier_product(supplier_id, product_id, values)
    return SupplierProductResponse.model_validate(row)


@router.delete(
    "/suppliers/{supplier_id}/products/{product_id}",
    summary="Remove Supplier Product",
)
async def remove_supplier_product_endpoint(
    supplier_id: Annotated[int, Path(description="Supplier ID.")],
    product_id: Annotated[int, Path(description="Product ID.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, str]:
    require_write_access(current_user, "supplier_products")
    existing = await get_supplier_product(supplier_id, product_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Supplier product mapping not found.")
    await remove_supplier_product(supplier_id, product_id)
    return {"message": "Supplier product removed successfully."}


# ═══════════════════════════════════════════════════════════════════════════
# Purchase Orders
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/purchase-orders",
    status_code=status.HTTP_201_CREATED,
    response_model=PurchaseOrderResponse,
    summary="Create Purchase Order",
)
async def create_po_endpoint(
    req: PurchaseOrderCreate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> PurchaseOrderResponse:
    require_write_access(current_user, "purchase_orders")
    supplier = await get_supplier(current_user.org_id, req.supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Supplier not found.")
    # Validate every product belongs to this org
    seen = set()
    for item in req.items:
        if item.product_id in seen:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Duplicate product in purchase order items.")
        seen.add(item.product_id)
        product = await get_product(current_user.org_id, item.product_id)
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Product {item.product_id} not found.")
    po = await create_purchase_order(
        org_id=current_user.org_id,
        supplier_id=req.supplier_id,
        created_by=current_user.id,
        notes=req.notes,
        items=[i.model_dump() for i in req.items],
    )
    await log_activity(current_user.org_id, current_user.id, "created",
                       "purchase_order", po["id"],
                       new_value={"supplier_id": req.supplier_id})
    return PurchaseOrderResponse.model_validate(po)


@router.get(
    "/purchase-orders/stats",
    response_model=PurchaseOrderStatsResponse,
    summary="Purchase Order Statistics",
)
async def po_stats_endpoint(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> PurchaseOrderStatsResponse:
    require_table_access(current_user, "purchase_orders")
    stats = await get_po_stats(current_user.org_id)
    return PurchaseOrderStatsResponse(
        total=stats["total"], draft=stats["draft"], ordered=stats["ordered"],
        partially_received=stats["partially_received"], received=stats["received"],
        cancelled=stats["cancelled"], open_value=stats["open_value"],
    )


@router.get(
    "/purchase-orders",
    response_model=PurchaseOrderListResponse,
    summary="List Purchase Orders",
)
async def list_pos_endpoint(
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    supplier_id: Annotated[int | None, Query(ge=1)] = None,
    sort_by: Annotated[str | None, Query()] = None,
    sort_order: Annotated[str | None, Query(pattern="^(asc|desc)?$")] = None,
) -> PurchaseOrderListResponse:
    require_table_access(current_user, "purchase_orders")
    rows, total = await list_purchase_orders(
        org_id=current_user.org_id,
        page=page,
        page_size=page_size,
        status=status_filter,
        supplier_id=supplier_id,
        sort_by=sort_by or "created_at",
        sort_order=sort_order or "desc",
    )
    items = [PurchaseOrderResponse.model_validate(r) for r in rows]
    pages = (total + page_size - 1) // page_size if total else 0
    return PurchaseOrderListResponse(items=items, total=total, page=page,
                                     page_size=page_size, pages=pages)


@router.get(
    "/purchase-orders/{order_id}",
    response_model=PurchaseOrderResponse,
    summary="Get Purchase Order",
)
async def get_po_endpoint(
    order_id: Annotated[int, Path(description="Purchase Order ID.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> PurchaseOrderResponse:
    require_table_access(current_user, "purchase_orders")
    po = await get_purchase_order(current_user.org_id, order_id)
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Purchase order not found.")
    return PurchaseOrderResponse.model_validate(po)


@router.put(
    "/purchase-orders/{order_id}",
    response_model=PurchaseOrderResponse,
    summary="Update Purchase Order (draft only)",
)
async def update_po_endpoint(
    order_id: Annotated[int, Path(description="Purchase Order ID.")],
    req: PurchaseOrderUpdate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> PurchaseOrderResponse:
    require_write_access(current_user, "purchase_orders")
    po = await get_purchase_order(current_user.org_id, order_id)
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Purchase order not found.")
    if po["status"] != "draft":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Only draft purchase orders can be edited.")
    values = {k: v for k, v in req.model_dump(exclude_unset=True).items()}
    if not values:
        return PurchaseOrderResponse.model_validate(po)
    if "supplier_id" in values and values["supplier_id"] != po["supplier_id"]:
        supplier = await get_supplier(current_user.org_id, values["supplier_id"])
        if not supplier:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Supplier not found.")
    row = await update_purchase_order(current_user.org_id, order_id, values)
    return PurchaseOrderResponse.model_validate(row)


@router.delete(
    "/purchase-orders/{order_id}",
    summary="Delete Purchase Order (draft only)",
)
async def delete_po_endpoint(
    order_id: Annotated[int, Path(description="Purchase Order ID.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> dict[str, str]:
    require_write_access(current_user, "purchase_orders")
    po = await get_purchase_order(current_user.org_id, order_id)
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Purchase order not found.")
    if po["status"] != "draft":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Only draft purchase orders can be deleted.")
    await delete_purchase_order(current_user.org_id, order_id)
    await log_activity(current_user.org_id, current_user.id, "deleted",
                       "purchase_order", order_id)
    return {"message": "Purchase order deleted successfully."}


@router.post(
    "/purchase-orders/{order_id}/items",
    response_model=PurchaseOrderResponse,
    summary="Add Purchase Order Item (draft only)",
)
async def add_po_item_endpoint(
    order_id: Annotated[int, Path(description="Purchase Order ID.")],
    req: PurchaseOrderItemCreate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> PurchaseOrderResponse:
    require_write_access(current_user, "purchase_orders")
    po = await get_purchase_order(current_user.org_id, order_id)
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Purchase order not found.")
    if po["status"] != "draft":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Items can only be added to draft orders.")
    product = await get_product(current_user.org_id, req.product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Product not found.")
    row = await add_po_item(current_user.org_id, order_id, req.product_id,
                             req.quantity_ordered, req.unit_cost)
    return PurchaseOrderResponse.model_validate(row)


@router.put(
    "/purchase-orders/{order_id}/items/{item_id}",
    response_model=PurchaseOrderResponse,
    summary="Update Purchase Order Item (draft only)",
)
async def update_po_item_endpoint(
    order_id: Annotated[int, Path(description="Purchase Order ID.")],
    item_id: Annotated[int, Path(description="Item ID.")],
    req: PurchaseOrderItemUpdate,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> PurchaseOrderResponse:
    require_write_access(current_user, "purchase_orders")
    po = await get_purchase_order(current_user.org_id, order_id)
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Purchase order not found.")
    if po["status"] != "draft":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Items can only be edited on draft orders.")
    item = await get_po_item(order_id, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Purchase order item not found.")
    values = {k: v for k, v in req.model_dump(exclude_unset=True).items()}
    row = await update_po_item(current_user.org_id, order_id, item_id, values)
    return PurchaseOrderResponse.model_validate(row)


@router.delete(
    "/purchase-orders/{order_id}/items/{item_id}",
    response_model=PurchaseOrderResponse,
    summary="Delete Purchase Order Item (draft only)",
)
async def delete_po_item_endpoint(
    order_id: Annotated[int, Path(description="Purchase Order ID.")],
    item_id: Annotated[int, Path(description="Item ID.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> PurchaseOrderResponse:
    require_write_access(current_user, "purchase_orders")
    po = await get_purchase_order(current_user.org_id, order_id)
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Purchase order not found.")
    if po["status"] != "draft":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Items can only be removed from draft orders.")
    ok = await delete_po_item(current_user.org_id, order_id, item_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Purchase order item not found.")
    row = await get_purchase_order(current_user.org_id, order_id)
    return PurchaseOrderResponse.model_validate(row)


@router.post(
    "/purchase-orders/{order_id}/submit",
    response_model=PurchaseOrderResponse,
    summary="Submit Purchase Order (draft → ordered)",
)
async def submit_po_endpoint(
    order_id: Annotated[int, Path(description="Purchase Order ID.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> PurchaseOrderResponse:
    require_write_access(current_user, "purchase_orders")
    po = await get_purchase_order(current_user.org_id, order_id)
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Purchase order not found.")
    if po["status"] != "draft":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Only draft purchase orders can be submitted.")
    if po["item_count"] == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Cannot submit an order with no items.")
    await set_po_status(order_id, "ordered",
                        ordered_at=datetime.now(timezone.utc))
    row = await get_purchase_order(current_user.org_id, order_id)
    await log_activity(current_user.org_id, current_user.id, "submitted",
                       "purchase_order", order_id)
    return PurchaseOrderResponse.model_validate(row)


@router.post(
    "/purchase-orders/{order_id}/receive",
    response_model=PurchaseOrderResponse,
    summary="Receive Goods against Purchase Order",
)
async def receive_po_endpoint(
    order_id: Annotated[int, Path(description="Purchase Order ID.")],
    req: ReceiveRequest,
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> PurchaseOrderResponse:
    require_write_access(current_user, "purchase_orders")
    po = await get_purchase_order(current_user.org_id, order_id)
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Purchase order not found.")
    if po["status"] in ("draft", "cancelled", "received"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Cannot receive goods for an order in '{po['status']}' state.")

    receive_map: dict[int, int] = {}
    if req.items:
        for r in req.items:
            receive_map[r.product_id] = r.quantity
    else:
        for it in po["items"]:
            remaining = it["quantity_ordered"] - it["quantity_received"]
            if remaining > 0:
                receive_map[it["product_id"]] = remaining

    if not receive_map:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="All items have already been fully received.")

    async with database.transaction():
        for item in po["items"]:
            pid = item["product_id"]
            if pid not in receive_map:
                continue
            want = receive_map[pid]
            remaining = item["quantity_ordered"] - item["quantity_received"]
            if want > remaining:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot receive {want} of product {pid}; "
                           f"only {remaining} remaining.",
                )
            new_received = item["quantity_received"] + want
            await database.execute(
                "UPDATE purchase_order_items SET quantity_received = :q "
                "WHERE id = :item_id",
                {"q": new_received, "item_id": item["id"]},
            )
            await increment_stock(pid, want)

        updated = await get_purchase_order(current_user.org_id, order_id)
        all_received = all(
            i["quantity_received"] >= i["quantity_ordered"] for i in updated["items"]
        )
        any_received = any(i["quantity_received"] > 0 for i in updated["items"])
        if all_received:
            new_status = "received"
        elif updated["status"] == "ordered" and any_received:
            new_status = "partially_received"
        else:
            new_status = updated["status"]
        received_at = datetime.now(timezone.utc) if all_received else None
        await set_po_status(order_id, new_status, received_at=received_at)

    row = await get_purchase_order(current_user.org_id, order_id)
    await log_activity(current_user.org_id, current_user.id, "received",
                       "purchase_order", order_id,
                       new_value={"items": len(receive_map)})
    return PurchaseOrderResponse.model_validate(row)


@router.post(
    "/purchase-orders/{order_id}/cancel",
    response_model=PurchaseOrderResponse,
    summary="Cancel Purchase Order",
)
async def cancel_po_endpoint(
    order_id: Annotated[int, Path(description="Purchase Order ID.")],
    current_user: Annotated[UserResponse, Depends(require_organization_member)],
) -> PurchaseOrderResponse:
    require_write_access(current_user, "purchase_orders")
    po = await get_purchase_order(current_user.org_id, order_id)
    if not po:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Purchase order not found.")
    if po["status"] in ("received", "cancelled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Cannot cancel an order in '{po['status']}' state.")
    await set_po_status(order_id, "cancelled")
    row = await get_purchase_order(current_user.org_id, order_id)
    await log_activity(current_user.org_id, current_user.id, "cancelled",
                       "purchase_order", order_id)
    return PurchaseOrderResponse.model_validate(row)
