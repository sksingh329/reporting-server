import configparser
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_TESTS_DIR = Path(__file__).resolve().parent
_ROOT = _TESTS_DIR.parent

# Load test secrets from .env.test (does not override already-set env vars)
load_dotenv(_ROOT / ".env.test")

_parser = configparser.ConfigParser()
_parser.read(_TESTS_DIR / "test-config.ini")


def _get(section: str, key: str, default: str) -> str:
    """Return value with priority: env var > test-config.ini > hard-coded default."""
    env_key = key.upper()
    ini_value = _parser.get(section, key, fallback=default)
    return os.environ.get(env_key, ini_value)


@dataclass
class TestSettings:
    env: str
    base_url: str
    timeout: int
    verify_ssl: bool
    api_token: str


def load_test_settings(env: str = "prod") -> TestSettings:
    return TestSettings(
        env=env,
        base_url=_get(env, "base_url", "http://localhost:8000"),
        timeout=int(_get(env, "timeout", "30")),
        verify_ssl=_get(env, "verify_ssl", "true").lower() not in ("0", "false", "no"),
        api_token=os.environ.get("API_TOKEN", ""),
    )
