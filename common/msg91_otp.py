"""MSG91 server-side helpers — verify access token only.

Phone OTP send / retry / verify happen in the browser via the MSG91 Web SDK.
Django must never call widget sendOtp / retryOtp / verifyOtp.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Any, Dict, Optional, Tuple

import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)

MSG91_VERIFY_ACCESS_TOKEN_URL = "https://control.msg91.com/api/v5/widget/verifyAccessToken"

USED_TOKEN_CACHE_PREFIX = "msg91_used_access_token:"
USED_TOKEN_TTL_SECONDS = 3600
VERIFY_RATE_PREFIX = "msg91_verify_rate:"
VERIFY_RATE_LIMIT = 20
VERIFY_RATE_WINDOW_SECONDS = 600


def _auth_key() -> str:
    return os.getenv("MSG91_AUTH_KEY", "").strip()


def is_msg91_configured() -> bool:
    return bool(_auth_key())


def to_msg91_mobile(phone: str) -> str:
    """Digits only with country code, no '+'."""
    return "".join(ch for ch in str(phone or "") if ch.isdigit())


def mobiles_match(a: str, b: str) -> bool:
    da, db = to_msg91_mobile(a), to_msg91_mobile(b)
    if not da or not db:
        return False
    if da == db:
        return True
    # Allow 0-prefix / missing country-code mismatches for same national length
    return da.endswith(db) or db.endswith(da)


def _parse_json(response: requests.Response) -> Dict[str, Any]:
    try:
        data = response.json() if response.content else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _is_msg91_failure(response: requests.Response, data: Dict[str, Any]) -> bool:
    """MSG91 may return HTTP 200 with an error body."""
    if response.status_code != 200:
        return True
    if data.get("hasError") is True:
        return True
    type_val = str(data.get("type") or "").lower()
    if type_val == "error":
        return True
    status_val = str(data.get("status") or "").lower()
    if status_val in {"fail", "failed", "error"}:
        return True
    return False


def _decode_jwt_payload(token: str) -> Dict[str, Any]:
    try:
        parts = str(token).split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        raw = base64.urlsafe_b64decode(payload + padding)
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _extract_verified_mobile(data: Dict[str, Any], access_token: str) -> Optional[str]:
    """Pull verified mobile/identifier from MSG91 verifyAccessToken response or JWT."""
    candidates = []

    for key in ("mobile", "phone", "phone_number", "identifier", "number"):
        if data.get(key):
            candidates.append(data.get(key))

    message = data.get("message")
    if isinstance(message, dict):
        for key in ("mobile", "phone", "phone_number", "identifier", "number"):
            if message.get(key):
                candidates.append(message.get(key))
    elif isinstance(message, str):
        digits = to_msg91_mobile(message)
        if 10 <= len(digits) <= 15:
            candidates.append(digits)
        # message may itself be a JWT access token
        jwt_payload = _decode_jwt_payload(message)
        for key in ("mobile", "phone", "phone_number", "identifier", "number", "sub"):
            if jwt_payload.get(key):
                candidates.append(jwt_payload.get(key))

    nested = data.get("data")
    if isinstance(nested, dict):
        for key in ("mobile", "phone", "phone_number", "identifier", "number"):
            if nested.get(key):
                candidates.append(nested.get(key))

    jwt_payload = _decode_jwt_payload(access_token)
    for key in ("mobile", "phone", "phone_number", "identifier", "number", "sub"):
        if jwt_payload.get(key):
            candidates.append(jwt_payload.get(key))

    for value in candidates:
        mobile = to_msg91_mobile(value)
        if len(mobile) >= 10:
            return mobile
    return None


def _token_fingerprint(access_token: str) -> str:
    # Do not store the raw token; cache a short fingerprint only.
    import hashlib

    return hashlib.sha256(str(access_token).encode("utf-8")).hexdigest()[:40]


def check_verify_rate_limit(bucket: str) -> Tuple[bool, str]:
    key = f"{VERIFY_RATE_PREFIX}{bucket}"
    try:
        count = cache.get(key) or 0
        if int(count) >= VERIFY_RATE_LIMIT:
            return False, "Too many verification attempts. Please try again later."
        cache.set(key, int(count) + 1, timeout=VERIFY_RATE_WINDOW_SECONDS)
    except Exception:
        # If cache is unavailable, do not block signup.
        pass
    return True, ""


def mark_access_token_used(access_token: str) -> None:
    try:
        cache.set(
            f"{USED_TOKEN_CACHE_PREFIX}{_token_fingerprint(access_token)}",
            1,
            timeout=USED_TOKEN_TTL_SECONDS,
        )
    except Exception:
        pass


def is_access_token_used(access_token: str) -> bool:
    try:
        return bool(cache.get(f"{USED_TOKEN_CACHE_PREFIX}{_token_fingerprint(access_token)}"))
    except Exception:
        return False


def verify_access_token(access_token: str) -> Tuple[bool, str, Optional[str]]:
    """
    Call MSG91 Verify Access Token (server-side integration).

    Returns:
        (success, message, verified_mobile_digits)
    """
    auth_key = _auth_key()
    token = str(access_token or "").strip()
    if not auth_key:
        logger.error("MSG91_AUTH_KEY is not configured")
        return False, "Phone verification is unavailable. Please try again or contact sales.", None
    if not token:
        return False, "Missing MSG91 access token.", None
    if is_access_token_used(token):
        return False, "This verification token has already been used.", None

    try:
        # Prefer JSON body; also accept form-style used by MSG91 examples.
        response = requests.post(
            MSG91_VERIFY_ACCESS_TOKEN_URL,
            headers={
                "authkey": auth_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "authkey": auth_key,
                "access-token": token,
            },
            timeout=30,
        )
        data = _parse_json(response)

        # Fallback to form-encoded if JSON shape is rejected
        if _is_msg91_failure(response, data) and response.status_code in (400, 401, 415, 422):
            response = requests.post(
                MSG91_VERIFY_ACCESS_TOKEN_URL,
                headers={"authkey": auth_key, "Accept": "application/json"},
                data={"authkey": auth_key, "access-token": token},
                timeout=30,
            )
            data = _parse_json(response)

        if _is_msg91_failure(response, data):
            err = str(data.get("message") or data.get("msg") or "Invalid or expired verification token.")
            # Avoid logging secrets
            safe_err = re.sub(r"[A-Za-z0-9_-]{20,}", "[redacted]", err)[:200]
            logger.info(
                "MSG91 verifyAccessToken failed: status=%s type=%s message=%s",
                response.status_code,
                data.get("type"),
                safe_err,
            )
            return False, "Invalid or expired phone verification. Please verify OTP again.", None

        verified_mobile = _extract_verified_mobile(data, token)
        if not verified_mobile:
            logger.error("MSG91 verifyAccessToken succeeded but no mobile found in response keys=%s", list(data.keys()))
            return False, "Could not confirm verified mobile number from MSG91.", None

        return True, "Phone verified successfully.", verified_mobile
    except Exception as exc:
        logger.exception("MSG91 verifyAccessToken exception: %s", exc)
        return False, "Phone verification service unavailable. Please try again.", None
