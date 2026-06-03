"""
Authentication strategy classes compatible with requests.auth.AuthBase.

Usage
-----
    client = APIClient(base_url, auth=BearerAuth("my-token"))
    client = APIClient(base_url, auth=BasicAuth("user", "pass"))
    client = APIClient(base_url, auth=APIKeyAuth("x-api-key", "secret"))
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests
from requests.auth import AuthBase

log = logging.getLogger("pytest_api_core.auth")


class BearerAuth(AuthBase):
    """Injects ``Authorization: Bearer <token>`` into every request."""

    def __init__(self, token: str) -> None:
        self._token = token

    def __call__(self, r: requests.PreparedRequest) -> requests.PreparedRequest:
        r.headers["Authorization"] = f"Bearer {self._token}"
        return r

    def __repr__(self) -> str:
        return f"<BearerAuth token=***{self._token[-4:]}>"


class BasicAuth(AuthBase):
    """
    HTTP Basic Authentication.
    Delegates to requests' built-in HTTPBasicAuth but subclasses AuthBase
    so it integrates cleanly with the fixture system.
    """

    def __init__(self, username: str, password: str) -> None:
        self._inner = requests.auth.HTTPBasicAuth(username, password)

    def __call__(self, r: requests.PreparedRequest) -> requests.PreparedRequest:
        return self._inner(r)

    def __repr__(self) -> str:
        return f"<BasicAuth username={self._inner.username!r}>"


class APIKeyAuth(AuthBase):
    """
    Injects an API key either as a request header or a query parameter.

    Parameters
    ----------
    name:
        Header name (e.g. ``x-api-key``) or query-parameter name.
    value:
        The API key value.
    location:
        ``"header"`` (default) or ``"query"``.
    """

    def __init__(self, name: str, value: str, location: str = "header") -> None:
        if location not in ("header", "query"):
            raise ValueError("location must be 'header' or 'query'")
        self._name = name
        self._value = value
        self._location = location

    def __call__(self, r: requests.PreparedRequest) -> requests.PreparedRequest:
        if self._location == "header":
            r.headers[self._name] = self._value
        else:
            # Append to existing query string
            from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

            parsed = urlparse(r.url or "")
            params = parse_qsl(parsed.query)
            params.append((self._name, self._value))
            r.url = urlunparse(parsed._replace(query=urlencode(params)))
        return r

    def __repr__(self) -> str:
        return f"<APIKeyAuth name={self._name!r} location={self._location!r}>"


class OAuth2ClientCredentials(AuthBase):
    """
    Fetches and caches an OAuth2 access token using the *client credentials* flow.
    Automatically refreshes when the token is within ``refresh_buffer`` seconds of expiry.

    Parameters
    ----------
    token_url:
        Full URL of the token endpoint.
    client_id:
        OAuth2 client ID.
    client_secret:
        OAuth2 client secret.
    scope:
        Space-separated list of scopes (optional).
    refresh_buffer:
        Seconds before expiry to proactively refresh (default 30).
    """

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str = "",
        refresh_buffer: int = 30,
    ) -> None:
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._refresh_buffer = refresh_buffer

        self._access_token: str | None = None
        self._expires_at: float = 0.0

    def _fetch_token(self) -> None:
        data: dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        if self._scope:
            data["scope"] = self._scope

        log.debug("Fetching OAuth2 token from %s", self._token_url)
        response = requests.post(self._token_url, data=data, timeout=15)
        response.raise_for_status()

        payload: dict[str, Any] = response.json()
        self._access_token = payload["access_token"]
        expires_in: int = payload.get("expires_in", 3600)
        self._expires_at = time.monotonic() + expires_in
        log.debug("OAuth2 token acquired, expires in %ds", expires_in)

    def _is_expired(self) -> bool:
        return time.monotonic() >= (self._expires_at - self._refresh_buffer)

    def __call__(self, r: requests.PreparedRequest) -> requests.PreparedRequest:
        if self._access_token is None or self._is_expired():
            self._fetch_token()
        r.headers["Authorization"] = f"Bearer {self._access_token}"
        return r

    def __repr__(self) -> str:
        return f"<OAuth2ClientCredentials client_id={self._client_id!r}>"
