import configparser
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]

# Load secrets from .env (does not override already-set env vars)
load_dotenv(_ROOT / ".env")

# Resolve config.ini relative to the project root
_CONFIG_PATH = _ROOT / "config.ini"

_parser = configparser.ConfigParser()
_parser.read(_CONFIG_PATH)
_ini = _parser["reporting-server"] if "reporting-server" in _parser else {}


def _get(key: str, default: str) -> str:
    """Return value with priority: env var > config.ini > hard-coded default."""
    return os.environ.get(key, _ini.get(key.lower(), default))


@dataclass
class Settings:
    # Database
    DATABASE_URL: str = ""

    # MinIO / S3-compatible storage
    STORAGE_ENDPOINT: str = ""
    STORAGE_ACCESS_KEY: str = ""
    STORAGE_SECRET_KEY: str = ""
    STORAGE_BUCKET: str = ""
    STORAGE_REGION: str = ""
    PRESIGNED_URL_EXPIRY: int = 3600

    # JWT auth
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_EXPIRE_DAYS: int = 30

    # CORS — comma-separated allowed origins; use * for local dev
    CORS_ORIGINS: str = "*"


def _load_settings() -> Settings:
    return Settings(
        DATABASE_URL=_get("DATABASE_URL", "sqlite:///./reporting.db"),
        STORAGE_ENDPOINT=_get("STORAGE_ENDPOINT", "http://localhost:9000"),
        STORAGE_ACCESS_KEY=_get("STORAGE_ACCESS_KEY", "minio"),
        STORAGE_SECRET_KEY=_get("STORAGE_SECRET_KEY", "minio123"),
        STORAGE_BUCKET=_get("STORAGE_BUCKET", "test-artifacts"),
        STORAGE_REGION=_get("STORAGE_REGION", "us-east-1"),
        PRESIGNED_URL_EXPIRY=int(_get("PRESIGNED_URL_EXPIRY", "3600")),
        JWT_SECRET=_get("JWT_SECRET", "change-me-in-production"),
        JWT_ALGORITHM=_get("JWT_ALGORITHM", "HS256"),
        JWT_ACCESS_EXPIRE_MINUTES=int(_get("JWT_ACCESS_EXPIRE_MINUTES", "30")),
        JWT_REFRESH_EXPIRE_DAYS=int(_get("JWT_REFRESH_EXPIRE_DAYS", "30")),
        CORS_ORIGINS=_get("CORS_ORIGINS", "*"),
    )


settings = _load_settings()
