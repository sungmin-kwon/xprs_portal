from __future__ import annotations

import hmac
import os
from pathlib import Path

from fastapi import HTTPException, Request


ACCESS_COOKIE = "xprs_kpredict_access"


def kpredict_root() -> Path | None:
    if os.getenv("KPREDICT_ENABLED", "false").lower() not in {"1", "true", "yes", "on"}:
        return None
    configured = os.getenv("KPREDICT_DATA_ROOT", "").strip()
    if not configured:
        return None
    root = Path(configured).expanduser().resolve()
    return root if (root / "manifest.json").is_file() else None


def _expected_tokens() -> tuple[str, ...]:
    return tuple(
        token
        for token in (
            os.getenv("XPRS_KPREDICT_TOKEN", "").strip(),
            os.getenv("XPRS_ADMIN_TOKEN", "").strip(),
        )
        if token
    )


def has_kpredict_access(request: Request) -> bool:
    expected_tokens = _expected_tokens()
    if not expected_tokens or kpredict_root() is None:
        return False
    supplied_tokens = tuple(
        token
        for token in (
            request.headers.get("X-XPRS-KPREDICT-Token", "").strip(),
            request.headers.get("X-XPRS-Admin-Token", "").strip(),
            request.cookies.get(ACCESS_COOKIE, "").strip(),
            request.cookies.get("xprs_admin_access", "").strip(),
        )
        if token
    )
    return any(
        hmac.compare_digest(supplied, expected)
        for supplied in supplied_tokens
        for expected in expected_tokens
    )


def require_kpredict_access(request: Request) -> Path:
    if not has_kpredict_access(request):
        # Do not disclose whether a private cohort is configured.
        raise HTTPException(status_code=404, detail="Not found")
    root = kpredict_root()
    if root is None:
        raise HTTPException(status_code=404, detail="Not found")
    return root
