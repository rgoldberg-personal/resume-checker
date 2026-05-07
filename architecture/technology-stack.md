# Technology Stack: Job Fit & Salary Estimator

**Version:** 1.0
**Date:** 2026-05-05
**Status:** Implementation-Ready
**Source document:** `./architecture/architecture.md`

---

## Table of Contents

1. [Overview](#1-overview)
2. [Package Management](#2-package-management)
3. [Backend Dependencies](#3-backend-dependencies)
4. [Frontend Dependencies](#4-frontend-dependencies)
5. [MCP Server Dependencies](#5-mcp-server-dependencies)
6. [Infrastructure](#6-infrastructure)
7. [Development Tools](#7-development-tools)
8. [Project Structure](#8-project-structure)
9. [Docker Compose Setup](#9-docker-compose-setup)
10. [Environment Variable Reference](#10-environment-variable-reference)
11. [Startup Validation](#11-startup-validation)
12. [Version Pinning Strategy](#12-version-pinning-strategy)

---

## 1. Overview

The system consists of three deployable units:

| Unit | Runtime | Entry Point |
|------|---------|-------------|
| FastAPI backend + Celery worker | Python 3.12 | `uvicorn app.main:app` / `celery -A app.celery_app worker` |
| React frontend | Node 20 (build only; served as static files or Vite dev server) | `vite dev` / `vite build` |
| Platy MCP server | Python 3.12 | `python platy_mcp/server.py` (started as subprocess by Celery worker) |

In development, all three are orchestrated by Docker Compose. The MCP server is not a separate Docker service — it is launched as a subprocess by the Celery worker process.

---

## 2. Package Management

### Python — uv

**Tool:** `uv` (Astral)
**Why:** Significantly faster than pip or poetry for dependency resolution and installation. Replaces `pip`, `pip-tools`, and `virtualenv` in a single binary. Compatible with `pyproject.toml` (PEP 621). No lock file format change headaches.

```bash
# Install uv (once, globally)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtualenv and install all dependencies
uv sync

# Add a new dependency
uv add fastapi

# Add a dev-only dependency
uv add --dev pytest

# Run a command inside the venv
uv run uvicorn app.main:app --reload
```

**Lock file:** `uv.lock` (committed to source control).
**Config:** `pyproject.toml` in the project root (one file for the entire Python project, including backend and MCP server).

### Node — pnpm

**Tool:** `pnpm` v9+
**Why:** Faster installs than npm, stricter dependency isolation than npm, smaller `node_modules` via content-addressable storage. Well-suited for the small frontend package count here.

```bash
# Install pnpm (once, globally)
npm install -g pnpm

# Install all frontend dependencies
cd frontend && pnpm install

# Add a dependency
pnpm add @tanstack/react-query

# Add a dev dependency
pnpm add -D vitest
```

**Lock file:** `frontend/pnpm-lock.yaml` (committed to source control).

---

## 3. Backend Dependencies

All backend Python packages are declared in `pyproject.toml` under `[project.dependencies]`.

### 3.1 Runtime Dependencies

| Package | Version Constraint | Purpose | Rationale |
|---------|-------------------|---------|-----------|
| `fastapi` | `>=0.111,<1.0` | HTTP API framework | Async-native; Pydantic v2 integration; auto-generates OpenAPI docs |
| `uvicorn[standard]` | `>=0.29,<1.0` | ASGI server | FastAPI's recommended server; `[standard]` adds `uvloop` and `websockets` |
| `pydantic` | `>=2.7,<3.0` | Data validation & serialization | FastAPI default; strict typing for all pipeline models |
| `pydantic-settings` | `>=2.3,<3.0` | Environment variable loading | Type-safe `.env` / environment config; integrates with Pydantic v2 |
| `celery[redis]` | `>=5.4,<6.0` | Task queue / pipeline orchestration | Battle-tested async task execution; `[redis]` includes `redis-py` |
| `redis` | `>=5.0,<6.0` | Redis client | Used directly for job state reads/writes outside of Celery machinery |
| `httpx` | `>=0.27,<1.0` | Async HTTP client | OpenRouter API calls; `asyncio`-compatible; better than `aiohttp` for this use case |
| `pdfplumber` | `>=0.10,<1.0` | PDF text extraction | Handles multi-column layouts and complex PDFs better than `PyPDF2` |
| `python-docx` | `>=1.1,<2.0` | DOCX text extraction | Standard library for `.docx`; actively maintained |
| `python-magic` | `>=0.4,<1.0` | MIME type validation | Validates file type from magic bytes, independent of file extension |
| `pyyaml` | `>=6.0,<7.0` | YAML config parsing | Loads `scoring_weights.yaml`, `salary_bands.yaml`, `role_mappings.yaml` |
| `python-dotenv` | `>=1.0,<2.0` | `.env` file loading | Loads `.env` into environment variables for local development |
| `structlog` | `>=24.0,<25.0` | Structured JSON logging | Context-rich logs per job_id and step; JSON output for log aggregation |
| `aiofiles` | `>=23.0,<25.0` | Async file I/O | Non-blocking file write for uploaded CV files |
| `mcp` | `>=1.0,<2.0` | MCP client/server SDK | Both the Celery worker (client) and Platy MCP server use this SDK |
| `python-multipart` | `>=0.0.9,<1.0` | Multipart form data parsing | Required by FastAPI for `UploadFile` / `Form` support |

### 3.2 Optional Runtime Dependencies

| Package | Version Constraint | Purpose | When Needed |
|---------|-------------------|---------|-------------|
| `flower` | `>=2.0,<3.0` | Celery task monitoring web UI | Development; `uv add --optional flower` |

### 3.3 Development / Test Dependencies

| Package | Version Constraint | Purpose |
|---------|-------------------|---------|
| `pytest` | `>=8.0,<9.0` | Test runner |
| `pytest-asyncio` | `>=0.23,<1.0` | Async test support (`async def test_...`) |
| `pytest-httpx` | `>=0.30,<1.0` | Mock `httpx` HTTP calls in tests (OpenRouter) |
| `ruff` | `>=0.4,<1.0` | Linter + formatter (replaces flake8, black, isort) |
| `mypy` | `>=1.10,<2.0` | Static type checker |
| `celery[pytest]` | — | Celery test fixtures (eager task execution) |

### 3.4 `pyproject.toml` Template

```toml
[project]
name = "cv-analyzer"
version = "1.0.0"
description = "Job Fit & Salary Estimator — CV analysis pipeline"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.111,<1.0",
    "uvicorn[standard]>=0.29,<1.0",
    "pydantic>=2.7,<3.0",
    "pydantic-settings>=2.3,<3.0",
    "celery[redis]>=5.4,<6.0",
    "redis>=5.0,<6.0",
    "httpx>=0.27,<1.0",
    "pdfplumber>=0.10,<1.0",
    "python-docx>=1.1,<2.0",
    "python-magic>=0.4,<1.0",
    "pyyaml>=6.0,<7.0",
    "python-dotenv>=1.0,<2.0",
    "structlog>=24.0,<25.0",
    "aiofiles>=23.0,<25.0",
    "mcp>=1.0,<2.0",
    "python-multipart>=0.0.9,<1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0,<9.0",
    "pytest-asyncio>=0.23,<1.0",
    "pytest-httpx>=0.30,<1.0",
    "ruff>=0.4,<1.0",
    "mypy>=1.10,<2.0",
    "celery[pytest]>=5.4,<6.0",
    "flower>=2.0,<3.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### 3.5 System-Level Dependency

`python-magic` requires `libmagic` to be installed at the OS level:

```bash
# macOS
brew install libmagic

# Debian/Ubuntu
apt-get install libmagic1

# Alpine (Docker)
apk add --no-cache libmagic
```

If `libmagic` is unavailable, fall back to extension-only validation and log a warning at startup. Document this in the README.

---

## 4. Frontend Dependencies

All frontend packages are declared in `frontend/package.json`.

### 4.1 Runtime Dependencies

| Package | Version Constraint | Purpose | Rationale |
|---------|-------------------|---------|-----------|
| `react` | `^18.3` | UI framework | Project constraint |
| `react-dom` | `^18.3` | React DOM renderer | Required alongside `react` |
| `@tanstack/react-query` | `^5.40` | API state management + polling | Elegant handling of loading/error states; built-in `refetchInterval` for polling |
| `react-dropzone` | `^14.2` | File upload drag-and-drop UX | Accessibility-friendly; handles file validation callbacks |
| `recharts` | `^2.12` | Score gauge / chart visualization | Declarative React charts; `RadialBarChart` for score gauge |

### 4.2 Development Dependencies

| Package | Version Constraint | Purpose |
|---------|-------------------|---------|
| `typescript` | `^5.4` | Type checking |
| `vite` | `^5.3` | Build tool / dev server |
| `@vitejs/plugin-react` | `^4.3` | Vite React plugin (Fast Refresh) |
| `tailwindcss` | `^3.4` | Utility-first CSS |
| `postcss` | `^8.4` | PostCSS (required by Tailwind) |
| `autoprefixer` | `^10.4` | CSS vendor prefixing (required by Tailwind) |
| `@types/react` | `^18.3` | TypeScript types for React |
| `@types/react-dom` | `^18.3` | TypeScript types for React DOM |
| `eslint` | `^9.0` | JavaScript / TypeScript linter |
| `@eslint/js` | `^9.0` | ESLint JS config |
| `typescript-eslint` | `^7.0` | TypeScript ESLint rules |
| `vitest` | `^1.6` | Unit test runner (Vite-native) |
| `@testing-library/react` | `^16.0` | React component testing |
| `@testing-library/user-event` | `^14.5` | User interaction simulation |

### 4.3 `package.json` Template

```json
{
  "name": "cv-analyzer-frontend",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "lint": "eslint src",
    "test": "vitest"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "@tanstack/react-query": "^5.40.0",
    "react-dropzone": "^14.2.3",
    "recharts": "^2.12.7"
  },
  "devDependencies": {
    "typescript": "^5.4.5",
    "vite": "^5.3.4",
    "@vitejs/plugin-react": "^4.3.1",
    "tailwindcss": "^3.4.4",
    "postcss": "^8.4.38",
    "autoprefixer": "^10.4.19",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "eslint": "^9.5.0",
    "@eslint/js": "^9.5.0",
    "typescript-eslint": "^7.13.1",
    "vitest": "^1.6.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.2"
  }
}
```

### 4.4 `vite.config.ts`

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Proxy /api requests to FastAPI during development
      // Only needed if running without Docker Compose
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
});
```

### 4.5 `tailwind.config.ts`

```typescript
import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {},
  },
  plugins: [],
} satisfies Config;
```

---

## 5. MCP Server Dependencies

The Platy MCP server shares the same Python virtualenv as the backend (declared in the same `pyproject.toml`). It requires only a subset of the backend dependencies.

### Minimal dependencies for MCP server

| Package | Version Constraint | Purpose |
|---------|-------------------|---------|
| `mcp` | `>=1.0,<2.0` | MCP server SDK; `FastMCP` abstraction |
| `pyyaml` | `>=6.0,<7.0` | Load salary data (if YAML format is used) |

The `mcp` package installs `FastMCP` as part of its SDK. The server entry point is:

```python
# platy_mcp/server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("platy-salary-mcp")

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

**Transport:** `stdio` — the MCP server communicates over stdin/stdout. It is launched as a subprocess by the Celery worker. No separate HTTP port is exposed.

---

## 6. Infrastructure

### Redis

| Attribute | Value |
|-----------|-------|
| Version | 7.x (latest stable) |
| Role | Celery message broker + result backend + job state store |
| Image (Docker) | `redis:7-alpine` |
| Default port | 6379 |
| Persistence | None for MVP (RDB/AOF disabled); job state is ephemeral |
| Connection URL | `redis://localhost:6379/0` (configurable via `REDIS_URL` env var) |

Redis serves three purposes:
1. **Celery broker:** task messages published to Redis queues
2. **Celery result backend:** task results stored in Redis (keyed by `task_id`)
3. **Job state store:** `HSET job:{job_id} status SCORING progress_step "..."` — written by each task for the polling API

### Python Runtime

| Attribute | Value |
|-----------|-------|
| Version | 3.12 (minimum; not 3.10 or 3.11) |
| Why 3.12 | Latest stable at time of writing; `ExceptionGroup`, improved typing, performance improvements |
| Docker base image | `python:3.12-slim-bookworm` |

### Node Runtime (build only)

| Attribute | Value |
|-----------|-------|
| Version | 20 LTS |
| Used for | Building the React frontend; not part of the runtime |
| Docker base image | `node:20-alpine` (multi-stage build target) |

---

## 7. Development Tools

### Python Linting & Formatting — ruff

**Tool:** `ruff` (replaces flake8 + black + isort in a single tool)

```bash
# Check for linting errors
uv run ruff check .

# Auto-fix safe issues
uv run ruff check --fix .

# Format code (replaces black)
uv run ruff format .
```

Config in `pyproject.toml` (see §3.4).

### Python Type Checking — mypy

```bash
uv run mypy app/ platy_mcp/
```

Run in `--strict` mode. Pydantic plugin enabled for model type inference.

### Python Testing — pytest

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=app --cov-report=term-missing

# Run a specific test file
uv run pytest tests/test_scoring.py -v
```

**Test configuration:**

```
tests/
├── unit/
│   ├── test_scoring.py          # ScoreBreakdown calculation
│   ├── test_salary_estimation.py # fallback bands, sanity check
│   ├── test_pii_stripping.py    # strip_pii_from_text
│   ├── test_role_mapping.py     # classify_role_category
│   └── test_assembler.py        # confidence calculation
├── integration/
│   ├── test_analyze_endpoint.py # POST /analyze with mock Celery
│   ├── test_status_endpoint.py  # GET /jobs/{id}/status
│   └── test_mcp_tools.py        # Platy MCP server tool calls
└── conftest.py                  # shared fixtures (mock Redis, mock OpenRouter)
```

**Key test patterns:**
- Mock OpenRouter calls with `pytest-httpx` (intercepts `httpx.AsyncClient` calls)
- Use `CELERY_TASK_ALWAYS_EAGER=True` for in-process task execution in tests
- Mock Redis with `fakeredis` library or use a real Redis started by Docker Compose test profile

### Frontend Linting — ESLint + TypeScript

```bash
# Lint frontend
cd frontend && pnpm lint

# Type check
pnpm exec tsc --noEmit
```

### Frontend Testing — Vitest

```bash
cd frontend && pnpm test

# Watch mode
pnpm test --watch

# With coverage
pnpm test --coverage
```

### Pre-commit Hooks (optional but recommended)

Install `pre-commit` and add a `.pre-commit-config.yaml`:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

---

## 8. Project Structure

```
resume_checker_app/
├── pyproject.toml               # Python project config (uv, ruff, mypy, pytest)
├── uv.lock                      # Python lock file (committed)
├── .env                         # Local secrets (NOT committed)
├── .env.example                 # Template for .env (committed)
├── .gitignore
├── docker-compose.yml           # Local development orchestration
├── Dockerfile.backend           # FastAPI + Celery image
│
├── app/                         # FastAPI backend
│   ├── main.py                  # FastAPI app creation, middleware, exception handlers
│   ├── routes/
│   │   ├── analyze.py           # POST /api/v1/analyze
│   │   ├── jobs.py              # GET /api/v1/jobs/{job_id}/status
│   │   └── health.py            # GET /api/v1/health
│   ├── schemas.py               # All Pydantic models (AnalysisResult, JobStatusResponse, etc.)
│   ├── celery_app.py            # Celery application instance + config
│   ├── tasks/
│   │   ├── __init__.py
│   │   ├── ingest_cv.py         # Task: extract text, strip PII
│   │   ├── extract_cv_structure.py  # Task: LLM-based CV structuring
│   │   ├── compute_score.py     # Task: weighted scoring
│   │   ├── estimate_salary.py   # Task: MCP lookup + fallback
│   │   ├── generate_explanation.py  # Task: LLM explanation
│   │   └── assemble_output.py   # Task: validate + store result
│   ├── pipeline.py              # chain() definition and run_analysis_pipeline()
│   ├── llm/
│   │   ├── client.py            # httpx wrapper for OpenRouter calls
│   │   └── prompts.py           # extraction and explanation prompt templates
│   ├── mcp_client.py            # MCP client session management
│   ├── job_store.py             # Redis reads/writes for job state
│   ├── config.py                # pydantic-settings Settings class
│   └── utils/
│       ├── pdf_extractor.py     # pdfplumber-based extraction
│       ├── docx_extractor.py    # python-docx-based extraction
│       ├── pii_stripper.py      # strip_pii_from_text
│       └── file_validator.py    # MIME type + size validation
│
├── platy_mcp/                   # Platy MCP server
│   ├── server.py                # FastMCP entry point
│   ├── tools.py                 # @mcp.tool() definitions
│   └── data/
│       ├── salary_data.json     # Curated Platy.cz salary data
│       └── roles.json           # Canonical role category list
│
├── config/                      # Static configuration files
│   ├── scoring_weights.yaml     # Sub-score weights (must sum to 100)
│   ├── salary_bands.yaml        # Fallback salary bands
│   └── role_mappings.yaml       # Role title → category mapping
│
├── frontend/                    # React frontend
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   ├── .env.local               # Frontend env vars (NOT committed)
│   └── src/
│       ├── main.tsx
│       ├── api/
│       │   └── client.ts        # Typed API client
│       ├── components/
│       │   ├── UploadForm.tsx
│       │   ├── ProgressTracker.tsx
│       │   ├── ScoreGauge.tsx
│       │   ├── SalaryRange.tsx
│       │   ├── ExplanationPanel.tsx
│       │   └── ErrorBanner.tsx
│       ├── hooks/
│       │   └── useAnalysis.ts   # React Query polling hook
│       ├── pages/
│       │   └── AnalyzerPage.tsx
│       ├── types/
│       │   └── api.ts           # TypeScript types (mirror Pydantic models)
│       └── test/
│           └── setup.ts
│
└── tests/                       # Backend tests
    ├── unit/
    ├── integration/
    └── conftest.py
```

---

## 9. Docker Compose Setup

The `docker-compose.yml` orchestrates the full development environment. Run with `docker compose up`.

```yaml
# docker-compose.yml
version: "3.9"

services:

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ports:
      - "8000:8000"
    volumes:
      - .:/app                     # mount source for --reload to work
      - /tmp/uploads:/tmp/uploads  # shared temp upload dir
    env_file:
      - .env
    environment:
      REDIS_URL: redis://redis:6379/0
      UPLOAD_DIR: /tmp/uploads
    depends_on:
      redis:
        condition: service_healthy

  worker:
    build:
      context: .
      dockerfile: Dockerfile.backend
    command: celery -A app.celery_app worker --loglevel=info --concurrency=2
    volumes:
      - .:/app
      - /tmp/uploads:/tmp/uploads
    env_file:
      - .env
    environment:
      REDIS_URL: redis://redis:6379/0
      UPLOAD_DIR: /tmp/uploads
    depends_on:
      redis:
        condition: service_healthy

  frontend:
    image: node:20-alpine
    working_dir: /app
    command: sh -c "corepack enable pnpm && pnpm install && pnpm dev --host 0.0.0.0"
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
    environment:
      VITE_API_BASE_URL: http://localhost:8000/api/v1

  # Optional: Celery monitoring UI
  flower:
    build:
      context: .
      dockerfile: Dockerfile.backend
    command: celery -A app.celery_app flower --port=5555
    ports:
      - "5555:5555"
    env_file:
      - .env
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy
    profiles:
      - monitoring    # only starts with: docker compose --profile monitoring up
```

### Dockerfile.backend

```dockerfile
# Dockerfile.backend
FROM python:3.12-slim-bookworm

# System dependencies (libmagic for python-magic)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev extras in production)
RUN uv sync --frozen --no-dev

# Copy application code
COPY app/ ./app/
COPY platy_mcp/ ./platy_mcp/
COPY config/ ./config/

# Use uv-managed Python
ENV PATH="/app/.venv/bin:$PATH"
```

### Common Commands

```bash
# Start all services (backend + worker + frontend + redis)
docker compose up

# Start with Celery monitoring (Flower)
docker compose --profile monitoring up

# Start only backend dependencies (redis), run backend locally
docker compose up redis
uv run uvicorn app.main:app --reload

# Run backend tests
docker compose up redis -d
uv run pytest

# Rebuild after dependency changes
docker compose build backend worker

# View Celery task logs
docker compose logs worker -f

# Access Flower monitoring UI
open http://localhost:5555
```

---

## 10. Environment Variable Reference

Complete list of all environment variables. Copy `.env.example` to `.env` and fill in values.

### `.env.example`

```bash
# ===========================================================================
# REQUIRED — Application will not start without these
# ===========================================================================

# OpenRouter API key (get from https://openrouter.ai/keys)
OPENROUTER_API_KEY=sk-or-v1-REPLACE_WITH_YOUR_KEY

# ===========================================================================
# LLM CONFIGURATION
# ===========================================================================

# OpenRouter API base URL (do not change unless using a different proxy)
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Model to use via OpenRouter (must support JSON response format)
OPENROUTER_MODEL=openai/gpt-4o

# LLM temperature: 0.0 for deterministic output
LLM_TEMPERATURE=0.0

# Per-call timeout in seconds (applied to both extraction and explanation calls)
LLM_TIMEOUT_SECONDS=30

# ===========================================================================
# REDIS
# ===========================================================================

# Redis connection URL (used by both FastAPI job store and Celery)
REDIS_URL=redis://localhost:6379/0

# ===========================================================================
# SERVER
# ===========================================================================

# FastAPI bind host
BACKEND_HOST=0.0.0.0

# FastAPI bind port
BACKEND_PORT=8000

# Frontend URL — used for CORS allowed origins
FRONTEND_URL=http://localhost:5173

# ===========================================================================
# FILE HANDLING
# ===========================================================================

# Directory for temporary uploaded CV files
# Must be writable by both the FastAPI process and the Celery worker process
UPLOAD_DIR=/tmp/uploads

# Maximum upload file size in bytes (default: 10 MB = 10485760)
MAX_FILE_SIZE_BYTES=10485760

# ===========================================================================
# PIPELINE LIMITS
# ===========================================================================

# Maximum number of concurrent analysis jobs
# Jobs beyond this limit receive a 429 response
MAX_CONCURRENT_JOBS=5

# ===========================================================================
# CACHING (optional feature, disabled by default)
# ===========================================================================

# Enable LLM response caching keyed by SHA-256 hash of CV text
LLM_CACHE_ENABLED=false

# Cache TTL in seconds (default: 24 hours)
LLM_CACHE_TTL_SECONDS=86400

# ===========================================================================
# LOGGING
# ===========================================================================

# Log level: DEBUG | INFO | WARNING | ERROR
LOG_LEVEL=INFO

# ===========================================================================
# CELERY
# ===========================================================================

# Celery task routing (all tasks go to the default queue for MVP)
CELERY_DEFAULT_QUEUE=default

# ===========================================================================
# APPLICATION
# ===========================================================================

# Application version (shown in health check response)
APP_VERSION=1.0.0
```

### Variable Summary Table

| Variable | Required | Default | Type | Description |
|----------|----------|---------|------|-------------|
| `OPENROUTER_API_KEY` | Yes | — | string | OpenRouter API key; validated at startup |
| `OPENROUTER_BASE_URL` | No | `https://openrouter.ai/api/v1` | string | OpenRouter base URL |
| `OPENROUTER_MODEL` | No | `openai/gpt-4o` | string | Model identifier |
| `LLM_TEMPERATURE` | No | `0.0` | float | LLM temperature; 0.0 for determinism |
| `LLM_TIMEOUT_SECONDS` | No | `30` | int | Per-call LLM timeout |
| `REDIS_URL` | No | `redis://localhost:6379/0` | string | Redis connection URL |
| `BACKEND_HOST` | No | `0.0.0.0` | string | FastAPI bind host |
| `BACKEND_PORT` | No | `8000` | int | FastAPI bind port |
| `FRONTEND_URL` | No | `http://localhost:5173` | string | Allowed CORS origin |
| `UPLOAD_DIR` | No | `/tmp/uploads` | string | Temp file directory (absolute path) |
| `MAX_FILE_SIZE_BYTES` | No | `10485760` | int | Max upload file size |
| `MAX_CONCURRENT_JOBS` | No | `5` | int | Concurrent job limit |
| `LLM_CACHE_ENABLED` | No | `false` | bool | Enable LLM response cache |
| `LLM_CACHE_TTL_SECONDS` | No | `86400` | int | Cache TTL |
| `LOG_LEVEL` | No | `INFO` | string | Logging verbosity |
| `CELERY_DEFAULT_QUEUE` | No | `default` | string | Celery queue name |
| `APP_VERSION` | No | `1.0.0` | string | Shown in health check |

### `pydantic-settings` Config Class

```python
# app/config.py
from pydantic import AnyUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Required
    openrouter_api_key: str

    # LLM
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o"
    llm_temperature: float = 0.0
    llm_timeout_seconds: int = 30

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Server
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_url: str = "http://localhost:5173"

    # File handling
    upload_dir: str = "/tmp/uploads"
    max_file_size_bytes: int = 10 * 1024 * 1024  # 10 MB

    # Pipeline limits
    max_concurrent_jobs: int = 5

    # Caching
    llm_cache_enabled: bool = False
    llm_cache_ttl_seconds: int = 86400

    # Logging
    log_level: str = "INFO"

    # App
    app_version: str = "1.0.0"
    celery_default_queue: str = "default"

    @field_validator("openrouter_api_key")
    @classmethod
    def api_key_must_not_be_empty(cls, v: str) -> str:
        if not v or v == "REPLACE_WITH_YOUR_KEY":
            raise ValueError("OPENROUTER_API_KEY must be set to a valid key")
        return v


# Singleton — import this throughout the application
settings = Settings()
```

---

## 11. Startup Validation

The application performs the following checks at startup (before accepting requests). Any failure causes the process to exit with a non-zero code and a clear error message.

| Check | What is Validated | Failure Behavior |
|-------|-------------------|-----------------|
| API key present | `OPENROUTER_API_KEY` is set and non-empty | Process exits; logs: "OPENROUTER_API_KEY is not configured. Set it in .env" |
| Upload dir writable | `UPLOAD_DIR` exists and is writable | Process exits; logs directory path and suggests `mkdir -p` |
| Redis reachable | `redis.ping()` succeeds | Process exits; logs Redis URL |
| Scoring weights valid | Sum of weights == 100 | Process exits; logs current values |
| Salary bands valid | All tiers have `min_czk < max_czk` and both > 0 | Process exits; logs which band is invalid |
| libmagic available | `import magic` succeeds | Warning only; falls back to extension validation |

Celery worker additionally validates:
- MCP server process starts successfully on `worker_init`; if it fails, worker logs a warning and uses fallback bands only

---

## 12. Version Pinning Strategy

**Python packages:** Use range constraints (`>=X.Y,<Z.0`) in `pyproject.toml`. The `uv.lock` file pins exact versions for reproducible builds. CI and Docker always install from the lock file (`uv sync --frozen`).

**Node packages:** Use `^X.Y.Z` (minor-compatible) in `package.json`. The `pnpm-lock.yaml` pins exact versions.

**Updating dependencies:**
```bash
# Python — update all to latest within constraints
uv lock --upgrade
uv sync

# Node — update all to latest within constraints
cd frontend && pnpm update
```

Run the full test suite after any dependency update before committing the updated lock file.

**Docker images:** Pin to major version tags (`redis:7-alpine`, `python:3.12-slim-bookworm`, `node:20-alpine`), not `latest`. Update manually when a new major version is adopted.
