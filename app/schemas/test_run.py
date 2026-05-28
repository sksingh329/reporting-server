from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel


TestStatus = Literal["passed", "failed", "skipped", "error"]


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str


class ScreenshotIn(BaseModel):
    storage_key: str
    step_name: Optional[str] = None
    is_failure_screenshot: bool = False


class TestCaseCreate(BaseModel):
    project_id: int
    test_name: str
    status: TestStatus
    environment: str = "default"
    duration_ms: Optional[float] = None
    error_message: Optional[str] = None
    log_storage_key: Optional[str] = None
    screenshots: List[ScreenshotIn] = []


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ProjectOut(BaseModel):
    id: int
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ScreenshotOut(BaseModel):
    id: int
    storage_key: str
    step_name: Optional[str]
    taken_at: datetime
    is_failure_screenshot: bool
    image_data: Optional[str] = None  # base64 data URI, usable as <img src> directly

    model_config = {"from_attributes": True}


class SubmittedByOut(BaseModel):
    type: str  # "user" | "service_token"
    name: str


class TestExecutionOut(BaseModel):
    id: int
    test_case_id: int
    environment: str
    status: str
    duration_ms: Optional[float]
    error_message: Optional[str]
    reported_at: datetime
    log: Optional[str] = None
    screenshots: List[ScreenshotOut] = []
    submitted_by: Optional[SubmittedByOut] = None

    model_config = {"from_attributes": True}


class TestCaseOut(BaseModel):
    id: int
    project_id: int
    name: str
    executions: List[TestExecutionOut] = []

    model_config = {"from_attributes": True}


class TestCaseSummaryOut(BaseModel):
    """Lightweight view used in list endpoints — only the latest execution is included."""

    id: int
    project_id: int
    name: str
    latest_status: Optional[str] = None       # status of the most recent execution
    total_executions: int = 0
    failed_count: int = 0
    latest_execution: Optional[TestExecutionOut] = None

    model_config = {"from_attributes": True}

