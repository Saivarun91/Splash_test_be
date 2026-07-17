from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.utils.timezone import is_naive
import json
from mongoengine.errors import NotUniqueError
from .models import User, Role, PendingSignup
from django.contrib.auth.hashers import make_password, check_password
import jwt
import datetime
from datetime import timedelta
from django.conf import settings
import secrets
from common.middleware import authenticate
from common.email_utils import send_registration_email, send_registration_admin_email, send_password_reset_email, generate_random_password
from common.email_utils import generate_otp, send_email_otp
from common.msg91_otp import (
    verify_access_token as msg91_verify_access_token,
    mark_access_token_used,
    check_verify_rate_limit,
    mobiles_match,
    to_msg91_mobile,
)
from plans.pricing_helpers import resolve_signup_credits

SECRET_KEY = settings.SECRET_KEY
OTP_EXPIRY_MINUTES = 10
OTP_RESEND_COOLDOWN_SECONDS = 120


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _is_otp_expired(expires_at) -> bool:
    if not expires_at:
        return True
    expiry = expires_at
    now = datetime.datetime.utcnow()
    if not is_naive(expiry):
        expiry = expiry.replace(tzinfo=None)
    return expiry < now


def _seconds_until_resend_allowed(sent_at) -> int:
    if not sent_at:
        return 0
    sent = sent_at
    if not is_naive(sent):
        sent = sent.replace(tzinfo=None)
    elapsed = (datetime.datetime.utcnow() - sent).total_seconds()
    remaining = OTP_RESEND_COOLDOWN_SECONDS - int(elapsed)
    return max(0, remaining)


def _phone_taken(phone_e164: str, exclude_email: str = None) -> bool:
    if not phone_e164:
        return False
    if User.objects(phone_number=phone_e164).first():
        return True
    pending_q = PendingSignup.objects(phone_e164=phone_e164)
    if exclude_email:
        pending_q = pending_q.filter(email__ne=_normalize_email(exclude_email))
    return bool(pending_q.first())


def _user_payload(user, token):
    organization_data = None
    organization_id = None
    if user.organization:
        try:
            org = user.organization
            organization_id = str(org.id)
            organization_data = {"id": organization_id, "name": getattr(org, "name", None)}
        except Exception:
            organization_id = str(user.organization)
            organization_data = {"id": organization_id}

    return {
        "message": "Account created successfully",
        "token": token,
        "user": {
            "id": str(user.id),
            "slug": user.slug if hasattr(user, "slug") and user.slug else None,
            "email": user.email,
            "preferred_language": getattr(user, "preferred_language", "en") or "en",
            "role": user.role.value,
            "full_name": user.full_name,
            "username": user.username,
            "phone_number": getattr(user, "phone_number", None),
            "organization": organization_data,
            "organization_id": organization_id,
            "organization_role": user.organization_role or None,
            "profile_completed": user.profile_completed,
        },
    }


def _pending_status_payload(pending: PendingSignup, **extra):
    email_resend_in = _seconds_until_resend_allowed(pending.email_otp_sent_at)
    phone_resend_in = _seconds_until_resend_allowed(pending.phone_otp_sent_at)
    return {
        "email": pending.email,
        "phone_e164": pending.phone_e164,
        "is_email_verified": bool(pending.is_email_verified),
        "is_phone_verified": bool(pending.is_phone_verified),
        "email_resend_available_in": email_resend_in,
        "phone_resend_available_in": phone_resend_in,
        "can_complete_signup": bool(pending.is_email_verified and pending.is_phone_verified),
        **extra,
    }


