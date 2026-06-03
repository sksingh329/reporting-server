"""
Fluent (chainable) response assertion API.

Usage
-----
    from pytest_api_core.assertions import assert_that

    assert_that(response).status_is(200)
    assert_that(response).status_is(200).has_key("id").json_path("$.name").equals("Alice")
    assert_that(response).content_type_contains("application/json")
    assert_that(response).response_time_under(500)   # ms

Every assertion method returns *self* so calls can be chained freely.
A clear AssertionError with context is raised on failure.
"""
from __future__ import annotations

import json
import re
from typing import Any

from pytest_api_core.client.api_response import APIResponse


class ResponseAssertions:
    """Chainable assertion wrapper for APIResponse objects."""

    def __init__(self, response: APIResponse) -> None:
        self._response = response
        # jsonpath-ng is optional; fall back to simple key lookup if absent
        self._json_path_value: Any = _UNSET

    # ------------------------------------------------------------------
    # Status code
    # ------------------------------------------------------------------

    def status_is(self, expected: int) -> "ResponseAssertions":
        """Assert the HTTP status code equals *expected*."""
        actual = self._response.status_code
        if actual != expected:
            raise AssertionError(
                f"Expected status {expected}, got {actual}.\n"
                f"  URL: {self._response.url}\n"
                f"  Body: {self._response.response_body_text()[:500]}"
            )
        return self

    def status_in(self, *expected: int) -> "ResponseAssertions":
        """Assert the status code is one of *expected*."""
        actual = self._response.status_code
        if actual not in expected:
            raise AssertionError(
                f"Expected status in {expected}, got {actual}.\n"
                f"  URL: {self._response.url}"
            )
        return self

    def is_success(self) -> "ResponseAssertions":
        """Assert 2xx status code."""
        actual = self._response.status_code
        if not (200 <= actual < 300):
            raise AssertionError(
                f"Expected 2xx status, got {actual}.\n"
                f"  URL: {self._response.url}\n"
                f"  Body: {self._response.response_body_text()[:500]}"
            )
        return self

    def is_client_error(self) -> "ResponseAssertions":
        """Assert 4xx status code."""
        actual = self._response.status_code
        if not (400 <= actual < 500):
            raise AssertionError(f"Expected 4xx status, got {actual}.")
        return self

    def is_server_error(self) -> "ResponseAssertions":
        """Assert 5xx status code."""
        actual = self._response.status_code
        if not (500 <= actual < 600):
            raise AssertionError(f"Expected 5xx status, got {actual}.")
        return self

    # ------------------------------------------------------------------
    # Headers
    # ------------------------------------------------------------------

    def has_header(self, name: str) -> "ResponseAssertions":
        """Assert a response header with *name* is present (case-insensitive)."""
        if name.lower() not in {k.lower() for k in self._response.headers}:
            raise AssertionError(
                f"Expected header '{name}' to be present.\n"
                f"  Headers: {dict(self._response.headers)}"
            )
        return self

    def header_equals(self, name: str, expected: str) -> "ResponseAssertions":
        """Assert header *name* equals *expected* (case-insensitive name match)."""
        actual = self._response.headers.get(name)
        if actual != expected:
            raise AssertionError(
                f"Expected header '{name}' = {expected!r}, got {actual!r}."
            )
        return self

    def content_type_contains(self, fragment: str) -> "ResponseAssertions":
        """Assert the Content-Type header contains *fragment*."""
        ct = self._response.headers.get("Content-Type", "")
        if fragment.lower() not in ct.lower():
            raise AssertionError(
                f"Expected Content-Type to contain {fragment!r}, got {ct!r}."
            )
        return self

    # ------------------------------------------------------------------
    # JSON body — top-level keys
    # ------------------------------------------------------------------

    def has_key(self, key: str) -> "ResponseAssertions":
        """Assert the JSON body contains *key* at the top level."""
        body = self._json_body()
        if not isinstance(body, dict) or key not in body:
            raise AssertionError(
                f"Expected JSON key '{key}' to be present.\n"
                f"  Body keys: {list(body.keys()) if isinstance(body, dict) else body}"
            )
        return self

    def key_equals(self, key: str, expected: Any) -> "ResponseAssertions":
        """Assert top-level JSON key *key* equals *expected*."""
        body = self._json_body()
        if not isinstance(body, dict):
            raise AssertionError(f"Response body is not a JSON object: {body!r}")
        actual = body.get(key, _UNSET)
        if actual is _UNSET:
            raise AssertionError(f"Key '{key}' not found in response body.")
        if actual != expected:
            raise AssertionError(
                f"Expected body['{key}'] = {expected!r}, got {actual!r}."
            )
        return self

    def body_contains(self, text: str) -> "ResponseAssertions":
        """Assert the raw response text contains *text*."""
        if text not in self._response.text:
            raise AssertionError(
                f"Expected response body to contain {text!r}.\n"
                f"  Body (first 300 chars): {self._response.text[:300]}"
            )
        return self

    def is_json_list(self) -> "ResponseAssertions":
        """Assert the JSON body is an array."""
        body = self._json_body()
        if not isinstance(body, list):
            raise AssertionError(f"Expected JSON array, got {type(body).__name__}.")
        return self

    def list_length(self, expected: int) -> "ResponseAssertions":
        """Assert the JSON array body has exactly *expected* items."""
        body = self._json_body()
        if not isinstance(body, list):
            raise AssertionError(f"Expected JSON array, got {type(body).__name__}.")
        if len(body) != expected:
            raise AssertionError(
                f"Expected JSON list length {expected}, got {len(body)}."
            )
        return self

    def list_length_gte(self, minimum: int) -> "ResponseAssertions":
        """Assert the JSON array length is at least *minimum*."""
        body = self._json_body()
        if not isinstance(body, list) or len(body) < minimum:
            raise AssertionError(
                f"Expected JSON list length >= {minimum}, got {len(body) if isinstance(body, list) else 'non-list'}."
            )
        return self

    # ------------------------------------------------------------------
    # JSONPath navigation (simple dot-notation; no external lib required)
    # ------------------------------------------------------------------

    def json_path(self, path: str) -> "ResponseAssertions":
        """
        Navigate to a value in the JSON body using a simple path expression.

        Supported syntax:
          ``$.key``            — top-level key
          ``$.key.nested``     — nested key
          ``$.items[0].id``    — array index
          ``$[0].id``          — root is array

        The extracted value is stored for the following ``.equals()`` /
        ``.matches()`` call.
        """
        body = self._json_body()
        self._json_path_value = _resolve_path(body, path)
        return self

    def equals(self, expected: Any) -> "ResponseAssertions":
        """Assert the value from the last ``.json_path()`` call equals *expected*."""
        if self._json_path_value is _UNSET:
            raise RuntimeError("Call .json_path() before .equals()")
        actual = self._json_path_value
        self._json_path_value = _UNSET
        if actual != expected:
            raise AssertionError(f"Expected {expected!r}, got {actual!r}.")
        return self

    def matches(self, pattern: str) -> "ResponseAssertions":
        """Assert the value from the last ``.json_path()`` call matches regex *pattern*."""
        if self._json_path_value is _UNSET:
            raise RuntimeError("Call .json_path() before .matches()")
        actual = str(self._json_path_value)
        self._json_path_value = _UNSET
        if not re.search(pattern, actual):
            raise AssertionError(
                f"Expected value to match /{pattern}/, got {actual!r}."
            )
        return self

    def is_not_none(self) -> "ResponseAssertions":
        """Assert the value from the last ``.json_path()`` call is not None."""
        if self._json_path_value is _UNSET:
            raise RuntimeError("Call .json_path() before .is_not_none()")
        actual = self._json_path_value
        self._json_path_value = _UNSET
        if actual is None:
            raise AssertionError("Expected value to be non-null.")
        return self

    # ------------------------------------------------------------------
    # Performance
    # ------------------------------------------------------------------

    def response_time_under(self, max_ms: float) -> "ResponseAssertions":
        """Assert the response time is under *max_ms* milliseconds."""
        actual = self._response.elapsed_ms
        if actual >= max_ms:
            raise AssertionError(
                f"Expected response time < {max_ms}ms, got {actual:.1f}ms.\n"
                f"  URL: {self._response.url}"
            )
        return self

    # ------------------------------------------------------------------
    # Schema validation (uses jsonschema if available)
    # ------------------------------------------------------------------

    def matches_schema(self, schema: dict[str, Any]) -> "ResponseAssertions":
        """Assert the JSON body conforms to the given JSON Schema."""
        try:
            import jsonschema

            jsonschema.validate(instance=self._json_body(), schema=schema)
        except ImportError:
            raise ImportError(
                "jsonschema is required for schema validation: pip install jsonschema"
            )
        except jsonschema.ValidationError as exc:
            raise AssertionError(f"Schema validation failed: {exc.message}") from exc
        return self

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _json_body(self) -> Any:
        try:
            return self._response.json()
        except (ValueError, TypeError) as exc:
            raise AssertionError(
                f"Response body is not valid JSON.\n"
                f"  Status: {self._response.status_code}\n"
                f"  Body: {self._response.text[:200]}"
            ) from exc


# ---------------------------------------------------------------------------
# Sentinel & helpers
# ---------------------------------------------------------------------------


class _Unset:
    """Sentinel for unset json_path value."""
    def __repr__(self) -> str:
        return "<UNSET>"


_UNSET = _Unset()


def _resolve_path(data: Any, path: str) -> Any:
    """Resolve a simple ``$.key.nested[0]`` path against *data*."""
    # Strip leading $
    path = path.lstrip("$")
    # Tokenise on "." and "[N]"
    tokens: list[str | int] = []
    for segment in re.split(r"\.|\[(\d+)\]", path):
        if segment is None or segment == "":
            continue
        try:
            tokens.append(int(segment))
        except ValueError:
            tokens.append(segment)

    current = data
    for token in tokens:
        if current is None:
            raise AssertionError(f"Path traversal failed at token {token!r}: value is null.")
        try:
            current = current[token]
        except (KeyError, IndexError, TypeError) as exc:
            raise AssertionError(
                f"Path token {token!r} not found in {type(current).__name__}: {current!r}"
            ) from exc
    return current


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def assert_that(response: APIResponse) -> ResponseAssertions:
    """Entry-point for the fluent assertion chain."""
    return ResponseAssertions(response)
