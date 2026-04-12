from __future__ import annotations

from functools import lru_cache
from typing import Any

import ccxt

from app.core.exceptions import ConfigurationError


def _exchange_class(exchange_name: str):
    exchange_cls = getattr(ccxt, exchange_name, None)
    if exchange_cls is None:
        raise ConfigurationError(f"Unsupported CCXT exchange: {exchange_name}")
    return exchange_cls


@lru_cache(maxsize=16)
def get_public_client(exchange_name: str, default_type: str | None = None):
    exchange_cls = _exchange_class(exchange_name)
    config: dict[str, Any] = {"enableRateLimit": True}
    if default_type:
        config["options"] = {"defaultType": default_type}
    return exchange_cls(config)


@lru_cache(maxsize=16)
def get_private_client(
    exchange_name: str,
    api_key: str,
    secret: str,
    password: str | None = None,
    default_type: str | None = None,
):
    exchange_cls = _exchange_class(exchange_name)
    config: dict[str, Any] = {"enableRateLimit": True}
    if default_type:
        config["options"] = {"defaultType": default_type}
    config["apiKey"] = api_key
    config["secret"] = secret
    if password:
        config["password"] = password
    return exchange_cls(config)
