# White Light Sales Bot

Backend for the White Light Trading sales tool. White Light is a B2B wholesale company in Bahrain. Tally Prime stays the source of truth for stock and invoices. This app reads exports from Tally and keeps a record of what the sales team does.

Phase 2 adds Tally imports. Orders, quotes, and cheques are not built yet.

## What works

- `GET /health` checks that the API and Postgres are up.
- `POST /auth/register` creates a **salesman**. The body has no role field, so nobody can sign up as an admin.
- `POST /auth/login` returns a JWT.
- `GET /auth/me` returns the logged-in user.
- `POST /users` creates an admin, a manager, or a salesman. **Admin only.**
- On startup, if `ADMIN_EMAIL` and `ADMIN_PASSWORD` are set and that email does not exist, the app creates one admin. If the email already exists, the password and role are left alone. `ADMIN_EMAIL` has to be a normal email address, such as `ceo@example.com`. Names like `.local` are rejected.
- `POST /imports/stock` reads a stock CSV and sets `stock_on_hand`. A manager or admin can call it.
- `POST /imports/receivables` reads an outstanding-invoices CSV and creates or updates invoices. A manager or admin can call it.

Roles are `admin` (CEO), `manager` (operations manager), and `salesman`.

## Run it locally

You need Python 3.12 and Docker.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
docker compose up -d
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m uvicorn app.main:app --reload
```

Then open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

1. Call `POST /auth/login` with `ADMIN_EMAIL` and `ADMIN_PASSWORD` from `.env`.
2. Click **Authorize** and paste the `access_token` only, without the word `Bearer`.
3. Call `POST /users` to add a manager or another admin.

Change `JWT_SECRET` and `ADMIN_PASSWORD` before using this anywhere except your own machine. `JWT_SECRET` should be at least 32 characters. `.env` is gitignored. The Postgres password in `docker-compose.yml` is for local Docker only.

The first `docker compose up` creates two databases: `whitelight` for the app and `whitelight_test` for pytest. Init scripts run only when the volume is new. If the test database is missing, reset the local volume:

```powershell
docker compose down -v
docker compose up -d
```

## Run the tests

Postgres must be up (`docker compose up -d`). From the project root:

```powershell
.venv\Scripts\python -m pytest -v
```

Pytest applies the Alembic migrations to `TEST_DATABASE_URL`. It refuses to run if that database name does not end with `_test`.

GitHub Actions runs the same tests against Postgres 16 on every push and pull request.

## API

| Method | Path | Who | Success |
| --- | --- | --- | --- |
| GET | `/health` | anyone | 200 |
| POST | `/auth/register` | anyone | 201 salesman |
| POST | `/auth/login` | anyone | 200 token |
| GET | `/auth/me` | logged-in user | 200 |
| POST | `/users` | admin | 201 |
| POST | `/imports/stock` | manager or admin | 200 |
| POST | `/imports/receivables` | manager or admin | 200 |

Status codes used here: **401** not logged in, **403** not allowed, **409** email already registered, **422** invalid input. A failed login is always `Incorrect email or password`, whether the email exists or not.

A Tally import with a readable CSV returns **200** even when some rows are bad. The body lists those rows. A file that is not UTF-8, or that is missing a required column, is **422** and nothing is saved.

Stock CSV:

```csv
sku,name,quantity
WL-100,Floor lamp,12
WL-200,Bath towel,40.500
```

Receivables CSV:

```csv
client,invoice_number,issue_date,due_date,amount,amount_paid
Gulf Hotel,INV-1001,2026-09-01,2026-10-01,150.500,50.000
```

Header names ignore case and spaces, so `Amount Paid` is the same as `amount_paid`. Send the file as form field `file`. Sample files with fake data are in `tests/fixtures/`.

Register:

```json
{
  "email": "ada@example.com",
  "password": "password123",
  "full_name": "Ada Yusuf"
}
```

Admin creates a manager:

```json
{
  "email": "noor@example.com",
  "password": "password123",
  "full_name": "Noor Ali",
  "role": "manager"
}
```

## Decisions

- Python code lives in `app/` so imports are `app.models`, `app.routers`, and `app.services`. Routers stay thin. Passwords, tokens, and creating users are in `services/`.
- Passwords are hashed with the `bcrypt` library. A password must be at least 8 characters and at most 72 bytes, because bcrypt ignores anything past 72 bytes.
- Login tokens last `JWT_EXPIRE_MINUTES` (8 hours by default). There is no refresh token.
- Emails are stored in lowercase, so `Ada@Example.com` and `ada@example.com` are the same user.
- Timestamps are timezone-aware UTC in the database. The business timezone is Asia/Bahrain. This phase only returns `created_at`; it does not convert it for display.
- Money and stock quantities are `Numeric(12, 3)`. The Bahraini dinar has 3 decimal places, and Tally quantities can be fractional. Do not use floats.
- A stock import sets `stock_on_hand` to the quantity in the file. It does not add to the old quantity, and products missing from the file are left as they are. Category, unit, reorder level, and active are not in the export, so a re-import does not wipe them. A new product starts as category blank, unit `pcs`, reorder level 0, and active.
- An invoice is identified by its number. Importing the same file again updates that invoice. A client is matched by name, ignoring case. A name the app has not seen becomes a client of type `other`, with no price list and a credit limit of 0.
- Invoice dates are calendar dates (`YYYY-MM-DD`), not UTC timestamps. User `created_at` is still stored in UTC. The business timezone is Asia/Bahrain.
- The `users.role` column is text with a check constraint, not a Postgres enum, so adding a role later is a normal migration.

## Layout

```
app/
  main.py            FastAPI app and startup
  config.py          settings from .env
  database.py        engine and session
  models.py          User
  schemas.py         request and response models
  routers/           HTTP only
  services/          passwords, tokens, creating users
alembic/             migrations
tests/
docker-compose.yml
.env.example
```
