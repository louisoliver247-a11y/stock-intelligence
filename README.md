# Stock Intelligence

Indian-equity market-data foundation for an explainable research platform.
**Scope: Milestones 0 and 1 foundation plus Milestone 2 offline indicators.**
No trading signals, forecasts or broker order placement are implemented.
See [offline indicator usage and conventions](docs/ANALYSIS_ENGINE.md).

## User accounts

Sign in with email and password. Administrators can create and delete accounts
from the Users page. See [user setup and permissions](docs/USERS.md).

## This Windows workspace

Double-click `Start Local App.cmd`, open http://localhost:8080, and paste the
operator key copied to your clipboard. Use `Stop Local App.cmd` to stop it.
See [local server setup and Upstox connection](docs/LOCAL_SERVER.md).

## Run with Docker

Requirements: Docker Engine with Compose, an Upstox developer app for authenticated
data, and a verified exchange-session calendar.

```sh
cp .env.example .env
# Fill passwords, DATABASE_URL, REDIS_URL and a random 32+ character ADMIN_API_KEY.
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Put the generated key in TOKEN_ENCRYPTION_KEY. Keep it outside source control.
docker compose up --build -d
```

Open <http://localhost:8080>. Enter the backend operator key; it is stored only in
browser memory. When running FastAPI directly, API documentation is at
<http://localhost:8000/docs>. Nginx only proxies `/api/`, so deployment documentation
is intentionally not exposed through the frontend service.

1. In Settings, connect Upstox using OAuth or configure the backend-only manual
   token environment variable. Register the exact redirect URI with Upstox.
2. Synchronize the instrument master; inspect the job result.
3. Import explicitly verified NSE sessions and holidays using Settings or
   `POST /api/calendar/sessions`. Do not use a weekday-only calendar as validation.
4. Select an instrument/date range and queue historical ingestion. Load the chart
   after the job succeeds. Query `/api/data-quality` for issues.
5. Set `FEED_INSTRUMENT_IDS` to a JSON list of synchronized canonical IDs, then
   run `docker compose --profile live up -d feed` to opt into the feed worker.
6. Compare provider history and live behavior before enabling any later analysis.

Session example (illustrative, not an authoritative calendar):

```json
[{"exchange":"NSE","session_date":"2025-01-02",
  "opens_at":"2025-01-02T09:15:00+05:30","closes_at":"2025-01-02T15:30:00+05:30",
  "source":"replace with verified exchange calendar reference"}]
```

## Local development

```sh
python -m venv .venv
# Activate your virtual environment.
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
python -m alembic upgrade head
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --no-access-log
# Separate terminal:
python -m market_data.worker
# Frontend:
cd frontend
npm ci
npm run dev
```

Local DATABASE_URL and REDIS_URL must point to reachable services instead of
Compose hostnames. `WEB_ORIGIN` must match Vite's origin for OAuth redirects.
On Windows with restrictive script policy, invoke `npm.cmd`.

## Validation

```sh
python -m pytest -q
python -m ruff check .
python -m alembic upgrade head --sql
cd frontend
npm test
npm run build
```

The PostgreSQL integration test requires `TEST_DATABASE_URL` set to a migrated,
disposable database. Never point integration tests at production data. Tests use
synthetic/mock inputs; passing them does not certify live market-data integrity.

See [architecture](docs/ARCHITECTURE.md), [implementation plan](docs/IMPLEMENTATION_PLAN.md),
[market data](docs/MARKET_DATA.md), [deployment](docs/DEPLOYMENT.md), and
[milestone report](docs/MILESTONE_REPORT.md).
