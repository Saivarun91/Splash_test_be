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
from common.middleware import authenticate

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
            role=Role.USER,  # Default
        )
        user.save()

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

        return JsonResponse(
            {
                "message": "Login successful",
                "token": token,
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "role": user.role.value,
                    # "sub_role": user.sub_role.value if user.sub_role else None,
                    "full_name": user.full_name,
                    "username": user.username,
                },
            },
            status=200,
        )

    except Exception as e:
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

        return JsonResponse({
            "success": True,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name or "",
                "username": user.username or "",
                "role": user.role.value,
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
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            }
        }, status=200)
    except NotUniqueError:
        return Response({"error": "Username already exists"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
