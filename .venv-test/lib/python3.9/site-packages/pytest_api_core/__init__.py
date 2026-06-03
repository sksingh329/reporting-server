"""
pytest-api-core: Reusable API automation framework for pytest.
Auto-registered as a pytest plugin via entry_points["pytest11"].
"""

from pytest_api_core.client.api_client import APIClient
from pytest_api_core.client.api_response import APIResponse
from pytest_api_core.assertions.response_assertions import assert_that
from pytest_api_core.auth.auth_handlers import BearerAuth, BasicAuth, APIKeyAuth, OAuth2ClientCredentials

__version__ = "1.0.0"
__all__ = [
    "APIClient",
    "APIResponse",
    "assert_that",
    "BearerAuth",
    "BasicAuth",
    "APIKeyAuth",
    "OAuth2ClientCredentials",
]
