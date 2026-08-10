"""Helpers for pricing geo / India detection."""
import json
import urllib.request


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.META.get("HTTP_X_REAL_IP")
    if real_ip:
        return real_ip.strip()
    return (request.META.get("REMOTE_ADDR") or "").strip()


def country_from_headers(request):
    for key in (
        "HTTP_CF_IPCOUNTRY",
        "HTTP_X_VERCEL_IP_COUNTRY",
        "HTTP_X_COUNTRY_CODE",
        "HTTP_CLOUDFRONT_VIEWER_COUNTRY",
    ):
        code = (request.META.get(key) or "").strip().upper()
        if code and code not in ("XX", "T1", "UNKNOWN"):
            return code
    return None


def is_private_ip(ip):
    if not ip:
        return True
    value = ip.strip().lower()
    if value in ("127.0.0.1", "::1", "localhost"):
        return True
    if value.startswith("10.") or value.startswith("192.168.") or value.startswith("fc") or value.startswith("fd"):
        return True
    if value.startswith("172."):
        try:
            second = int(value.split(".")[1])
            if 16 <= second <= 31:
                return True
        except (IndexError, ValueError):
            pass
    return False


def country_from_ip_lookup(ip):
    """Resolve country for an IP. Private/local IPs use the server's public egress IP."""
    try:
        if is_private_ip(ip):
            url = "http://ip-api.com/json/?fields=status,countryCode"
        else:
            url = f"http://ip-api.com/json/{ip}?fields=status,countryCode"
        with urllib.request.urlopen(url, timeout=2.5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if payload.get("status") == "success" and payload.get("countryCode"):
            return str(payload["countryCode"]).upper()
    except Exception:
        return None
    return None


def detect_request_country(request):
    """
    Return (country_code, source, ip).
    country_code may be None when detection fails.
    """
    ip = client_ip(request)
    country = country_from_headers(request)
    if country:
        return country, "header", ip
    country = country_from_ip_lookup(ip)
    if country:
        return country, "ip", ip
    return None, None, ip


def is_india_request(request):
    country, _source, _ip = detect_request_country(request)
    return country == "IN"
