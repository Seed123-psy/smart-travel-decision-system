# Repository Guidelines

## Project Structure & Module Organization

`frontend/src/` contains Vue views, components, composables, API clients, types, and styles. `backend/app/` separates HTTP routes, configuration, schemas, ORM models, Agents, providers, and services. Planning uses HelloAgents roles, DeepSeek, and Amap; services own orchestration, validation, and persistence.

Tests live in `backend/tests/` and `frontend/tests/`. `backend/migrations/` owns Alembic revisions. Root planning documents define scope; `development-baseline.md` records decisions and `README.md` records setup and verification. Preserve the original teaching Word document.

## Approved Development Baseline

Use Vue 3, TypeScript, Vite, FastAPI, MySQL, and HelloAgents. Target one local operator, one mainland China destination, 1–7 days, and 1–10 travelers. MySQL 8.4 is the design target; initial migrations support 8.0.16+. Deterministic validators are not Agents. Keep model calls cancellable within the shared 60-second task deadline.

## Build, Test, and Development Commands

From `backend/`, with its virtual environment active:

- `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`: start the API.
- `python -m pytest`: run contract and API tests.
- `python -m app.scripts.check_providers`: inspect configuration; `--live` makes real calls.
- `python -m alembic upgrade head --sql`: inspect migration SQL without connecting.
- `python -m alembic upgrade head`: apply reviewed migrations to the configured database.

From `frontend/`, run `npm ci`, `npm run dev`, `npm run typecheck`, `npm test`, and `npm run build`. Dependency upgrades update `package.json` and `package-lock.json` together. Read README for verification limits.

## Coding Style & Naming Conventions

Follow `.editorconfig`: four spaces for Python, two for frontend code, UTF-8, and LF. Use Python `snake_case`, Vue component `PascalCase`, and TypeScript `camelCase`. No enforced formatter is installed. Keep calculations outside Agent prompts and HTTP handlers.

Preserve Chinese documentation, feature IDs F001–F013, and WHEN/THEN criteria. Update affected contracts and documentation together.

## Testing & Review Guidelines

Use pytest (`test_*.py`) for backend behavior and Node's test runner (`*.test.mjs`) for initial frontend clients. Cover invalid dates, money precision, confirmation, unavailable dependencies, and safe errors. No coverage threshold is configured. Fixtures must declare sources and reference time; they cannot prove live API accuracy. Render and inspect edited Word documents.

## Configuration, Commits & Pull Requests

Keep credentials in ignored `.env` files. Use the dedicated database and reviewed migrations, never startup `create_all()`. P0 budget is group-total CNY destination spending, excluding intercity transport; precision belongs to P1.

No Git history is available. Use imperative commits, such as `feat: validate travel dates`. PRs should explain rationale, affected features, checks performed, and interface changes with screenshots.
