import pytest
from pytest_api_core import APIClient, BearerAuth

from settings import load_test_settings


def pytest_addoption(parser):
    parser.addoption(
        "--env",
        default="prod",
        help="Target environment section from tests/test-config.ini (default: prod)",
    )


@pytest.fixture(scope="session")
def test_settings(request):
    env = request.config.getoption("--env")
    return load_test_settings(env)


@pytest.fixture(scope="session")
def api_client(test_settings):
    auth = BearerAuth(test_settings.api_token) if test_settings.api_token else None
    with APIClient(
        base_url=test_settings.base_url,
        auth=auth,
        timeout=test_settings.timeout,
        verify_ssl=test_settings.verify_ssl,
    ) as client:
        yield client
