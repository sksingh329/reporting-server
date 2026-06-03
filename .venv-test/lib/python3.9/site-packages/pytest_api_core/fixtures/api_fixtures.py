"""
Auto-registered pytest fixtures provided by pytest-api-core.

These fixtures are available in every test suite that has the package
installed — no ``conftest.py`` import required.

Fixtures
--------
api_config      (session)  — resolved config dict for the target environment
api_client      (session)  — configured APIClient instance
api_bearer_auth (function) — BearerAuth instance (token from cfg or API_TOKEN)
api_basic_auth  (function) — BasicAuth instance (from API_USERNAME / API_PASSWORD)
api_key_auth    (function) — APIKeyAuth instance
"""
from __future__ import annotations

import os
from typing import Any, Generator

import pytest

from pytest_api_core.auth.auth_handlers import APIKeyAuth, BasicAuth, BearerAuth
from pytest_api_core.client.api_client import APIClient
from pytest_api_core.config.config_manager import ConfigManager


# ---------------------------------------------------------------------------
# Config fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def api_config(request: pytest.FixtureRequest) -> dict[str, Any]:
    """
    Returns the fully-resolved configuration dict for the active environment.

    Override via CLI: ``--api-env=staging --api-config-dir=config/env``
    Override via ini: ``api_env = staging``
    Override via env-var: ``API_ENV=staging``
    """
    env: str | None = (
        request.config.getoption("--api-env", default=None)
        or request.config.getini("api_env")
        or None
    )
    config_dir: str = (
        request.config.getoption("--api-config-dir", default="config/env")
        or request.config.getini("api_config_dir")
        or "config/env"
    )
    base_url_override: str | None = request.config.getoption("--api-base-url", default=None)

    manager = ConfigManager(
        env=env,
        config_dir=config_dir,
        cli_overrides={"base_url": base_url_override} if base_url_override else None,
    )
    return manager.load()


# ---------------------------------------------------------------------------
# Client fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def api_client(api_config: dict[str, Any]) -> Generator[APIClient, None, None]:
    """
    Session-scoped APIClient built from *api_config*.

    Automatically applies a BearerAuth if ``API_TOKEN`` env-var is set
    or ``api_config["_token"]`` is present.
    """
    auth = None
    token = api_config.pop("_token", None) or os.environ.get("API_TOKEN")
    if token:
        auth = BearerAuth(token)

    client = APIClient(
        base_url=api_config["base_url"],
        auth=auth,
        timeout=api_config.get("timeout", 30),
        verify_ssl=api_config.get("verify_ssl", True),
        default_headers=api_config.get("headers"),
    )
    yield client
    client.close()


# ---------------------------------------------------------------------------
# Auth fixtures (function-scoped so tests can customise per-test)
# ---------------------------------------------------------------------------


@pytest.fixture()
def api_bearer_auth(api_config: dict[str, Any]) -> BearerAuth:
    """
    BearerAuth built from ``API_TOKEN`` env-var or ``api_config["token"]``.
    Raises if no token is available.
    """
    token = os.environ.get("API_TOKEN") or api_config.get("token")
    if not token:
        raise ValueError(
            "api_bearer_auth requires an API token. "
            "Set the API_TOKEN environment variable or add 'token' to your env config."
        )
    return BearerAuth(token)


@pytest.fixture()
def api_basic_auth() -> BasicAuth:
    """
    BasicAuth built from ``API_USERNAME`` / ``API_PASSWORD`` env-vars.
    Raises if either is missing.
    """
    username = os.environ.get("API_USERNAME", "")
    password = os.environ.get("API_PASSWORD", "")
    if not username or not password:
        raise ValueError(
            "api_basic_auth requires API_USERNAME and API_PASSWORD environment variables."
        )
    return BasicAuth(username, password)


@pytest.fixture()
def api_key_auth() -> APIKeyAuth:
    """
    APIKeyAuth built from ``API_KEY_NAME`` / ``API_KEY_VALUE`` / ``API_KEY_LOCATION`` env-vars.
    """
    name = os.environ.get("API_KEY_NAME", "x-api-key")
    value = os.environ.get("API_KEY_VALUE", "")
    location = os.environ.get("API_KEY_LOCATION", "header")
    if not value:
        raise ValueError(
            "api_key_auth requires API_KEY_VALUE environment variable."
        )
    return APIKeyAuth(name, value, location)
