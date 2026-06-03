"""
pytest plugin entry-point.
Registered via [project.entry-points."pytest11"] in pyproject.toml so pytest
auto-discovers and loads it without any conftest.py changes in consuming projects.
"""
from __future__ import annotations

import pytest

from pytest_api_core.fixtures.api_fixtures import (
    api_config,
    api_client,
    api_bearer_auth,
    api_basic_auth,
    api_key_auth,
)
from pytest_api_core.reporters.html_reporter import HTMLReporter


# ---------------------------------------------------------------------------
# CLI options
# ---------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("pytest-api-core", "API framework options")
    group.addoption(
        "--api-env",
        action="store",
        default=None,
        help="Target environment name (maps to config/env/<name>.yaml)",
    )
    group.addoption(
        "--api-config-dir",
        action="store",
        default="config/env",
        help="Directory containing environment YAML files (default: config/env)",
    )
    group.addoption(
        "--api-html-report",
        action="store",
        default=None,
        metavar="PATH",
        help="Path for the custom HTML report (e.g. reports/report.html)",
    )
    group.addoption(
        "--api-base-url",
        action="store",
        default=None,
        help="Override base_url from config",
    )
    # Register ini options to suppress "Unknown config option" warnings
    parser.addini("api_env", help="Default environment (e.g. dev, staging, prod)", default="dev")
    parser.addini("api_config_dir", help="Directory containing env YAML files", default="config/env")
    parser.addini("api_html_report", help="Output path for the custom HTML report", default=None)


# ---------------------------------------------------------------------------
# ini options (allow pytest.ini / pyproject.toml [tool.pytest.ini_options])
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "api: mark test as an API test")

    report_path = config.getoption("--api-html-report", default=None)
    if not report_path:
        report_path = config.getini("api_html_report")
    if report_path:
        plugin = HTMLReporter(report_path)
        config.pluginmanager.register(plugin, "api-html-reporter")


# ---------------------------------------------------------------------------
# Re-export fixtures so pytest can discover them from this module
# ---------------------------------------------------------------------------

__all__ = [
    "api_config",
    "api_client",
    "api_bearer_auth",
    "api_basic_auth",
    "api_key_auth",
]
