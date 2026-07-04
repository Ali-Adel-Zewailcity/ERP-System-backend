# ERP System — Backend

A modular, async-first REST API built with **FastAPI**, **SQLAlchemy Core** (raw SQL via the `databases` library), and **JWT** authentication.

---

## Table of Contents

- [File Structure](#file-structure)
- [How to Run](#how-to-run)
- [API Documentation](#api-documentation)

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
    │   ├── metadata.py         # SQLAlchemy MetaData object shared across models
    │   └── init_db.py          # Creates all tables on first run (SQLAlchemy Core)
    │
    ├── models/
    │   └── auth.py             # SQLAlchemy Core Table definitions (users, tokens, …)
    │
    ├── schema/
    │   ├── auth.py             # Pydantic request/response models for auth endpoints
    │   ├── hr.py               # Pydantic schemas for HR module
    │   ├── inventory.py        # Pydantic schemas for Inventory module
    │   └── sales.py            # Pydantic schemas for Sales module
    │
    ├── routers/
    │   ├── auth.py             # Endpoints: /auth/register, /auth/login, /auth/refresh …
    │   └── user.py             # Endpoints: /users/me
    │
    └── utils/
        ├── security.py         # Password hashing (argon2) + JWT encode/decode
        ├── dependency.py       # FastAPI dependencies (get_current_user, …)
        └── user.py             # Shared user-lookup helpers
```

### Key Design Decisions

| Layer | Technology | Role |
|---|---|---|
| HTTP framework | FastAPI | Routing, dependency injection, OpenAPI generation |
| Async DB driver | `databases` + `aiosqlite` / `asyncpg` | Raw SQL queries with `await` |
| Table definitions | SQLAlchemy Core (`Table`, `Column`) | Schema only — no ORM sessions |
| Validation | Pydantic v2 | Request bodies & response serialization |
| Auth | JWT (PyJWT) + argon2 | Stateless access + refresh tokens |
| Config | pydantic-settings | Typed env vars loaded from `.env` |


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

### 5. Initialize the database

```bash
python -m app.db.init_db
```

This creates all tables defined in `app/models/` inside your configured database.

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

- Click **Authorize** (top-right 🔒) and paste a JWT Bearer token to test protected routes.
- Each endpoint shows its expected request body, response schema, and possible status codes.

### ReDoc — `/redoc`

> `http://127.0.0.1:8000/redoc`

A clean, read-only reference format — better for sharing with frontend developers or stakeholders.

### OpenAPI JSON Schema — `/openapi.json`

> `http://127.0.0.1:8000/openapi.json`

The raw machine-readable OpenAPI 3.x specification. Use it to:

```bash
# Download the schema
curl http://127.0.0.1:8000/openapi.json -o openapi.json

# Generate a typed client (example with openapi-typescript)
npx openapi-typescript openapi.json -o src/api/schema.d.ts

# Generate a Python client
pip install openapi-python-client
openapi-python-client generate --url http://127.0.0.1:8000/openapi.json
```

### Health Check

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","app":"ERP System","version":"0.1.0","env":"development"}
```
