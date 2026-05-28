import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.ingest import router as ingest_router
from app.api.service_tokens import router as service_tokens_router
from app.api.users import router as users_router
from app.core.config import settings
from app.db.session import engine
from app.db import models  # noqa: F401 — ensure models are registered before create_all

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _migrate(engine) -> None:
    """
    Migrate from old schema (test_runs + test_cases with test_run_id)
    to new schema (test_cases as stable identity + test_executions per run).
    Safe to run on an already-migrated DB.
    """
    with engine.connect() as conn:
        tables = {r[0] for r in conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )).fetchall()}

        if "test_executions" in tables:
            return  # Already on new schema

        if "test_runs" not in tables:
            return  # Fresh DB — create_all will build the right tables

        logger.info("Migrating DB schema to stable test_case identity model...")

        # 1. Preserve old test_cases rows
        conn.execute(text("ALTER TABLE test_cases RENAME TO _old_test_cases"))
        conn.commit()

        # 2. Create new tables manually (create_all runs after this)
        conn.execute(text("""
            CREATE TABLE test_cases (
                id   INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name VARCHAR(512) NOT NULL,
                UNIQUE (project_id, name)
            )
        """))
        conn.execute(text("""
            CREATE TABLE test_executions (
                id           INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                test_case_id INTEGER NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
                status       VARCHAR(16) NOT NULL,
                duration_ms  FLOAT,
                error_message TEXT,
                reported_at  DATETIME NOT NULL,
                log_storage_key VARCHAR(1024)
            )
        """))
        conn.commit()

        # 3. Migrate rows: join old test_cases with test_runs to get project_id
        old_rows = conn.execute(text("""
            SELECT oc.id, tr.project_id, oc.name, oc.status, oc.duration_ms,
                   oc.error_message, oc.reported_at, oc.log_storage_key
            FROM _old_test_cases oc
            JOIN test_runs tr ON tr.id = oc.test_run_id
        """)).fetchall()

        case_map: dict = {}   # (project_id, name) -> new test_case id
        exec_map: dict = {}   # old test_case id   -> new test_execution id

        for old_id, project_id, name, status, dur, err, rep, log_key in old_rows:
            key = (project_id, name)
            if key not in case_map:
                r = conn.execute(text(
                    "INSERT INTO test_cases (project_id, name) VALUES (:pid, :n)"
                ), {"pid": project_id, "n": name})
                case_map[key] = r.lastrowid

            r = conn.execute(text("""
                INSERT INTO test_executions
                    (test_case_id, status, duration_ms, error_message, reported_at, log_storage_key)
                VALUES (:tcid, :st, :dur, :err, :rep, :log)
            """), {"tcid": case_map[key], "st": status, "dur": dur,
                   "err": err, "rep": rep, "log": log_key})
            exec_map[old_id] = r.lastrowid

        conn.commit()

        # 4. Migrate screenshots: rename FK column and update references
        try:
            conn.execute(text(
                "ALTER TABLE test_screenshots RENAME COLUMN test_case_id TO test_execution_id"
            ))
            for old_tc_id, new_exec_id in exec_map.items():
                conn.execute(text(
                    "UPDATE test_screenshots SET test_execution_id = :eid WHERE test_execution_id = :oid"
                ), {"eid": new_exec_id, "oid": old_tc_id})
            conn.commit()
        except Exception as exc:
            logger.warning("Screenshot migration skipped: %s", exc)

        # 5. Drop old tables
        conn.execute(text("DROP TABLE IF EXISTS _old_test_cases"))
        conn.execute(text("DROP TABLE IF EXISTS test_runs"))
        conn.commit()
        logger.info("Schema migration complete.")


_migrate(engine)


def _ensure_columns(engine) -> None:
    """Add new columns to existing tables without dropping data (SQLite ALTER TABLE)."""
    with engine.connect() as conn:
        tables = {r[0] for r in conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )).fetchall()}
        if "test_executions" not in tables:
            return  # fresh DB — create_all will handle everything
        existing_cols = {r[1] for r in conn.execute(text(
            "PRAGMA table_info(test_executions)"
        )).fetchall()}
        if "submitted_by_user_id" not in existing_cols:
            conn.execute(text(
                "ALTER TABLE test_executions ADD COLUMN submitted_by_user_id INTEGER "
                "REFERENCES users(id) ON DELETE SET NULL"
            ))
            conn.commit()
        if "submitted_by_token_id" not in existing_cols:
            conn.execute(text(
                "ALTER TABLE test_executions ADD COLUMN submitted_by_token_id INTEGER "
                "REFERENCES service_tokens(id) ON DELETE SET NULL"
            ))
            conn.commit()
        if "environment" not in existing_cols:
            conn.execute(text(
                "ALTER TABLE test_executions ADD COLUMN environment VARCHAR(128) NOT NULL DEFAULT 'default'"
            ))
            conn.commit()


_ensure_columns(engine)
models.Base.metadata.create_all(bind=engine)



app = FastAPI(
    title="Test Reporting Server",
    description="Collects automated test results, stores structured data in SQLite and artifacts in MinIO.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(service_tokens_router)
app.include_router(ingest_router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}
