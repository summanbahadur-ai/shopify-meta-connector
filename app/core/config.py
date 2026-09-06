from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Mapping


def _load_local_env() -> None:
    """Load a simple .env file for local/PyCharm runs only."""
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_local_env()


class ConfigurationError(RuntimeError):
    pass


def _read(source: Any, key: str) -> str | None:
    if source is None:
        return None
    value = source.get(key) if isinstance(source, Mapping) else getattr(source, key, None)
    return None if value is None else str(value)


@dataclass(frozen=True)
class Settings:
    shopify_store_domain: str
    shopify_client_id: str
    shopify_client_secret: str
    shopify_api_version: str = "2026-07"
    shopify_access_token: str | None = None

    @property
    def graphql_url(self) -> str:
        return f"https://{self.shopify_store_domain}/admin/api/{self.shopify_api_version}/graphql.json"

    @property
    def token_url(self) -> str:
        return f"https://{self.shopify_store_domain}/admin/oauth/access_token"

    @classmethod
    def from_mapping(cls, source: Any) -> "Settings":
        domain = (_read(source, "SHOPIFY_STORE_DOMAIN") or "").strip()
        client_id = (_read(source, "SHOPIFY_CLIENT_ID") or "").strip()
        client_secret = (_read(source, "SHOPIFY_CLIENT_SECRET") or "").strip()
        access_token = (_read(source, "SHOPIFY_ACCESS_TOKEN") or "").strip() or None
        version = (_read(source, "SHOPIFY_API_VERSION") or "2026-07").strip()
        domain = domain.removeprefix("https://").removeprefix("http://").rstrip("/")
        if not domain:
            raise ConfigurationError("SHOPIFY_STORE_DOMAIN is required")
        if not access_token and (not client_id or not client_secret):
            raise ConfigurationError("SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET are required for new Shopify apps")
        return cls(domain, client_id, client_secret, version, access_token)

    @classmethod
    def from_request(cls, request) -> "Settings":
        worker_env = request.scope.get("env") if request is not None else None
        if worker_env is not None:
            try:
                return cls.from_mapping(worker_env)
            except ConfigurationError:
                pass
        return cls.from_mapping(os.environ)
