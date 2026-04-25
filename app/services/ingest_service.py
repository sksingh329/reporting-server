from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import Project, TestCase, TestExecution, TestScreenshot
from app.schemas.test_run import ProjectCreate, ProjectOut, TestCaseCreate, TestCaseOut, TestCaseSummaryOut, TestExecutionOut


def create_project(payload: ProjectCreate, db: Session) -> ProjectOut:
    project = Project(name=payload.name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return ProjectOut.model_validate(project)


def _find_or_create_project(project_name: str, db: Session) -> Project:
    project = db.query(Project).filter(Project.name == project_name).first()
    if project is None:
        project = Project(name=project_name)
        db.add(project)
        db.flush()
    return project


def _find_or_create_test_case(project_id: int, test_name: str, db: Session) -> TestCase:
    test_case = (
        db.query(TestCase)
        .filter(TestCase.project_id == project_id, TestCase.name == test_name)
        .first()
    )
    if test_case is None:
        test_case = TestCase(project_id=project_id, name=test_name)
        db.add(test_case)
        db.flush()
    return test_case


def ingest_test_case(payload: TestCaseCreate, db: Session) -> TestCaseOut:
    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if project is None:
        raise ValueError(f"Project {payload.project_id} not found")
    test_case = _find_or_create_test_case(project.id, payload.test_name, db)

    execution = TestExecution(
        test_case_id=test_case.id,
        status=payload.status,
        duration_ms=payload.duration_ms,
        error_message=payload.error_message,
        log_storage_key=payload.log_storage_key,
    )
    db.add(execution)
    db.flush()

    for sc in payload.screenshots:
        db.add(TestScreenshot(
            test_execution_id=execution.id,
            storage_key=sc.storage_key,
            step_name=sc.step_name,
            is_failure_screenshot=sc.is_failure_screenshot,
        ))

    db.commit()
    db.refresh(test_case)
    return _build_test_case_out(test_case)


def _build_execution_out(execution: TestExecution) -> TestExecutionOut:
    from app.services.storage_service import storage_service

    out = TestExecutionOut.model_validate(execution)

    if execution.log_storage_key:
        try:
            out.log = storage_service.fetch_object(execution.log_storage_key).decode("utf-8")
        except Exception:
            out.log = None

    for sc_out, sc_db in zip(out.screenshots, execution.screenshots):
        try:
            sc_out.download_url = storage_service.generate_download_url(sc_db.storage_key)
        except Exception:
            sc_out.download_url = None

    return out


def _build_test_case_out(test_case: TestCase) -> TestCaseOut:
    out = TestCaseOut.model_validate(test_case)
    out.executions = [_build_execution_out(e) for e in test_case.executions]
    return out


# ---------------------------------------------------------------------------
# List helpers
# ---------------------------------------------------------------------------

def list_projects(db: Session) -> list[ProjectOut]:
    return [ProjectOut.model_validate(p) for p in db.query(Project).order_by(Project.id).all()]


def list_test_cases(
    project_id: int,
    db: Session,
    status_filter: Optional[str] = None,
) -> Optional[list[TestCaseSummaryOut]]:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        return None

    from sqlalchemy import func

    # Latest execution id per test case
    latest_exec_id = (
        db.query(func.max(TestExecution.id))
        .filter(TestExecution.test_case_id == TestCase.id)
        .correlate(TestCase)
        .scalar_subquery()
    )

    # Total executions per test case
    total_count = (
        db.query(func.count(TestExecution.id))
        .filter(TestExecution.test_case_id == TestCase.id)
        .correlate(TestCase)
        .scalar_subquery()
    )

    # Failed executions per test case
    fail_count = (
        db.query(func.count(TestExecution.id))
        .filter(TestExecution.test_case_id == TestCase.id, TestExecution.status == "failed")
        .correlate(TestCase)
        .scalar_subquery()
    )

    query = (
        db.query(TestCase, TestExecution, total_count.label("total"), fail_count.label("fails"))
        .outerjoin(TestExecution, TestExecution.id == latest_exec_id)
        .filter(TestCase.project_id == project_id)
    )
    if status_filter:
        query = query.filter(TestExecution.status == status_filter)

    results = []
    for test_case, latest_exec, total, fails in query.order_by(TestCase.id).all():
        summary = TestCaseSummaryOut(
            id=test_case.id,
            project_id=test_case.project_id,
            name=test_case.name,
            latest_status=latest_exec.status if latest_exec else None,
            total_executions=total or 0,
            failed_count=fails or 0,
            latest_execution=_build_execution_out(latest_exec) if latest_exec else None,
        )
        results.append(summary)
    return results


def list_executions(project_id: int, test_case_id: int, db: Session) -> Optional[list[TestExecutionOut]]:
    test_case = (
        db.query(TestCase)
        .filter(TestCase.id == test_case_id, TestCase.project_id == project_id)
        .first()
    )
    if test_case is None:
        return None
    return [_build_execution_out(e) for e in test_case.executions]


# ---------------------------------------------------------------------------
# Single-resource getters with parent validation
# ---------------------------------------------------------------------------

def get_project(project_id: int, db: Session) -> Optional[ProjectOut]:
    project = db.query(Project).filter(Project.id == project_id).first()
    return ProjectOut.model_validate(project) if project else None


def get_test_case(project_id: int, test_case_id: int, db: Session) -> Optional[TestCaseOut]:
    test_case = (
        db.query(TestCase)
        .filter(TestCase.id == test_case_id, TestCase.project_id == project_id)
        .first()
    )
    return _build_test_case_out(test_case) if test_case else None


def get_execution(project_id: int, test_case_id: int, execution_id: int, db: Session) -> Optional[TestExecutionOut]:
    execution = (
        db.query(TestExecution)
        .join(TestCase)
        .filter(
            TestExecution.id == execution_id,
            TestExecution.test_case_id == test_case_id,
            TestCase.project_id == project_id,
        )
        .first()
    )
    return _build_execution_out(execution) if execution else None