# Utility: Generate JWT with role & sub_role
def generate_jwt(user):
    payload = {
        "id": str(user.id),
        "email": user.email,
        "role": user.role.value,

        "exp": datetime.datetime.utcnow() + timedelta(days=1),
        "iat": datetime.datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def generate_refresh_jwt(user):
    """Generate a longer-lived JWT used only for obtaining new access tokens."""
    payload = {
        "id": str(user.id),
        "type": "refresh",
        "exp": datetime.datetime.utcnow() + timedelta(days=7),
        "iat": datetime.datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


# =====================
# JWT Token endpoints (for admin frontend: access + refresh)
# =====================
@api_view(['POST'])
@csrf_exempt
def token_obtain_pair(request):
    """POST with { email, password } -> { access, refresh }."""
    try:
        data = json.loads(request.body)
        email = data.get("email")
        password = data.get("password")
        if not email or not password:
            return JsonResponse({"error": "Email and password required"}, status=400)
        user = User.objects(email=email).first()
        if not user or not check_password(password, user.password):
            return JsonResponse({"error": "Invalid credentials"}, status=401)
        access = generate_jwt(user)
        refresh = generate_refresh_jwt(user)
        return JsonResponse({"access": access, "refresh": refresh}, status=200)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@api_view(['POST'])
@csrf_exempt
def token_refresh(request):
    """POST with { refresh } -> { access, refresh }."""
    try:
        data = json.loads(request.body)
        refresh_token = data.get("refresh")
        if not refresh_token:
            return JsonResponse({"error": "Refresh token required"}, status=400)
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "refresh":
            return JsonResponse({"error": "Invalid refresh token"}, status=401)
        user_id = payload.get("id")
        if not user_id:
            return JsonResponse({"error": "Invalid refresh token"}, status=401)
        user = User.objects(id=user_id).first()
        if not user:
            return JsonResponse({"error": "User not found"}, status=401)
        access = generate_jwt(user)
        refresh = generate_refresh_jwt(user)
        return JsonResponse({"access": access, "refresh": refresh}, status=200)
    except jwt.ExpiredSignatureError:
        return JsonResponse({"error": "Refresh token expired"}, status=401)
    except jwt.InvalidTokenError:
        return JsonResponse({"error": "Invalid refresh token"}, status=401)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# =====================
# User Registration (PendingSignup + dual OTP)
# =====================
@api_view(['POST'])
@csrf_exempt
def register_user(request):
    try:
        data = json.loads(request.body)
        email = _normalize_email(data.get("email"))
        password = data.get("password")
        full_name = (data.get("full_name") or "").strip()
        username = (data.get("username") or "").strip()
        phone_e164 = (data.get("phone_e164") or data.get("phone_number") or "").strip()
        phone_country_code = (data.get("phone_country_code") or "").strip()
        phone_national = (data.get("phone_national") or "").strip()
        signup_source = data.get("signup_source")

        if not email or not password:
            return Response({"error": "Email and password required"}, status=400)
        if not full_name or not username:
            return Response({"error": "Full name and username are required"}, status=400)
        if not phone_e164 or not phone_e164.startswith("+") or len(phone_e164) < 8:
            return Response({"error": "Valid mobile number with country code is required"}, status=400)
        if len(password) < 8:
            return Response({"error": "Password must be at least 8 characters"}, status=400)

        existing_user = User.objects(email=email).first()
        if existing_user and existing_user.is_email_verified:
            return Response(
                {"error": "An account with this email already exists. Please log in instead."},
                status=400,
            )
        if existing_user and not existing_user.is_email_verified:
            # Legacy unverified User rows — remove so PendingSignup owns the flow
            existing_user.delete()

        username_owner = User.objects(username=username).first()
        if username_owner:
            return Response(
                {"error": "Username already taken. Please choose a different username."},
                status=400,
            )

        if _phone_taken(phone_e164, exclude_email=email):
            return Response(
                {"error": "This mobile number is already registered. Please use a different number or log in."},
                status=400,
            )

        pending = PendingSignup.objects(email=email).first()
        hashed_pw = make_password(password)
        phone_changed = False

        if pending:
            phone_changed = (pending.phone_e164 or "") != phone_e164
            # Preserve email verification only; password/phone/details can change
            keep_email_verified = bool(pending.is_email_verified)
            pending.password = hashed_pw
            pending.full_name = full_name
            pending.username = username
            pending.phone_e164 = phone_e164
            pending.phone_country_code = phone_country_code
            pending.phone_national = phone_national
            pending.signup_source = signup_source
            pending.is_email_verified = keep_email_verified
            if phone_changed:
                pending.is_phone_verified = False
                pending.phone_otp = None
                pending.phone_otp_expires_at = None
                pending.phone_otp_sent_at = None
                pending.msg91_req_id = None
            if not keep_email_verified:
                pending.email_otp = None
                pending.email_otp_expires_at = None
                pending.email_otp_sent_at = None
        else:
            # Clear any other pending with same phone
            PendingSignup.objects(phone_e164=phone_e164).delete()
            pending = PendingSignup(
                email=email,
                password=hashed_pw,
                full_name=full_name,
                username=username,
                phone_e164=phone_e164,
                phone_country_code=phone_country_code,
                phone_national=phone_national,
                signup_source=signup_source,
                is_email_verified=False,
                is_phone_verified=False,
            )

        email_sent = True
        now = datetime.datetime.utcnow()

        if not pending.is_email_verified:
            otp = generate_otp()
            pending.email_otp = otp
            pending.email_otp_expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)
            pending.email_otp_sent_at = now
            try:
                send_email_otp(pending.email, otp, pending.full_name or pending.username)
            except Exception as email_error:
                email_sent = False
                print(f"Failed to send OTP email to {pending.email}: {email_error}")

        # Phone OTP is sent in the browser via MSG91 Web SDK (CAPTCHA).
        pending.save()

        if not email_sent and not pending.is_email_verified:
            return Response(
                {
                    **_pending_status_payload(
                        pending,
                        message="Failed to send email OTP. Please try again.",
                        email_sent=False,
                        phone_sent=False,
                        phone_via_sdk=True,
                    ),
                },
                status=400,
            )

        return JsonResponse(
            {
                **_pending_status_payload(
                    pending,
                    message=(
                        "Email OTP sent. Verify phone with the SMS OTP from MSG91."
                        if not pending.is_email_verified
                        else "Email already verified. Verify phone with the SMS OTP from MSG91."
                    ),
                    email_sent=True,
                    phone_sent=False,
                    phone_via_sdk=True,
                ),
            },
            status=201,
        )

    except NotUniqueError:
        return Response({"error": "Email, username, or phone already exists"}, status=400)
    except Exception as e:
        print("REGISTER USER ERROR:", e)
        return JsonResponse({"error": "Registration failed. Please try again."}, status=500)


@api_view(['POST'])
@csrf_exempt
def verify_email_otp(request):
    """Verify email OTP for PendingSignup (does not create the account yet)."""
    try:
        data = json.loads(request.body)
        email = _normalize_email(data.get("email"))
        otp = (data.get("otp") or "").strip()

        if not email or not otp:
            return Response({"error": "Email and OTP required"}, status=400)

        pending = PendingSignup.objects(email=email).first()
        if not pending:
            # Legacy fallback for old unverified User records
            user = User.objects(email=email).first()
            if not user:
                return Response({"error": "Signup session not found. Please start signup again."}, status=404)
            if user.is_email_verified:
                return Response({"message": "Email already verified", "is_email_verified": True}, status=200)
            if user.email_otp != otp:
                return Response({"error": "Invalid OTP"}, status=400)
            if _is_otp_expired(user.email_otp_expires_at):
                return Response({"error": "OTP expired"}, status=400)
            user.is_email_verified = True
            user.email_otp = None
            user.email_otp_expires_at = None
            user.save()
            return Response({"message": "Email verified successfully", "is_email_verified": True}, status=200)

        if pending.is_email_verified:
            return Response(
                {
                    **_pending_status_payload(pending, message="Email already verified"),
                },
                status=200,
            )

        if pending.email_otp != otp:
            return Response({"error": "Invalid OTP"}, status=400)
        if _is_otp_expired(pending.email_otp_expires_at):
            return Response({"error": "OTP expired"}, status=400)

        pending.is_email_verified = True
        pending.email_otp = None
        pending.email_otp_expires_at = None
        pending.save()

        return Response(
            {
                **_pending_status_payload(pending, message="Email verified successfully"),
            },
            status=200,
        )

    except Exception as e:
        print("VERIFY EMAIL OTP ERROR:", str(e))
        return Response({"error": "Failed to verify email OTP. Please try again."}, status=500)


@api_view(['POST'])
@csrf_exempt
def verify_phone_otp(request):
    """
    Mark phone verified only after MSG91 server-side access-token validation.

    Body: { email, msg91_access_token, mobile? }
    Do not trust any frontend phone_verified flag.
    """
    try:
        data = json.loads(request.body)
        email = _normalize_email(data.get("email"))
        access_token = (data.get("msg91_access_token") or data.get("access_token") or "").strip()
        submitted_mobile = (
            data.get("mobile")
            or data.get("phone_e164")
            or data.get("phone_number")
            or ""
        ).strip()

        if not email:
            return Response({"error": "Email is required", "success": False}, status=400)
        if not access_token:
            return Response({"error": "Missing MSG91 access token", "success": False}, status=400)

        rate_ok, rate_msg = check_verify_rate_limit(f"email:{email}")
        if not rate_ok:
            return Response({"error": rate_msg, "success": False}, status=429)

        pending = PendingSignup.objects(email=email).first()
        if not pending:
            return Response(
                {"error": "Signup session not found. Please start signup again.", "success": False},
                status=404,
            )

        if pending.is_phone_verified:
            return Response(
                {**_pending_status_payload(pending, message="Phone already verified", success=True)},
                status=200,
            )

        expected_mobile = submitted_mobile or pending.phone_e164
        ok, message, verified_mobile = msg91_verify_access_token(access_token)
        if not ok:
            return Response({"error": message, "success": False}, status=400)

        if not mobiles_match(verified_mobile, expected_mobile):
            return Response(
                {
                    "error": "Verified phone number does not match the signup number.",
                    "success": False,
                },
                status=400,
            )

        if not mobiles_match(verified_mobile, pending.phone_e164):
            return Response(
                {
                    "error": "Verified phone number does not match this signup session.",
                    "success": False,
                },
                status=400,
            )

        mark_access_token_used(access_token)
        pending.is_phone_verified = True
        pending.phone_otp = None
        pending.phone_otp_expires_at = None
        pending.msg91_req_id = None
        pending.save()

        return Response(
            {
                **_pending_status_payload(pending, message="Phone verified successfully", success=True),
            },
            status=200,
        )
    except Exception as e:
        print("VERIFY PHONE ACCESS TOKEN ERROR:", str(e))
        return Response({"error": "Failed to verify phone. Please try again.", "success": False}, status=500)


@api_view(['POST'])
@csrf_exempt
def resend_email_otp(request):
    """Resend email OTP for PendingSignup with 2-minute cooldown."""
    try:
        data = json.loads(request.body)
        email = _normalize_email(data.get("email"))
        if not email:
            return Response({"error": "Email is required"}, status=400)

        pending = PendingSignup.objects(email=email).first()
        if not pending:
            return Response({
                "message": "If the email exists, an OTP has been sent."
            }, status=200)

        if pending.is_email_verified:
            return Response({"error": "Email is already verified"}, status=400)

        wait = _seconds_until_resend_allowed(pending.email_otp_sent_at)
        if wait > 0:
            return Response(
                {
                    "error": f"Please wait {wait} seconds before resending email OTP.",
                    "email_resend_available_in": wait,
                },
                status=400,
            )

        otp = generate_otp()
        now = datetime.datetime.utcnow()
        pending.email_otp = otp
        pending.email_otp_expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)
        pending.email_otp_sent_at = now
        pending.save()

        try:
            send_email_otp(pending.email, otp, pending.full_name or pending.username)
        except Exception as e:
            print(f"Failed to send OTP email: {e}")
            return Response({"error": "Failed to send OTP email. Please try again later."}, status=500)

        return Response({
            **_pending_status_payload(pending, message="OTP has been resent to your email.", success=True),
        }, status=200)

    except Exception as e:
        print("RESEND EMAIL OTP ERROR:", str(e))
        return Response({"error": str(e)}, status=500)


