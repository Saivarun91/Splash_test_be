from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt
import json
from mongoengine.errors import NotUniqueError
from .models import User, Role
from django.contrib.auth.hashers import make_password, check_password
import jwt
import datetime
from datetime import timedelta
from django.conf import settings
import secrets
from common.middleware import authenticate
from common.email_utils import send_registration_email, send_registration_admin_email, send_password_reset_email, generate_random_password

SECRET_KEY = settings.SECRET_KEY


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


# =====================
# User Registration
# =====================
@api_view(['POST'])
@csrf_exempt
def register_user(request):

    try:
        data = json.loads(request.body)
        email = data.get("email")
        password = data.get("password")
        full_name = data.get("full_name")
        username = data.get("username")
        role = data.get("role")
        if not email or not password:
            return Response({"error": "Email and password required"}, status=400)

        # Hash password
        hashed_pw = make_password(password)

        # Create new user
        user = User(
            email=email,
            password=hashed_pw,
            full_name=full_name,
            username=username,
            role=role,  # Default
            
            profile_completed=False,  # User needs to complete profile
        )
        user.save()

        # Send registration email to user
        try:
            send_registration_email(user.email, user.full_name or user.username)
        except Exception as e:
            print(f"Failed to send registration email: {e}")
        # Notify admin(s) that a new user registered
        try:
            send_registration_admin_email(
                user.email,
                user.full_name or user.username,
                user.username,
            )
        except Exception as e:
            print(f"Failed to send registration admin notification: {e}")
            # Don't fail registration if email fails

        # Generate JWT after registration (optional)
        token = generate_jwt(user)

        return JsonResponse(
            {
                "message": "User registered successfully!",
                "token": token,
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "role": user.role.value,
                    "profile_completed": user.profile_completed,
                },
            },
            status=201,
        )

    except NotUniqueError:
        return Response({"error": "Email or username already exists"}, status=400)
    except Exception as e:
        print(e)
        return JsonResponse({"error": str(e)}, status=500)


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
                    "email": user.email,
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
