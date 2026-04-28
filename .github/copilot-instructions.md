# Reporting Server — Copilot Instructions

## Project Overview
FastAPI-based test reporting server. Clients (pytest automation frameworks) POST test results and screenshots after each test run. Results are stored in SQLite; binary artifacts (screenshots, logs) are stored in MinIO (S3-compatible).

## Stack
- **Framework**: FastAPI (Python 3.12)
- **DB**: SQLite via SQLAlchemy ORM (`/data/reporting.db` inside container)
- **Storage**: MinIO via `boto3` (S3-compatible, path-style URLs)
- **Container**: Podman / podman-compose, port `8000`
- **Config**: `config.ini` + env vars (secrets via `.env`)

## Project Structure
```
app/
  api/ingest.py        # All HTTP endpoints (single router, prefix /api)
  core/config.py       # Settings loaded from config.ini / env
  db/models.py         # SQLAlchemy models
  db/session.py        # DB engine + get_db dependency
  schemas/test_run.py  # Pydantic request/response models
  services/
    ingest_service.py  # Business logic, builds response objects
    storage_service.py # MinIO upload/download/fetch wrapper
```

## Data Model
- **Project** → many **TestCase** (unique per project+name) → many **TestExecution** → many **TestScreenshot**
- `TestExecution`: `status`, `duration_ms`, `error_message`, `log_storage_key`
- `TestScreenshot`: `storage_key`, `step_name` (derived from uploaded filename without extension), `is_failure_screenshot`

## Key API Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/projects` | Create project |
| GET | `/api/projects` | List projects |
| POST | `/api/projects/{id}/test-cases` | Ingest test result + screenshots |
| GET | `/api/projects/{id}/test-cases` | List test cases with latest execution |
| GET | `/api/projects/{id}/test-cases/{id}` | Full test case with all executions |
| GET | `/api/projects/{id}/test-cases/{id}/executions/{id}` | Single execution with embedded screenshots |

## Ingest Request (`multipart/form-data`)
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `test_name` | string | Yes | |
| `status` | string | Yes | `passed` / `failed` / `skipped` / `error` |
| `duration_ms` | float | No | |
| `error_message` | string | No | |
| `log_text` | string | No | Uploaded to MinIO, returned inline in response |
| `screenshots` | file(s) | No | Repeat field for multiple; filename (no ext) = `step_name` |

## Screenshot Handling
- Stored in MinIO under `screenshots/{project_id}/{test_name}/{uuid}-{filename}`
- Returned in responses as base64 `data:` URI in `image_data` field — usable directly as `<img src>`
- No presigned MinIO URLs are ever exposed to clients

## Conventions
- `_safe_segment()` in `storage_service.py` sanitises all storage key path segments
- `ingest_service._build_execution_out()` is where logs are fetched and `image_data` is populated
- Deploy: `podman stop reporting-server_reporting-server_1 && podman rm reporting-server_reporting-server_1 && podman compose up -d --build reporting-server`
