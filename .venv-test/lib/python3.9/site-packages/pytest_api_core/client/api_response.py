"""
Thin wrapper around requests.Response that adds helper properties
and is consumed by the fluent assertion API.
"""
from __future__ import annotations

import json
import time
from typing import Any

import requests


class APIResponse:
    """Wraps requests.Response with additional convenience methods."""

    def __init__(self, response: requests.Response, elapsed_ms: float | None = None) -> None:
        self._response = response
        self.elapsed_ms: float = elapsed_ms if elapsed_ms is not None else (
            response.elapsed.total_seconds() * 1000 if response.elapsed else 0.0
        )

    # ------------------------------------------------------------------
    # Delegated properties
    # ------------------------------------------------------------------

    @property
    def status_code(self) -> int:
        return self._response.status_code

    @property
    def headers(self) -> requests.structures.CaseInsensitiveDict:  # type: ignore[type-arg]
        return self._response.headers

    @property
    def text(self) -> str:
        return self._response.text

    @property
    def content(self) -> bytes:
        return self._response.content

    @property
    def url(self) -> str:
        return self._response.url

    @property
    def ok(self) -> bool:
        return self._response.ok

    @property
    def request(self) -> requests.PreparedRequest:
        return self._response.request

    # ------------------------------------------------------------------
    # JSON helpers
    # ------------------------------------------------------------------

    def json(self, **kwargs: Any) -> Any:
        return self._response.json(**kwargs)

    def json_value(self, key: str, default: Any = None) -> Any:
        """Return a top-level key from the JSON body, or *default* if missing."""
        try:
            return self.json().get(key, default)
        except (ValueError, AttributeError):
            return default

    # ------------------------------------------------------------------
    # Request echo (for logging / reporting)
    # ------------------------------------------------------------------

    def request_body_text(self) -> str:
        """Return the raw request body as a string (best-effort)."""
        body = self._response.request.body
        if body is None:
            return ""
        if isinstance(body, bytes):
            try:
                parsed = json.loads(body)
                return json.dumps(parsed, indent=2)
            except (ValueError, TypeError):
                return body.decode("utf-8", errors="replace")
        return str(body)

    def response_body_text(self) -> str:
        """Return the response body pretty-printed if JSON, else raw text."""
        try:
            return json.dumps(self.json(), indent=2)
        except (ValueError, TypeError):
            return self.text

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"<APIResponse [{self.status_code}] {self.url} ({self.elapsed_ms:.1f} ms)>"

    def raise_for_status(self) -> None:
        self._response.raise_for_status()
