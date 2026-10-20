# White Light Sales Bot

Backend for the White Light Trading sales tool. White Light is a B2B wholesale company in Bahrain. Tally Prime stays the source of truth for stock and invoices. This app reads exports from Tally and keeps a record of what the sales team does.

Phase 1 is project setup and accounts. Stock, invoices, orders, quotes, and cheques are not built yet.

## What works

- `GET /health` checks that the API and Postgres are up.
- `POST /auth/register` creates a **salesman**. The body has no role field, so nobody can sign up as an admin.
- `POST /auth/login` returns a JWT.
- `GET /auth/me` returns the logged-in user.
- `POST /users` creates an admin, a manager, or a salesman. **Admin only.**
- On startup, if `ADMIN_EMAIL` and `ADMIN_PASSWORD` are set and that email does not exist, the app creates one admin. If the email already exists, the password and role are left alone. `ADMIN_EMAIL` has to be a normal email address, such as `ceo@example.com`. Names like `.local` are rejected.

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

Status codes used here: **401** not logged in, **403** not allowed, **409** email already registered, **422** invalid input. A failed login is always `Incorrect email or password`, whether the email exists or not.

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
- Money is not stored yet. Later phases will use `Numeric(12, 3)` because the Bahraini dinar has 3 decimal places. Do not use floats for money.
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
