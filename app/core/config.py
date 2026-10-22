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


@dataclass(frozen=True, repr=False)
class WhatChimpSettings:
    api_token: str
    phone_number_id: str
    inbound_api_key: str
    base_url: str = "https://app.whatchimp.com/api/v1"

    @classmethod
    def from_request(cls, request):
        from urllib.parse import urlsplit
        worker = request.scope.get("env")
        def read(key, default=""):
            return (_read(worker, key) or os.environ.get(key) or default).strip()
        token = read("WHATCHIMP_API_TOKEN")
        phone_id = read("WHATCHIMP_PHONE_NUMBER_ID")
        key = read("WHATCHIMP_INBOUND_API_KEY")
        base = read("WHATCHIMP_API_BASE_URL", "https://app.whatchimp.com/api/v1").rstrip("/")
        parts = urlsplit(base)
        if not token or not phone_id.isascii() or not phone_id.isdigit() or not key:
            raise ConfigurationError("WhatChimp configuration is incomplete")
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ConfigurationError("WhatChimp base URL is invalid")
        return cls(token, phone_id, key, base)
