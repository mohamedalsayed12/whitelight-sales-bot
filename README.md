# White Light Sales Bot

Backend for the White Light Trading sales tool. White Light is a B2B wholesale company in Bahrain. Tally Prime stays the source of truth for stock and invoices. This app reads exports from Tally and keeps a record of what the sales team does.

The lead desk is at [http://127.0.0.1:8000/](http://127.0.0.1:8000/). A salesman sees his leads and a WhatsApp message. A manager or the CEO sees the week, assigns new leads, and can export a CSV. Sample businesses load once so the screens are not empty. They are fictional. The app does not search the web for leads.

## What works

- `GET /health` checks that the API and Postgres are up.
- `POST /auth/register` creates a **salesman**. The body has no role field, so nobody can sign up as an admin.
- `POST /auth/login` returns a JWT.
- `GET /auth/me` returns the logged-in user.
- `POST /users` creates an admin, a manager, or a salesman. **Admin only.**
- On startup, if `ADMIN_EMAIL` and `ADMIN_PASSWORD` are set and that email does not exist, the app creates one admin. If the email already exists, the password and role are left alone. `ADMIN_EMAIL` has to be a normal email address, such as `ceo@example.com`. Names like `.local` are rejected.
- `POST /imports/stock` reads a stock CSV and sets `stock_on_hand`. A manager or admin can call it.
- `POST /imports/receivables` reads an outstanding-invoices CSV and creates or updates invoices. A manager or admin can call it.
- `GET /stock?q=lamp` finds active products by sku or name. Any logged-in user can call it. Each row shows the available quantity and whether it is low stock.
- `GET /clients/{id}/account` shows what the client owes, split into overdue buckets, plus pending cheques and a status of `ok`, `warning`, or `on_hold`. A salesman only sees clients assigned to them.
- `PUT /price-lists/{hotel|restaurant}/items` sets a product price. A manager or admin can call it.
- `PATCH /clients/{id}` sets the client's price list or credit limit. A manager or admin can call it.
- `POST /orders` lets a salesman submit an order for an assigned client. Prices are copied from that client's price list. If any line needs more than the available stock, the order is rejected. If the client is on hold, the order is still saved and the response warns that a manager must approve it.
- `POST /orders/{id}/status` lets a manager or admin approve the order, send it out for delivery, mark it delivered, or cancel it. Each change is stored with who did it and when.
- `POST /quotes` lets a salesman build a quote for an assigned client. Prices are copied from that client's price list. A product that is not on the list is rejected. A quote does not reserve stock.
- `GET /quotes/{id}/pdf` returns a one-page PDF the salesman can send on WhatsApp.
- `POST /cheques` lets a salesman log a cheque collected from an assigned client. It starts as `received`.
- `POST /cheques/{id}/status` lets a manager or admin mark it `deposited`, then `cleared` or `bounced`.
- `GET /cheques/due` lists received and deposited cheques due today through seven days ahead. `GET /cheques/bounced` lists bounced cheques. A salesman only sees clients assigned to them.
- `GET /reorder` lists active products whose available quantity is at or below the reorder level, including how many are on open orders. A manager or admin can call it.
- `GET /summary` is the CEO's daily summary: today's orders, cheques collected today, total overdue, and the reorder list. **Admin only.**

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

Then open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) for the lead screens. The API docs stay at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Sample salesman: `ahmed@example.com` / `password123`. The CEO signs in with `ADMIN_EMAIL` and `ADMIN_PASSWORD` from `.env` and sees the weekly overview. Yusuf and Ravi use the same sample password.

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
| GET | `/stock?q=` | logged-in user | 200 |
| GET | `/clients/{id}/account` | assigned salesman, manager, or admin | 200 |
| PATCH | `/clients/{id}` | manager or admin | 200 |
| PUT | `/price-lists/{name}/items` | manager or admin | 200 |
| POST | `/orders` | salesman | 201 |
| GET | `/orders` | own orders, or all for manager and admin | 200 |
| GET | `/orders/{id}` | owning salesman, manager, or admin | 200 |
| POST | `/orders/{id}/status` | manager or admin | 200 |
| POST | `/quotes` | salesman | 201 |
| GET | `/quotes` | own quotes, or all for manager and admin | 200 |
| GET | `/quotes/{id}` | owning salesman, manager, or admin | 200 |
| GET | `/quotes/{id}/pdf` | owning salesman, manager, or admin | 200 PDF |
| POST | `/cheques` | salesman | 201 |
| POST | `/cheques/{id}/status` | manager or admin | 200 |
| GET | `/cheques/due` | own clients, or all for manager and admin | 200 |
| GET | `/cheques/bounced` | own clients, or all for manager and admin | 200 |
| GET | `/reorder` | manager or admin | 200 |
| GET | `/summary` | admin | 200 |

