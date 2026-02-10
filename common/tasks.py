import hashlib
import time
from django.core.mail import send_mail
from django.conf import settings
from celery import shared_task

# Dedupe: same (path + error) won't send again for this many seconds
ERROR_REPORT_DEDUPE_SECONDS = 900  # 15 minutes

# In-memory dedupe when Django cache is not configured (key -> expiry timestamp)
_error_report_sent = {}

def _error_dedupe_seen(cache_key):
    global _error_report_sent
    now = time.time()
    # Prune old entries
    _error_report_sent = {k: v for k, v in _error_report_sent.items() if v > now}
    if cache_key in _error_report_sent:
        return True
    _error_report_sent[cache_key] = now + ERROR_REPORT_DEDUPE_SECONDS
    return False


def _enrich_user_details(payload):
    """Resolve user_id to full details: name, email, organization name, phone (from payment/invoice)."""
    user = payload.get("user")
    if not isinstance(user, dict):
        return
    user_id = user.get("id") or (payload.get("context") or {}).get("user_id")
    if not user_id:
        return
    try:
        from users.models import User as UserModel
        from payments.models import PaymentTransaction

        user_id_str = str(user_id).strip()
        if len(user_id_str) != 24:
            return
        try:
            from bson import ObjectId
            uid = ObjectId(user_id_str)
        except Exception:
            return
        db_user = UserModel.objects(id=uid).first()
        if not db_user:
            return
        user["email"] = getattr(db_user, "email", None)
        user["full_name"] = getattr(db_user, "full_name", None)
        user["username"] = getattr(db_user, "username", None)
        user["role"] = str(getattr(db_user, "role", "")) if getattr(db_user, "role", None) else None
        org = getattr(db_user, "organization", None)
        if org:
            try:
                user["organization_name"] = getattr(org, "name", None) if org else None
            except Exception:
                user["organization_name"] = None
        else:
            user["organization_name"] = None
        # Phone from latest payment transaction (billing_phone)
        try:
            txn = PaymentTransaction.objects(user=db_user).order_by("-created_at").first()
            user["phone"] = getattr(txn, "billing_phone", None) if txn else None
        except Exception:
            user["phone"] = None
    except Exception:
        pass


def _format_user_section(payload):
    """Format user details: name, email, organization, phone (enriched when possible)."""
    user = payload.get("user")
    if user is None:
        return "User: (none)"
    if isinstance(user, dict):
        if not user.get("authenticated"):
            return "User: anonymous (not authenticated)"
        parts = ["User (authenticated):"]
        for label, key in [
            ("Name", "full_name"),
            ("Email", "email"),
            ("Username", "username"),
            ("Organization", "organization_name"),
            ("Phone", "phone"),
            ("Role", "role"),
            ("ID", "id"),
        ]:
            val = user.get(key)
            if val is not None and str(val).strip():
                parts.append(f"  {label}: {val}")
        return "\n".join(parts) if len(parts) > 1 else "User: " + str(user)
    return f"User: {user}"


def _format_location_section(payload):
    """Format where the error occurred (new format: location dict, or legacy: path + method)."""
    location = payload.get("location")
    if isinstance(location, dict):
        parts = [
            f"Path: {location.get('path', '')}",
            f"Full path: {location.get('full_path', '')}",
            f"Method: {location.get('method', '')}",
        ]
        if location.get("view_name"):
            parts.append(f"View/URL name: {location['view_name']}")
        if location.get("view_func"):
            parts.append(f"View function: {location['view_func']}")
        return "\n".join(parts)
    return "Path: {}\nMethod: {}".format(
        payload.get("path", ""),
        payload.get("method", "HTTP"),
    )


def _error_email_plain(payload):
    parts = [
        _format_user_section(payload),
        "",
        "Where it occurred:",
        _format_location_section(payload),
        "",
    ]
    if payload.get("handled"):
        parts.extend(["Handled: yes (caught in code, still reported)", ""])
    parts.extend([
        "Error:",
        payload.get("error", ""),
        "",
        "Traceback:",
        payload.get("traceback", ""),
    ])
    return "\n".join(parts)


def _error_email_html(payload):
    import html
    user_html = html.escape(_format_user_section(payload).replace("\n", "<br>"))
    location_html = html.escape(_format_location_section(payload).replace("\n", "<br>"))
    handled_note = "<p><em>Handled exception (caught in code, still reported)</em></p>" if payload.get("handled") else ""
    error_html = html.escape(payload.get("error", ""))
    traceback_html = "<pre style=\"background:#f1f5f9;padding:12px;overflow:auto;\">" + html.escape(payload.get("traceback", "")) + "</pre>"
    body = f"""
<p><strong>User who triggered the error</strong></p>
<p>{user_html}</p>
<p><strong>Where it occurred</strong></p>
<p>{location_html}</p>
{handled_note}
<p><strong>Error</strong></p>
<p>{error_html}</p>
<p><strong>Traceback</strong></p>
{traceback_html}
"""
    from common.email_utils import get_base_email_html
    return get_base_email_html(body, title="Application Error / Exception")


def _error_report_dedupe_key(payload):
    """Cache key for deduplication: same location + error message = same key."""
    path = (payload.get("location") or {}).get("path") or payload.get("path") or ""
    err = (payload.get("error") or "")[:300]
    raw = f"{path}|{err}"
    return "error_report:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=5, retry_kwargs={"max_retries": 3})
def notify_admin_error(self, payload):
    if not getattr(settings, "ADMIN_EMAIL", None) or not settings.ADMIN_EMAIL:
        return

    # Deduplicate: only send one email per (path, error) within the time window
    cache_key = _error_report_dedupe_key(payload)
    if _error_dedupe_seen(cache_key):
        return
    try:
        from django.core.cache import cache
        if cache.get(cache_key):
            return
        cache.set(cache_key, 1, timeout=ERROR_REPORT_DEDUPE_SECONDS)
    except Exception:
        pass

    # Enrich user with name, email, organization, phone from DB
    _enrich_user_details(payload)

    subject = "[Gosplash] Error / Exception reported"
    if payload.get("handled"):
        subject = "[Gosplash] Handled exception reported"
    body_plain = _error_email_plain(payload)
    body_html = _error_email_html(payload)

    send_mail(
        subject=subject,
        message=body_plain,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=list(settings.ADMIN_EMAIL),
        fail_silently=False,
        html_message=body_html,
    )
