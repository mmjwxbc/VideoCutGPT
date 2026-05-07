from __future__ import annotations

import base64
import json
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import settings


class AccessIdentity(BaseModel):
    access_user_id: str
    email: str = ""
    name: str = ""
    raw_claims: dict[str, Any] = Field(default_factory=dict)


def _decode_access_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("invalid JWT format")
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    decoded = base64.urlsafe_b64decode(f"{payload}{padding}")
    parsed = json.loads(decoded.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("invalid JWT payload")
    return parsed


def _claim_as_string(claims: dict[str, Any], key: str) -> str:
    value = claims.get(key)
    return value.strip() if isinstance(value, str) else ""


def _resolve_user_id(claims: dict[str, Any], fallback_email: str) -> str:
    for key in ("user_uuid", "sub", "email"):
        value = _claim_as_string(claims, key)
        if value:
            return value
    return fallback_email.strip()


async def get_current_access_identity(
    cf_access_jwt_assertion: Annotated[str | None, Header(alias="Cf-Access-Jwt-Assertion")] = None,
    cf_access_authenticated_user_email: Annotated[
        str | None,
        Header(alias="Cf-Access-Authenticated-User-Email"),
    ] = None,
) -> AccessIdentity:
    if not settings.cloudflare_access_enabled:
        return AccessIdentity(
            access_user_id=settings.dev_access_user_id,
            email=settings.dev_access_user_email,
            name=settings.dev_access_user_name,
        )

    claims: dict[str, Any] = {}
    if cf_access_jwt_assertion:
        try:
            claims = _decode_access_jwt_payload(cf_access_jwt_assertion)
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的 Cloudflare Access JWT",
            ) from exc

    email = _claim_as_string(claims, "email") or (cf_access_authenticated_user_email or "").strip()
    access_user_id = _resolve_user_id(claims, email)
    if not access_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Cloudflare Access 用户身份",
        )

    name = _claim_as_string(claims, "name") or _claim_as_string(claims, "common_name") or email
    return AccessIdentity(
        access_user_id=access_user_id,
        email=email,
        name=name,
        raw_claims=claims,
    )


CurrentAccessIdentity = Annotated[AccessIdentity, Depends(get_current_access_identity)]
