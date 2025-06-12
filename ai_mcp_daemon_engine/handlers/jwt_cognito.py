# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bibow"

from time import monotonic
from typing import Any, Dict

import httpx
from fastapi import HTTPException
from jose import JWTError, jwt

from .config import Config

_JWKS_CACHE: Dict[str, Any] | None = None
_JWKS_EXPIRES_AT = 0.0


def _jwks() -> Dict[str, Any]:
    global _JWKS_CACHE, _JWKS_EXPIRES_AT
    now = monotonic()
    if _JWKS_CACHE is None or now >= _JWKS_EXPIRES_AT:
        resp = httpx.get(Config.jwks_endpoint, timeout=10)
        resp.raise_for_status()
        _JWKS_CACHE = resp.json()
        _JWKS_EXPIRES_AT = now + Config.jwks_cache_ttl
    return _JWKS_CACHE


def verify_cognito_jwt(token: str) -> Dict[str, Any]:
    try:
        head = jwt.get_unverified_header(token)
        key = next(k for k in _jwks()["keys"] if k["kid"] == head["kid"])
        claims = jwt.decode(
            token,
            key,
            algorithms=[key["alg"]],
            audience=Config.cognito_app_client_id,
            issuer=Config.issuer,
        )
        return claims
    except (JWTError, StopIteration) as e:
        raise HTTPException(
            status_code=401,
            detail="Invalid Cognito JWT",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
