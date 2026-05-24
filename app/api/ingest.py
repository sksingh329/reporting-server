import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_admin
from app.db.session import get_db
from app.schemas.test_run import (
    ProjectCreate,
    ProjectOut,
    ScreenshotIn,
    TestCaseCreate,
    TestCaseOut,
    TestCaseSummaryOut,
    TestExecutionOut,
)
from app.services import ingest_service
from app.services.storage_service import _safe_segment, storage_service

router = APIRouter(prefix="/api", tags=["ingest"])

_404 = status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@router.get("/projects", response_model=list[ProjectOut], summary="List all projects")
def list_projects(db: Session = Depends(get_db), _=Depends(get_current_user)) -> list[ProjectOut]:
    return ingest_service.list_projects(db)


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED, summary="Create a project")
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), _=Depends(require_admin)) -> ProjectOut:
    return ingest_service.create_project(payload, db)


@router.get("/projects/{project_id}", response_model=ProjectOut, summary="Get a project")
def get_project(project_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)) -> ProjectOut:
    result = ingest_service.get_project(project_id, db)
    if result is None:
        raise HTTPException(status_code=_404, detail="Project not found")
    return result


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project and all its data (admin only)",
)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> None:
    result = ingest_service.get_project(project_id, db)
    if result is None:
        raise HTTPException(status_code=_404, detail="Project not found")
    ingest_service.delete_project(project_id, db)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/test-cases",
    response_model=TestCaseOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a test execution",
)
async def create_test_case(
    project_id: int,
    test_name: str = Form(...),
    test_status: str = Form(..., alias="status"),
    duration_ms: Optional[float] = Form(None),
    error_message: Optional[str] = Form(None),
    log_text: Optional[str] = Form(None),
    screenshots: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> TestCaseOut:
    """Ingest one test execution. Returns 404 if the project does not exist."""
    log_storage_key: Optional[str] = None
    screenshot_ins: list[ScreenshotIn] = []

    if log_text is not None:
        log_key = (
            f"logs/{project_id}"
            f"/{_safe_segment(test_name)}"
            f"/{uuid.uuid4().hex[:8]}-run.log"
        )
        storage_service.upload_file(log_key, log_text.encode("utf-8"), "text/plain")
        log_storage_key = log_key

    for idx, screenshot in enumerate(screenshots):
        file_bytes = await screenshot.read()
        filename = screenshot.filename or "screenshot.png"
        content_type = screenshot.content_type or "image/png"
        storage_key = (
            f"screenshots/{project_id}"
            f"/{_safe_segment(test_name)}"
            f"/{uuid.uuid4().hex[:8]}-{_safe_segment(filename)}"
        )
        storage_service.upload_file(storage_key, file_bytes, content_type)
        step_name = filename.rsplit(".", 1)[0] if "." in filename else filename
        screenshot_ins.append(ScreenshotIn(
            storage_key=storage_key,
            step_name=step_name,
            is_failure_screenshot=(test_status == "failed"),
        ))

    try:
        return ingest_service.ingest_test_case(
            TestCaseCreate(
                project_id=project_id,
                test_name=test_name,
                status=test_status,
                duration_ms=duration_ms,
                error_message=error_message,
                log_storage_key=log_storage_key,
                screenshots=screenshot_ins,
            ),
            db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=_404, detail=str(exc))


@router.get(
    "/projects/{project_id}/test-cases",
    response_model=list[TestCaseSummaryOut],
    summary="List all test cases with latest execution (optionally filtered by status)",
)
def list_test_cases(
    project_id: int,
    status: Optional[str] = Query(None, description="Filter by status: passed | failed | skipped | error"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> list[TestCaseSummaryOut]:
    result = ingest_service.list_test_cases(project_id, db, status_filter=status)
    if result is None:
        raise HTTPException(status_code=_404, detail="Project not found")
    return result


@router.get(
    "/projects/{project_id}/test-cases/{test_case_id}",
    response_model=TestCaseOut,
    summary="Get a test case with all its executions",
)
def get_test_case(project_id: int, test_case_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)) -> TestCaseOut:
    result = ingest_service.get_test_case(project_id, test_case_id, db)
    if result is None:
        raise HTTPException(status_code=_404, detail="Test case not found")
    return result


@router.delete(
    "/projects/{project_id}/test-cases/{test_case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a test case and all its executions (admin only)",
)
def delete_test_case(
    project_id: int,
    test_case_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> None:
    deleted = ingest_service.delete_test_case(project_id, test_case_id, db)
    if not deleted:
        raise HTTPException(status_code=_404, detail="Test case not found")


# ---------------------------------------------------------------------------
# Executions
# ---------------------------------------------------------------------------

@router.get(
    "/projects/{project_id}/test-cases/{test_case_id}/executions",
    response_model=list[TestExecutionOut],
    summary="List all executions of a test case",
)
def list_executions(project_id: int, test_case_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)) -> list[TestExecutionOut]:
    result = ingest_service.list_executions(project_id, test_case_id, db)
    if result is None:
        raise HTTPException(status_code=_404, detail="Test case not found")
    return result


@router.get(
    "/projects/{project_id}/test-cases/{test_case_id}/executions/{execution_id}",
    response_model=TestExecutionOut,
    summary="Get a single execution",
)
def get_execution(
    project_id: int, test_case_id: int, execution_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)
) -> TestExecutionOut:
    result = ingest_service.get_execution(project_id, test_case_id, execution_id, db)
    if result is None:
        raise HTTPException(status_code=_404, detail="Execution not found")
    return result


@router.delete(
    "/projects/{project_id}/test-cases/{test_case_id}/executions/{execution_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a single execution and its artifacts (admin only)",
)
def delete_execution(
    project_id: int,
    test_case_id: int,
    execution_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> None:
    deleted = ingest_service.delete_execution(project_id, test_case_id, execution_id, db)
    if not deleted:
        raise HTTPException(status_code=_404, detail="Execution not found")



