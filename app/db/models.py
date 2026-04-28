from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(128), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(16), nullable=False, default="user")  # admin | user
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    user = relationship("User", back_populates="refresh_tokens")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    test_cases = relationship("TestCase", back_populates="project", cascade="all, delete-orphan")


class TestCase(Base):
    """Stable identity for a test within a project. One row per unique test name."""

    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(512), nullable=False, index=True)

    __table_args__ = (UniqueConstraint("project_id", "name"),)

    project = relationship("Project", back_populates="test_cases")
    executions = relationship("TestExecution", back_populates="test_case", cascade="all, delete-orphan")


class TestExecution(Base):
    """One row per execution (run) of a TestCase."""

    __tablename__ = "test_executions"

    id = Column(Integer, primary_key=True, index=True)
    test_case_id = Column(Integer, ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(16), nullable=False, index=True)  # passed | failed | skipped | error
    duration_ms = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    reported_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    log_storage_key = Column(String(1024), nullable=True)

    test_case = relationship("TestCase", back_populates="executions")
    screenshots = relationship("TestScreenshot", back_populates="test_execution", cascade="all, delete-orphan")


class TestScreenshot(Base):
    __tablename__ = "test_screenshots"

    id = Column(Integer, primary_key=True, index=True)
    test_execution_id = Column(Integer, ForeignKey("test_executions.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_key = Column(String(1024), nullable=False)
    step_name = Column(String(255), nullable=True)
    taken_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    is_failure_screenshot = Column(Boolean, nullable=False, default=False)

    test_execution = relationship("TestExecution", back_populates="screenshots")