@api_view(['POST'])
@csrf_exempt
def resend_phone_otp(request):
    """Phone resend is handled by MSG91 Web SDK in the browser — not Django."""
    return Response(
        {
            "success": False,
            "error": "Phone OTP resend is handled in the browser via MSG91. Use Resend on the signup page.",
        },
        status=410,
    )


@api_view(['POST'])
@csrf_exempt
def complete_phone_signup(request):
    """
    Verify MSG91 access token server-side, confirm mobile match, mark phone verified.
    If email is already verified on the pending signup, create the user and log in.
    """
    try:
        data = json.loads(request.body)
        email = _normalize_email(data.get("email"))
        access_token = (data.get("msg91_access_token") or data.get("access_token") or "").strip()
        mobile = (data.get("mobile") or data.get("phone_e164") or "").strip()
        full_name = (data.get("name") or data.get("full_name") or "").strip()
        password = data.get("password")

        if not email or not access_token:
            return Response(
                {"error": "Email and msg91_access_token are required", "success": False},
                status=400,
            )

        rate_ok, rate_msg = check_verify_rate_limit(f"complete:{email}")
        if not rate_ok:
            return Response({"error": rate_msg, "success": False}, status=429)

        pending = PendingSignup.objects(email=email).first()
        if not pending:
            return Response(
                {"error": "Signup session not found. Please start signup again.", "success": False},
                status=404,
            )

        # Optional password refresh if client resubmits signup data
        if password and len(str(password)) >= 8:
            pending.password = make_password(password)
        if full_name:
            pending.full_name = full_name
        if mobile:
            normalized = mobile if str(mobile).startswith("+") else f"+{to_msg91_mobile(mobile)}"
            if _phone_taken(normalized, exclude_email=email):
                return Response(
                    {"error": "This mobile number is already registered.", "success": False},
                    status=400,
                )
            pending.phone_e164 = normalized

        expected = mobile or pending.phone_e164
        ok, message, verified_mobile = msg91_verify_access_token(access_token)
        if not ok:
            status = 503 if "unavailable" in message.lower() else 400
            return Response({"error": message, "success": False}, status=status)

        if not mobiles_match(verified_mobile, expected) or not mobiles_match(verified_mobile, pending.phone_e164):
            return Response(
                {"error": "Verified phone number does not match the signup number.", "success": False},
                status=400,
            )

        mark_access_token_used(access_token)
        pending.is_phone_verified = True
        pending.phone_otp = None
        pending.msg91_req_id = None
        pending.save()

        if not pending.is_email_verified:
            return Response(
                {
                    **_pending_status_payload(
                        pending,
                        message="Phone verified. Please verify your email OTP to complete signup.",
                        success=True,
                    ),
                },
                status=200,
            )

        # Both verified → create user (same as complete_signup)
        if User.objects(email=pending.email).first():
            pending.delete()
            return Response(
                {"error": "An account with this email already exists. Please log in instead.", "success": False},
                status=400,
            )
        if User.objects(username=pending.username).first():
            return Response(
                {"error": "Username already taken. Please start signup again.", "success": False},
                status=400,
            )
        if User.objects(phone_number=pending.phone_e164).first():
            return Response(
                {"error": "This mobile number is already registered.", "success": False},
                status=400,
            )

        user = User(
            email=pending.email,
            password=pending.password,
            full_name=pending.full_name,
            username=pending.username,
            phone_number=pending.phone_e164,
            credit_balance=resolve_signup_credits(pending.signup_source),
            profile_completed=True,
            is_email_verified=True,
            is_phone_verified=True,
            role=Role.USER,
        )
        user.save()
        pending.delete()

        try:
            send_registration_email(user.email, user.full_name or user.username)
        except Exception as welcome_error:
            print(f"Failed to send welcome email to {user.email}: {welcome_error}")

        try:
            send_registration_admin_email(
                user.email,
                user_name=user.full_name,
                user_username=user.username,
            )
        except Exception:
            pass

        token = generate_jwt(user)
        return Response({**_user_payload(user, token), "success": True}, status=200)

    except NotUniqueError:
        return Response({"error": "Email, username, or phone already exists", "success": False}, status=400)
    except Exception as e:
        print("COMPLETE PHONE SIGNUP ERROR:", str(e))
        return Response({"error": "Failed to complete signup. Please try again.", "success": False}, status=500)


