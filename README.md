# ERP System — Backend

A modular, high-performance REST API built with **FastAPI**, **SQLAlchemy Core** (raw SQL via the `databases` library), **JWT** authentication, and a **Simplified Zero-DB RBAC Architecture**.

---

## Table of Contents

- [Architecture & Security (RBAC)](#architecture--security-rbac)
- [File Structure](#file-structure)
- [How to Run](#how-to-run)
- [API Documentation](#api-documentation)

---

## Architecture & Security (RBAC)

The system uses a **Single-Organization, 4-Level Role Hierarchy** designed for maximum performance, simplicity, and strict boundary enforcement.

### 1. Zero-DB RBAC Resolution
Unlike traditional RBAC systems that require complex joins across role, permission, and matrix tables on every HTTP request, this system uses **In-Memory Static Permission Maps** (`app/utils/roles.py`).
When a user authenticates, their access rights are calculated instantly from their fixed `role` and `department` fields, resulting in **zero database lookups** for permission verification.

### 2. Role Hierarchy & Table Access
The system enforces table-level access control across 4 distinct operational modules (**HR**, **Inventory**, **Sales**, and **Administration**):

| Role | Department Required? | Table / Module Access | Capabilities |
|---|---|---|---|
| **`owner`** | No | `ALL_TABLES` | Full unrestricted CRUD across all modules. Can add/remove org members and assign roles. |
| **`admin`** | No | `ALL_TABLES` | Full unrestricted CRUD across all modules. Can view all org members. |
| **`hr_manager`** | Yes (`hr`) | `HR_TABLES` + `ADMIN_TABLES` | Full CRUD on HR tables (`employees`, `attendance`, `payroll`, etc.) and user/audit viewing. |
| **`inventory_manager`** | Yes (`inventory`) | `INVENTORY_TABLES` + `ADMIN_TABLES` | Full CRUD on Inventory tables (`products`, `stock`, `purchase_orders`, etc.). |
| **`sales_manager`** | Yes (`sales`) | `SALES_TABLES` + `ADMIN_TABLES` | Full CRUD on Sales tables (`customers`, `sales_orders`, `returns`, etc.). |
| **`employee`** | Yes (`hr`, `inventory`, or `sales`) | Department Tables Only | Read-only access strictly scoped to their assigned department's tables. |

### 3. Organization & Member Management
- **Single Organization**: When an account is registered, `org_id` and `role` are initially `NULL`. When creating an organization (`POST /organization/`), the creator automatically becomes the **`owner`**.
- **Member Management**:
  - **Add/Remove Users**: The Owner can add existing users by ID (`POST /organization/members/{user_id}`) and remove them (`DELETE /organization/members/{user_id}`).
  - **Role Assignment**: The Owner assigns fixed roles and departments (`PUT /organization/members/{user_id}/role`).
  - **Department Scoping for Managers**: When Department Managers call `GET /organization/members`, the API automatically filters the results to return only members belonging to their department. Owners and Admins see all members.

---

## File Structure

```
Backend/
├── .gitignore
├── requirements.txt            # Python dependencies
│
└── app/
    ├── main.py                 # FastAPI app factory + lifespan (DB connect/disconnect)
    │
    ├── core/
    │   └── config.py           # Pydantic-settings: loads and validates all env vars
    │
    ├── db/
    │   ├── database.py         # Shared async `Database` instance (databases library)
    │   ├── metadata.py         # SQLAlchemy MetaData object shared across schemas
    │   └── init_db.py          # Creates all database tables on startup
    │
    ├── models/                 # Pydantic v2 request/response schemas
    │   ├── auth.py             # User, Token, and Login models
    │   ├── organization.py     # Organization & Member response schemas
    │   ├── roles.py            # Role assignment & permission response schemas
    │   ├── hr.py               # HR module schemas (Employees, Attendance, Payroll)
    │   ├── inventory.py        # Inventory module schemas (Products, Stock, Suppliers)
    │   └── sales.py            # Sales module schemas (Orders, Customers, Returns)
    │
    ├── schema/                 # SQLAlchemy Core Table definitions (raw database tables)
    │   ├── auth.py             # users, organizations, refresh_tokens
    │   ├── hr.py               # employees, attendance, leave_requests, payroll, departments
    │   ├── inventory.py        # products, inventory_stock, suppliers, purchase_orders
    │   ├── sales.py            # customers, sales_orders, sales_order_items, returns
    │   └── activity_logs.py    # audit trail table
    │
    ├── routers/                # FastAPI endpoint handlers
    │   ├── auth.py             # Authentication: /auth/register, /auth/login, /auth/refresh
    │   ├── user.py             # User profile: /users/me
    │   ├── organization.py     # Organization & member CRUD: /organization/*
    │   ├── rbac.py             # Permissions: /rbac/mypermissions
    │   ├── hr.py               # HR module endpoints: /hr/*
    │   ├── inventory.py        # Inventory module endpoints: /inventory/*
    │   ├── sales.py            # Sales module endpoints: /sales/*
    │   └── activity_logs.py    # Audit logs: /admin/activity-logs
    │
    └── utils/                  # Shared utilities & helpers
        ├── roles.py            # Static zero-DB permission maps & role enforcement helpers
        ├── security.py         # Password hashing (argon2) + JWT encode/decode
        ├── dependency.py       # FastAPI dependencies (get_current_user, require_table_access)
        ├── phone.py            # Phone number normalization & validation
        └── pagination.py       # Standardized query pagination helpers
```

### Key Design Decisions

| Layer | Technology | Role |
|---|---|---|
| **HTTP Framework** | FastAPI | Routing, dependency injection, automatic OpenAPI generation |
| **Async DB Driver** | `databases` + `aiosqlite` / `asyncpg` | Raw SQL queries with asynchronous execution (`await`) |
| **Table Definitions** | SQLAlchemy Core (`Table`, `Column`) | Lightweight schema definition — no heavy ORM sessions |
| **Validation** | Pydantic v2 | Strict request validation & response serialization |
| **Auth & Security** | JWT (PyJWT) + Argon2 | Stateless access tokens + hashed refresh tokens |
| **RBAC Resolution** | Static In-Memory Map | Zero-DB overhead table-level permission checking |
| **Config** | pydantic-settings | Type-safe environment variables loaded from `.env` |

---

## How to Run

### 1. Clone and enter the directory

```bash
git clone https://github.com/Ali-Adel-Zewailcity/ERP-System.git
cd Backend
```

### 2. Create and activate a virtual environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables in `.env` file
Create a `.env` file in the `Backend/` directory (refer to `.env.example` or defaults in `app/core/config.py`).

### 5. Initialize the database

```bash
python -m app.db.init_db
```
This creates all tables defined in `app/schema/` inside your configured database.

### 6. Start the development server

```bash
fastapi dev
```
The API will be available at **`http://127.0.0.1:8000`**.

---

## API Documentation

FastAPI generates interactive documentation automatically from your route definitions and Pydantic schemas.

### Swagger UI — `/docs`

> `http://127.0.0.1:8000/docs`

A full interactive UI where you can **read, test, and authenticate** against every endpoint directly in the browser.

- Click **Authorize** (top-right 🔒) and paste your JWT Bearer token to test protected routes.
- Each endpoint shows its expected request body, response schema, and possible status codes.

### ReDoc — `/redoc`

> `http://127.0.0.1:8000/redoc`

A clean, read-only reference format — ideal for sharing with frontend developers and stakeholders.

### OpenAPI JSON Schema — `/openapi.json`

> `http://127.0.0.1:8000/openapi.json`

The raw machine-readable OpenAPI 3.x specification. Use it to generate typed frontend or backend API clients:

```bash
# Download the schema
curl http://127.0.0.1:8000/openapi.json -o openapi.json

# Generate a typed TypeScript client (example with openapi-typescript)
npx openapi-typescript openapi.json -o src/api/schema.d.ts
```

### Health Check

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","app":"ERP System","version":"0.1.0","env":"development"}
```
