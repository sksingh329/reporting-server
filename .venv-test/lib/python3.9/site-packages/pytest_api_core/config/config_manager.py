"""
Environment-aware configuration manager.

Resolution order (highest → lowest priority):
  1. Environment variables  (API_BASE_URL, API_TOKEN, …)
  2. ``--api-base-url`` CLI flag
  3. YAML file at ``<config_dir>/<env>.yaml``
  4. Built-in defaults

Usage
-----
    manager = ConfigManager(env="staging", config_dir="config/env")
    cfg = manager.load()
    # cfg = {"base_url": "https://staging.api.example.com", "timeout": 30, ...}
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("pytest_api_core.config")

_DEFAULTS: dict[str, Any] = {
    "base_url": "http://localhost",
    "timeout": 30,
    "verify_ssl": True,
    "headers": {},
    "retry": {
        "total": 3,
        "backoff_factor": 0.3,
        "status_forcelist": [500, 502, 503, 504],
    },
}

# Maps env-var names → config keys
_ENV_VAR_MAP: dict[str, str] = {
    "API_BASE_URL": "base_url",
    "API_TIMEOUT": "timeout",
    "API_VERIFY_SSL": "verify_ssl",
    "API_TOKEN": "_token",          # consumed by fixtures, not stored in cfg directly
}


class ConfigManager:
    """
    Loads and merges configuration for a given environment name.

    Parameters
    ----------
    env:
        Environment label (e.g. ``"dev"``, ``"staging"``).
    config_dir:
        Directory (absolute or relative to CWD) containing ``<env>.yaml`` files.
    cli_overrides:
        Extra key/value pairs from CLI options (e.g. ``--api-base-url``).
    """

    def __init__(
        self,
        env: str | None = None,
        config_dir: str | Path = "config/env",
        cli_overrides: dict[str, Any] | None = None,
    ) -> None:
        self._env = env or os.environ.get("API_ENV", "dev")
        self._config_dir = Path(config_dir)
        self._cli_overrides: dict[str, Any] = cli_overrides or {}
        self._cache: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def env(self) -> str:
        return self._env

    def load(self) -> dict[str, Any]:
        """Return the fully-resolved config dict (cached after first call)."""
        if self._cache is not None:
            return self._cache

        cfg: dict[str, Any] = dict(_DEFAULTS)

        # Layer 1: YAML file
        yaml_cfg = self._load_yaml()
        _deep_merge(cfg, yaml_cfg)

        # Layer 2: CLI overrides
        _deep_merge(cfg, {k: v for k, v in self._cli_overrides.items() if v is not None})

        # Layer 3: Environment variables
        for env_var, cfg_key in _ENV_VAR_MAP.items():
            value = os.environ.get(env_var)
            if value is not None:
                cfg[cfg_key] = self._coerce(cfg_key, value)

        log.debug("Loaded config for env=%r: %s", self._env, cfg)
        self._cache = cfg
        return cfg

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_yaml(self) -> dict[str, Any]:
        yaml_path = self._config_dir / f"{self._env}.yaml"
        if not yaml_path.exists():
            log.warning(
                "Config file not found: %s — using defaults only", yaml_path
            )
            return {}
        with yaml_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _coerce(key: str, raw: str) -> Any:
        """Coerce env-var strings to appropriate Python types."""
        if key in ("timeout",):
            try:
                return int(raw)
            except ValueError:
                return float(raw)
        if key == "verify_ssl":
            return raw.lower() not in ("0", "false", "no")
        return raw


# ------------------------------------------------------------------
# Utility
# ------------------------------------------------------------------


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    """Recursively merge *override* into *base* in-place."""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