Status codes used here: **401** not logged in, **403** not allowed, **404** not found, **409** conflict (duplicate email, not enough stock, or a status change that is not allowed), **422** invalid input. A failed login is always `Incorrect email or password`, whether the email exists or not.

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
- Timestamps are timezone-aware UTC in the database. The business timezone is Asia/Bahrain. Order history returns `changed_at` in UTC. Overdue days use today's date in Asia/Bahrain.
- Money and stock quantities are `Numeric(12, 3)`. The Bahraini dinar has 3 decimal places, and Tally quantities can be fractional. Do not use floats.
- A stock import sets `stock_on_hand` to the quantity in the file. It does not add to the old quantity, and products missing from the file are left as they are. Category, unit, reorder level, and active are not in the export, so a re-import does not wipe them. A new product starts as category blank, unit `pcs`, reorder level 0, and active.
- An invoice is identified by its number. Importing the same file again updates that invoice. A client is matched by name, ignoring case. A name the app has not seen becomes a client of type `other`, with no price list and a credit limit of 0.
- Invoice dates are calendar dates (`YYYY-MM-DD`), not UTC timestamps. User `created_at` is still stored in UTC.
- Available stock is `stock_on_hand` minus quantities on orders that are submitted, approved, or out for delivery. Low stock means that available quantity is at or below `reorder_level`. Inactive products are left out of search. Marking an order delivered reduces `stock_on_hand` by the same amount, so the goods do not become available again. Cancelling an order releases the reservation. The next Tally stock import still replaces `stock_on_hand`.
- An order stores the unit price from the client's price list at that moment. A later price change does not rewrite the order. There is no driver user: "out for delivery" is a status, not an assignment to a person.
- A manager moves an order one step at a time: submitted, approved, out for delivery, delivered. Cancel is allowed until it is delivered. A salesman cannot change the status.
- A quote stores the same unit price as an order, plus a `valid_until` date. That date cannot be before today in Asia/Bahrain. The PDF is one page of Latin-1 text, so a character outside that set is written as `?`. The next Tally import does not change a saved quote.
- A cheque starts as `received`. A manager can mark it `deposited`, and from there `cleared` or `bounced`. It can also bounce straight from `received`. Cleared and bounced do not change again. Due cheques are those still pending with a due date from today through seven days ahead, using Asia/Bahrain. "Today" for orders and cheques collected is that same business date, including the hours after midnight even when UTC is still the day before.
- The daily summary does not include cancelled orders. Cheques collected are every cheque logged that day, including ones that later bounce. Total overdue is unpaid money due today or earlier, for every client. Cash is not tracked separately. The reorder list uses available stock, so goods already on an open order can push a product onto the list. A product with stock 0 and reorder level 0 is on the list, because it is at its reorder level. Inactive products are left out.
- Account status: `on_hold` if the outstanding total is over the credit limit, or any money is more than 90 days past due. `warning` if something is overdue but the client is not on hold. Matching the credit limit exactly is still `ok`. A client created from a Tally import has a credit limit of 0, so any unpaid invoice puts them on hold until a manager raises the limit.
- Pending cheques are those marked received or deposited. Cleared and bounced cheques are not pending. Money that is not due yet is outstanding, but it is not in an overdue bucket. Due today counts as 0 days late (the 0-30 bucket). 90 days late is still a warning. 91 days is on hold.
- The `users.role` column is text with a check constraint, not a Postgres enum, so adding a role later is a normal migration.

## Layout

```
app/
  main.py            FastAPI app and startup
  config.py          settings from .env
  database.py        engine and session
  models.py          users, products, clients, invoices, orders, quotes
  schemas.py         request and response models
  routers/           HTTP only
  services/          passwords, imports, stock, accounts, orders, quotes, cheques
alembic/             migrations
tests/
docker-compose.yml
.env.example
```
