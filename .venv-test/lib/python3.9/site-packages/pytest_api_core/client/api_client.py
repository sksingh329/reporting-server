"""
HTTP client built on top of requests.Session.

Features
--------
- Automatic base-URL resolution
- Configurable retry with back-off (via urllib3.Retry)
- Request / response logging
- Pluggable auth strategies
- Returns APIResponse objects for use with the fluent assertion API
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pytest_api_core.client.api_response import APIResponse

log = logging.getLogger("pytest_api_core.client")


_DEFAULT_RETRY = Retry(
    total=3,
    backoff_factor=0.3,
    status_forcelist=(500, 502, 503, 504),
    allowed_methods={"GET", "OPTIONS", "HEAD"},
    raise_on_status=False,
)


class APIClient:
    """
    Session-backed HTTP client used by API tests.

    Parameters
    ----------
    base_url:
        Root URL prepended to every relative path (e.g. ``https://api.example.com/v1``).
    auth:
        An auth handler instance (BearerAuth, BasicAuth, APIKeyAuth, …) or any
        callable accepted by requests.
    timeout:
        Default timeout in seconds for every request.
    verify_ssl:
        Whether to verify TLS certificates.
    default_headers:
        Headers merged into every request.
    retry:
        urllib3 Retry config.  Pass ``None`` to disable retries.
    """

    def __init__(
        self,
        base_url: str,
        auth: Any = None,
        timeout: int | float = 30,
        verify_ssl: bool = True,
        default_headers: dict[str, str] | None = None,
        retry: Retry | None = _DEFAULT_RETRY,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verify_ssl = verify_ssl

        self._session = requests.Session()

        if auth is not None:
            self._session.auth = auth

        if default_headers:
            self._session.headers.update(default_headers)

        if retry:
            adapter = HTTPAdapter(max_retries=retry)
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)

    # ------------------------------------------------------------------
    # HTTP verbs
    # ------------------------------------------------------------------

    def get(self, path: str, **kwargs: Any) -> APIResponse:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> APIResponse:
        return self._request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> APIResponse:
        return self._request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> APIResponse:
        return self._request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> APIResponse:
        return self._request("DELETE", path, **kwargs)

    def head(self, path: str, **kwargs: Any) -> APIResponse:
        return self._request("HEAD", path, **kwargs)

    def options(self, path: str, **kwargs: Any) -> APIResponse:
        return self._request("OPTIONS", path, **kwargs)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, **kwargs: Any) -> APIResponse:
        url = self._resolve_url(path)
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", self.verify_ssl)

        log.debug("%s %s  kwargs=%s", method, url, {k: v for k, v in kwargs.items() if k != "json"})

        start = time.monotonic()
        response = self._session.request(method, url, **kwargs)
        elapsed_ms = (time.monotonic() - start) * 1000

        api_resp = APIResponse(response, elapsed_ms)
        log.debug(
            "%s %s → %s  (%.1f ms)",
            method,
            url,
            response.status_code,
            elapsed_ms,
        )
        return api_resp

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "APIClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        self._session.close()

    def __repr__(self) -> str:
        return f"<APIClient base_url={self.base_url!r}>"