@api_view(['POST'])
@csrf_exempt
def complete_signup(request):
    """Create the real User after both email and phone are verified."""
    try:
        data = json.loads(request.body)
        email = _normalize_email(data.get("email"))
        if not email:
            return Response({"error": "Email is required"}, status=400)

        pending = PendingSignup.objects(email=email).first()
        if not pending:
            return Response({"error": "Signup session not found. Please start signup again."}, status=404)

        if not pending.is_email_verified:
            return Response({"error": "Please verify your email first."}, status=400)
        if not pending.is_phone_verified:
            return Response({"error": "Please verify your phone first."}, status=400)

        if User.objects(email=pending.email).first():
            pending.delete()
            return Response(
                {"error": "An account with this email already exists. Please log in instead."},
                status=400,
            )
        if User.objects(username=pending.username).first():
            return Response(
                {"error": "Username already taken. Please start signup again with a different username."},
                status=400,
            )
        if User.objects(phone_number=pending.phone_e164).first():
            return Response(
                {"error": "This mobile number is already registered. Please use a different number."},
                status=400,
            )

        user = User(
            email=pending.email,
            password=pending.password,
            full_name=pending.full_name,
            username=pending.username,
            phone_number=pending.phone_e164,
            credit_balance=resolve_signup_credits(pending.signup_source),
            profile_completed=True,
            is_email_verified=True,
            is_phone_verified=True,
            role=Role.USER,
        )
        user.save()
        pending.delete()

        try:
            send_registration_email(user.email, user.full_name or user.username)
        except Exception as welcome_error:
            print(f"Failed to send welcome email to {user.email}: {welcome_error}")

        try:
            send_registration_admin_email(
                user.email,
                user_name=user.full_name,
                user_username=user.username,
            )
        except Exception:
            pass

        token = generate_jwt(user)
        return Response(_user_payload(user, token), status=200)

    except NotUniqueError:
        return Response({"error": "Email, username, or phone already exists"}, status=400)
    except Exception as e:
        print("COMPLETE SIGNUP ERROR:", str(e))
        return Response({"error": "Failed to create account. Please try again."}, status=500)


@api_view(['POST'])
@csrf_exempt
def signup_status(request):
    """Return pending signup verification status for resume UI."""
    try:
        data = json.loads(request.body)
        email = _normalize_email(data.get("email"))
        if not email:
            return Response({"error": "Email is required"}, status=400)
        pending = PendingSignup.objects(email=email).first()
        if not pending:
            return Response({"exists": False}, status=200)
        return Response({"exists": True, **_pending_status_payload(pending)}, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)


# =====================
# User Login
# =====================
@api_view(['POST'])
@csrf_exempt
def login_user(request):

    try:
        data = json.loads(request.body)
        email = data.get("email")
        password = data.get("password")

        if not email or not password:
            return Response({"error": "Email and password required"}, status=400)

        user = User.objects(email=email).first()
        if not user or not check_password(password, user.password):
            return JsonResponse({"error": "Invalid credentials"}, status=401)

        # Generate JWT token with user info
        token = generate_jwt(user)

        # Prepare organization data
        organization_data = None
        organization_id = None
        
        if user.organization:
            try:
                user.reload()  # Ensure organization is loaded
                if hasattr(user.organization, 'id'):
                    organization_id = str(user.organization.id)
                    organization_data = {
                        "id": organization_id,
                        "name": user.organization.name if hasattr(user.organization, 'name') else None,
                    }
                else:
                    organization_id = str(user.organization)
                    organization_data = {
                        "id": organization_id
                    }
            except Exception as e:
                organization_id = str(user.organization) if user.organization else None
                if organization_id:
                    organization_data = {
                        "id": organization_id
                    }

        return JsonResponse(
            {
                "message": "Login successful",
                "token": token,
                "user": {
                    "id": str(user.id),
                    "slug": user.slug if hasattr(user, 'slug') and user.slug else None,
                    "email": user.email,
                    "preferred_language": getattr(user, 'preferred_language', 'en') or 'en',
                    "role": user.role.value,
                    "full_name": user.full_name,
                    "username": user.username,
                    "organization": organization_data,
                    "organization_id": organization_id,
                    "organization_role": user.organization_role or None,
                    "profile_completed": user.profile_completed,
                },
            },
            status=200,
        )

    except Exception as e:
        print("LOGIN ERROR:", str(e))
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def invite_user(request):
    """
    Allows Owner or Admin to invite another user with a sub-role
    """
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = json.loads(request.body)
        inviter_email = data.get("inviter_email")
        invitee_email = data.get("invitee_email")
        # sub_role = data.get("sub_role")

        inviter = User.objects(email=inviter_email).first()
        if not inviter:
            return JsonResponse({"error": "Inviter not found"}, status=404)

        if inviter.role != Role.ADMIN:  # and inviter.sub_role != SubRole.OWNER:
            return JsonResponse({"error": "Only owners or admins can invite"}, status=403)

        # if sub_role not in [s.value for s in SubRole]:
        #     return JsonResponse({"error": "Invalid sub role"}, status=400)

        invitee = User.objects(email=invitee_email).first()
        if not invitee:
            # Create a new user placeholder (they can complete registration later)
            invitee = User(
                email=invitee_email,
                password=make_password("temp_password"),
                role=Role.USER,
                # sub_role=SubRole[sub_role.upper()]
            )
            invitee.save()
        else:
            # invitee.sub_role = SubRole[sub_role.upper()]
            invitee.save()

        return JsonResponse({"message": f"User invited"}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# =====================
# Get User Profile
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def get_user_profile(request):
    """Get current user's profile information"""
    try:
        user = request.user
        
        # Reload user to ensure organization reference is loaded
        user.reload()
        
        # Prepare organization data
        organization_data = None
        organization_id = None
        
        if user.organization:
            try:
                # Try to access as a dereferenced Document
                if hasattr(user.organization, 'id'):
                    # Organization is a Document instance
                    organization_id = str(user.organization.id)
                    organization_data = {
                        "id": organization_id,
                        "name": user.organization.name if hasattr(user.organization, 'name') else None,
                        "credit_balance": user.organization.credit_balance if hasattr(user.organization, 'credit_balance') else None
                    }
                else:
                    # Organization is just an ObjectId
                    organization_id = str(user.organization)
                    organization_data = {
                        "id": organization_id
                    }
            except Exception as e:
                # If dereferencing fails, just use the ID
                organization_id = str(user.organization) if user.organization else None
                if organization_id:
                    organization_data = {
                        "id": organization_id
                    }

        return JsonResponse({
            "success": True,
            "user": {
                "id": str(user.id),
                "slug": user.slug if hasattr(user, 'slug') and user.slug else None,
                "email": user.email,
                "full_name": user.full_name or "",
                "username": user.username or "",
                "role": user.role.value,
                "organization": organization_data,
                "organization_id": organization_id,
                "organization_role": user.organization_role or None,
                "profile_completed": user.profile_completed,
                "preferred_language": getattr(user, 'preferred_language', 'en') or 'en',
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None,
                "credit_balance": user.credit_balance or 0,
            }
        }, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# =====================
# Update User Profile
# =====================
@api_view(['PUT'])
@csrf_exempt
@authenticate
def update_user_profile(request):
    """Update current user's profile information"""
    try:
        user = request.user
        data = json.loads(request.body)

        # Update allowed fields
        if 'full_name' in data:
            user.full_name = data['full_name']

        if 'username' in data:
            # Check if username is unique (if changed)
            existing_user = User.objects(username=data['username']).first()
            if existing_user and str(existing_user.id) != str(user.id):
                return Response({"error": "Username already exists"}, status=400)
            user.username = data['username']

        if 'preferred_language' in data:
            # Validate language code
            if data['preferred_language'] in ['en', 'es']:
                user.preferred_language = data['preferred_language']
            else:
                return Response({"error": "Invalid language code"}, status=400)

        # Update timestamp
        user.updated_at = datetime.datetime.utcnow()
        user.save()

        return JsonResponse({
            "success": True,
            "message": "Profile updated successfully",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name or "",
                "username": user.username or "",
                "role": user.role.value,
                "profile_completed": user.profile_completed,
                "preferred_language": getattr(user, 'preferred_language', 'en') or 'en',
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            }
        }, status=200)
    except NotUniqueError:
        return Response({"error": "Username already exists"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# =====================
# Complete Profile
# =====================
@api_view(['POST'])
@csrf_exempt
@authenticate
def complete_profile(request):
    """Complete user profile - allows setting password and updating profile info"""
    try:
        user = request.user
        data = json.loads(request.body)

        # Update allowed fields
        if 'full_name' in data:
            user.full_name = data['full_name']

        if 'username' in data:
            # Check if username is unique (if changed)
            existing_user = User.objects(username=data['username']).first()
            if existing_user and str(existing_user.id) != str(user.id):
                return JsonResponse({"error": "Username already exists"}, status=400)
            user.username = data['username']

        # Password is required during profile completion
        if 'new_password' not in data or not data['new_password']:
            return JsonResponse({"error": "Password is required to complete your profile"}, status=400)
        
        new_password = data['new_password']
        if len(new_password) < 8:
            return JsonResponse({"error": "Password must be at least 8 characters long"}, status=400)
        user.password = make_password(new_password)

        # Mark profile as completed
        user.profile_completed = True
        user.updated_at = datetime.datetime.utcnow()
        user.save()

        # Reload to get organization data
        user.reload()
        
        # Prepare organization data
        organization_data = None
        organization_id = None
        
        if user.organization:
            try:
                if hasattr(user.organization, 'id'):
                    organization_id = str(user.organization.id)
                    organization_data = {
                        "id": organization_id,
                        "name": user.organization.name if hasattr(user.organization, 'name') else None,
                    }
                else:
                    organization_id = str(user.organization)
                    organization_data = {
                        "id": organization_id
                    }
            except Exception as e:
                organization_id = str(user.organization) if user.organization else None
                if organization_id:
                    organization_data = {
                        "id": organization_id
                    }

        return JsonResponse({
            "success": True,
            "message": "Profile completed successfully",
            "user": {
                "id": str(user.id),
                "slug": user.slug if hasattr(user, 'slug') and user.slug else None,
                "email": user.email,
                "full_name": user.full_name or "",
                "username": user.username or "",
                "role": user.role.value,
                "organization": organization_data,
                "organization_id": organization_id,
                "organization_role": user.organization_role or None,
                "profile_completed": user.profile_completed,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            }
        }, status=200)
    except NotUniqueError:
        return JsonResponse({"error": "Username already exists"}, status=400)
    except Exception as e:
        
        return JsonResponse({"error": str(e)}, status=500)


# =====================
# Forgot Password
# =====================
@api_view(['POST'])
@csrf_exempt
def forgot_password(request):
    """Send password reset email to user"""
    try:
        data = json.loads(request.body)
        email = data.get("email")

        if not email:
            return JsonResponse({"error": "Email is required"}, status=400)

        user = User.objects(email=email).first()
        if not user:
            # Don't reveal if email exists for security
            return JsonResponse({
                "message": "If the email exists, a password reset link has been sent."
            }, status=200)

        # Generate reset token
        reset_token = secrets.token_urlsafe(32)
        user.reset_password_token = reset_token
        user.reset_password_token_expiry = datetime.datetime.utcnow() + timedelta(hours=24)
        user.save()

        # Send reset email
        try:
            send_password_reset_email(user.email, reset_token, user.full_name or user.username)
        except Exception as e:
            print(f"Failed to send password reset email: {e}")
            return JsonResponse({"error": "Failed to send reset email. Please try again later."}, status=500)

        return JsonResponse({
            "message": "If the email exists, a password reset link has been sent."
        }, status=200)

    except Exception as e:
        print("FORGOT PASSWORD ERROR:", str(e))
        return JsonResponse({"error": str(e)}, status=500)


# =====================
# Reset Password
# =====================
@api_view(['POST'])
@csrf_exempt
def reset_password(request):
    """Reset password using token from email"""
    try:
        data = json.loads(request.body)
        token = data.get("token")
        new_password = data.get("new_password")

        if not token or not new_password:
            return JsonResponse({"error": "Token and new password are required"}, status=400)

        if len(new_password) < 8:
            return JsonResponse({"error": "Password must be at least 8 characters long"}, status=400)

        user = User.objects(reset_password_token=token).first()
        if not user:
            return JsonResponse({"error": "Invalid or expired reset token"}, status=400)

        # Check if token is expired
        if user.reset_password_token_expiry and user.reset_password_token_expiry < datetime.datetime.utcnow():
            user.reset_password_token = None
            user.reset_password_token_expiry = None
            user.save()
            return JsonResponse({"error": "Reset token has expired. Please request a new one."}, status=400)

        # Update password
        user.password = make_password(new_password)
        user.reset_password_token = None
        user.reset_password_token_expiry = None
        user.updated_at = datetime.datetime.utcnow()
        user.save()

        return JsonResponse({
            "message": "Password reset successfully. You can now log in with your new password."
        }, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# =====================
# Change Password (Authenticated)
# =====================
@api_view(["POST"])
@csrf_exempt
@authenticate
def change_password(request):
    """Change password for the currently authenticated user."""
    try:
        user = request.user
        data = json.loads(request.body or "{}")
        current_password = data.get("current_password")
        new_password = data.get("new_password")

        if not current_password or not new_password:
            return JsonResponse(
                {"error": "Current password and new password are required"}, status=400
            )

        if not check_password(current_password, user.password):
            return JsonResponse({"error": "Current password is incorrect"}, status=400)

        if len(new_password) < 8:
            return JsonResponse(
                {"error": "Password must be at least 8 characters long"}, status=400
            )

        user.password = make_password(new_password)
        user.updated_at = datetime.datetime.utcnow()
        user.save()

        return JsonResponse({"success": True, "message": "Password updated successfully"}, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)