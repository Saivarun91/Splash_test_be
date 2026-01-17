"""
Organization CRUD views with role-based access control
"""
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt
import json
from mongoengine.errors import DoesNotExist, NotUniqueError
from .models import Organization
from users.models import User, Role
from roles.models import OrgRole, OrgRoleType
from common.middleware import authenticate
from CREDITS.utils import add_credits, deduct_credits
from datetime import datetime
from django.contrib.auth.hashers import make_password
from probackendapp.models import Project


def is_admin(user):
    """Check if user is admin"""
    return user.role == Role.ADMIN


def is_organization_owner(user, organization):
    """Check if user is owner of the organization"""
    if not user.organization or str(user.organization.id) != str(organization.id):
        return False
    return user.organization_role == "owner" or str(organization.owner.id) == str(user.id)


def is_organization_member(user, organization):
    """Check if user is a member of the organization"""
    if not user.organization:
        return False
    return str(user.organization.id) == str(organization.id)


def has_organization_permission(user, organization, required_roles=None):
    """
    Check if user has permission to perform action on organization.
    Admin has all permissions.
    Owner, chief_editor, editor have edit permissions.
    """
    if is_admin(user):
        return True

    if not is_organization_member(user, organization):
        return False

    if is_organization_owner(user, organization):
        return True

    if required_roles:
        user_role = user.organization_role or ""
        return user_role in required_roles

    return True


# =====================
# Admin-only: Create Organization
# =====================
@api_view(['POST'])
@csrf_exempt
@authenticate
def create_organization(request):
    """Only admin can create organizations"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can create organizations'}, status=403)

    try:
        data = json.loads(request.body)
        name = data.get('name')
        owner_email = data.get('owner_email')
        initial_credits = data.get('initial_credits', 0)

        if not name or not owner_email:
            return JsonResponse({'error': 'Name and owner_email are required'}, status=400)

        # Check if organization name already exists
        if Organization.objects(name=name).first():
            return JsonResponse({'error': 'Organization with this name already exists'}, status=400)

        # Get or create owner user
        owner = User.objects(email=owner_email).first()
        user_created = False
        if not owner:
            # Create new user as organization owner
            # Generate username from email (part before @)
            username = owner_email.split('@')[0]
            # Ensure username is unique by appending numbers if needed
            base_username = username
            counter = 1
            while User.objects(username=username).first():
                username = f"{base_username}{counter}"
                counter += 1

            # Create user with temporary password (user should reset it on first login)
            owner = User(
                email=owner_email,
                # Temporary password - should be changed on first login
                password=make_password("12345678"),
                username=username,
                # Use first word of org name or username
                full_name=name.split()[0] if name else username,
                role=Role.USER
            )
            try:
                owner.save()
                user_created = True
            except NotUniqueError:
                return JsonResponse({'error': 'User with this email or username already exists'}, status=400)

        # Create organization
        organization = Organization(
            name=name,
            owner=owner,
            credit_balance=initial_credits,
            created_by=request.user,
            updated_by=request.user
        )
        organization.save()

        # Update owner's organization
        owner.organization = organization
        owner.organization_role = "owner"
        owner.save()

        # Add owner to members list
        if owner not in organization.members:
            organization.members.append(owner)
            organization.save()

        # Create OrgRole entry for owner (BUSSINESS_OWNER)
        org_role = OrgRole(
            user=owner,
            organization=organization,
            role=OrgRoleType.BUSSINESS_OWNER,
            created_by=request.user,
            updated_by=request.user
        )
        org_role.save()

        # Create ledger entry for initial credits if any
        if initial_credits > 0:
            add_credits(organization, request.user, initial_credits,
                        reason="Initial credit allocation")

        message = 'Organization created successfully'
        if user_created:
            message += '. Owner user was created with temporary password (temp_password_123). Please change it on first login.'

        return JsonResponse({
            'success': True,
            'message': message,
            'organization': {
                'id': str(organization.id),
                'name': organization.name,
                'owner_email': owner.email,
                'credit_balance': organization.credit_balance
            },
            'user_created': user_created
        }, status=201)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Admin-only: Add User to Organization
# =====================
@api_view(['POST'])
@csrf_exempt
@authenticate
def add_user_to_organization(request):
    """Only admin can add users to organizations"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can add users to organizations'}, status=403)

    try:
        data = json.loads(request.body)
        user_email = data.get('user_email')
        organization_id = data.get('organization_id')
        # owner, editor, chief_editor, member
        organization_role = data.get('organization_role', 'member')

        if not user_email or not organization_id:
            return JsonResponse({'error': 'user_email and organization_id are required'}, status=400)

        # Validate organization role
        valid_roles = ['owner', 'chief_editor', 'creative_head', 'member']
        if organization_role not in valid_roles:
            return JsonResponse({'error': f'Invalid role. Must be one of: {", ".join(valid_roles)}'}, status=400)

        user = User.objects(email=user_email).first()
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)

        organization = Organization.objects(id=organization_id).first()
        if not organization:
            return JsonResponse({'error': 'Organization not found'}, status=404)

        # Ensure organization is saved (should already be, but verify)
        if not organization.id:
            organization.save()

        # Update user's organization - assign the organization Document directly to ReferenceField
        # MongoEngine will automatically convert it to a DBRef when saving
        user.organization = organization
        user.organization_role = organization_role
        user.updated_at = datetime.utcnow()  # Explicitly update the timestamp

        # Save the user with the organization reference
        user.save()

        # Verify the organization reference was saved correctly
        user.reload()

        # Double-check that the organization reference is properly set
        if not user.organization or str(user.organization.id) != str(organization.id):
            # If reference didn't save, try saving again with explicit reference
            user.organization = organization
            user.save()
            user.reload()

        # Add to members list if not already
        if user not in organization.members:
            organization.members.append(user)
            organization.save()

        # Create OrgRole entry
        # Map organization_role to OrgRoleType enum
        role_mapping = {
            'owner': OrgRoleType.BUSSINESS_OWNER,
            'chief_editor': OrgRoleType.CHIEF_EDITOR,
            'creative_head': OrgRoleType.CREATIVE_HEAD,
            'member': OrgRoleType.MEMBER,
        }
        role_enum = role_mapping.get(organization_role, OrgRoleType.MEMBER)

        org_role = OrgRole(
            user=user,
            organization=organization,
            role=role_enum,
            created_by=request.user,
            updated_by=request.user
        )
        org_role.save()

        # Verify organization reference is saved
        org_ref_id = str(user.organization.id) if user.organization else None
        org_id = str(organization.id)

        return JsonResponse({
            'success': True,
            'message': 'User added to organization successfully',
            'user': {
                'id': str(user.id),
                'email': user.email,
                'full_name': user.full_name,
                'organization': {
                    'id': org_ref_id or org_id,
                    'name': organization.name
                },
                'organization_id': org_ref_id or org_id,
                'organization_role': organization_role,
                'updated_at': user.updated_at.isoformat() if user.updated_at else None,
                'organization_reference_saved': org_ref_id == org_id if org_ref_id else False
            }
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# List Organizations (Admin sees all, users see their own)
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def list_organizations(request):
    """List organizations - admin sees all, users see their own"""
    try:
        if is_admin(request.user):
            organizations = Organization.objects.all()
        else:
            if not request.user.organization:
                return JsonResponse({'organizations': []}, status=200)
            organizations = [request.user.organization]

        org_list = []
        for org in organizations:
            org_list.append({
                'id': str(org.id),
                'name': org.name,
                'owner_email': org.owner.email,
                'credit_balance': org.credit_balance,
                'member_count': len(org.members) if org.members else 0,
                'created_at': org.created_at.isoformat() if org.created_at else None
            })

        return JsonResponse({'organizations': org_list}, status=200)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Get Organization Details
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def get_organization(request, organization_id):
    """Get organization details - must be member or admin"""
    try:
        organization = Organization.objects(id=organization_id).first()
        if not organization:
            return JsonResponse({'error': 'Organization not found'}, status=404)

        if not has_organization_permission(request.user, organization):
            return JsonResponse({'error': 'You do not have permission to view this organization'}, status=403)

        members_list = []
        for member in organization.members:
            members_list.append({
                'id': str(member.id),
                'email': member.email,
                'full_name': member.full_name,
                'organization_role': member.organization_role
            })

        # Get projects for this organization
        projects_list = []
        for project_ref in organization.projects:
            try:
                # Dereference the project (MongoEngine ReferenceField)
                if hasattr(project_ref, 'id'):
                    # Already dereferenced
                    project = project_ref
                else:
                    # Need to dereference - get the project by ID
                    project = Project.objects(id=project_ref).first()
                    if not project:
                        continue

                projects_list.append({
                    'id': str(project.id),
                    'name': project.name,
                    'about': project.about,
                    'status': project.status,
                    'created_at': project.created_at.isoformat() if project.created_at else None,
                    'organization': str(project.organization.id) if project.organization else None,
                    'organization_id': str(project.organization.id) if project.organization else None,
                })
            except (DoesNotExist, AttributeError, TypeError):
                # Skip projects that no longer exist or have issues
                continue

        return JsonResponse({
            'id': str(organization.id),
            'name': organization.name,
            'owner_email': organization.owner.email,
            'credit_balance': organization.credit_balance,
            'members': members_list,
            'projects': projects_list,
            'created_at': organization.created_at.isoformat() if organization.created_at else None
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Update Organization (Owner/Admin only)
# =====================
@api_view(['PUT'])
@csrf_exempt
@authenticate
def update_organization(request, organization_id):
    """Update organization - owner or admin only"""
    try:
        organization = Organization.objects(id=organization_id).first()
        if not organization:
            return JsonResponse({'error': 'Organization not found'}, status=404)

        if not (is_admin(request.user) or is_organization_owner(request.user, organization)):
            return JsonResponse({'error': 'Only owner or admin can update organization'}, status=403)

        data = json.loads(request.body)

        if 'name' in data:
            # Check if name is unique
            existing = Organization.objects(name=data['name']).first()
            if existing and str(existing.id) != str(organization.id):
                return JsonResponse({'error': 'Organization name already exists'}, status=400)
            organization.name = data['name']

        if 'metadata' in data:
            organization.metadata = data['metadata']

        organization.updated_by = request.user
        organization.updated_at = datetime.utcnow()
        organization.save()

        return JsonResponse({
            'success': True,
            'message': 'Organization updated successfully',
            'organization': {
                'id': str(organization.id),
                'name': organization.name,
                'credit_balance': organization.credit_balance
            }
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Delete Organization (Admin only)
# =====================
@api_view(['DELETE'])
@csrf_exempt
@authenticate
def delete_organization(request, organization_id):
    """Delete organization - admin only"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can delete organizations'}, status=403)

    try:
        organization = Organization.objects(id=organization_id).first()
        if not organization:
            return JsonResponse({'error': 'Organization not found'}, status=404)

        organization.delete()

        return JsonResponse({
            'success': True,
            'message': 'Organization deleted successfully'
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Admin-only: Add Credits to Organization
# =====================
@api_view(['POST'])
@csrf_exempt
@authenticate
def add_organization_credits(request, organization_id):
    """Only admin can add credits to organizations"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can add credits'}, status=403)

    try:
        data = json.loads(request.body)
        amount = data.get('amount')
        reason = data.get('reason', 'Credit top-up by admin')

        if not amount or amount <= 0:
            return JsonResponse({'error': 'Valid amount is required'}, status=400)

        organization = Organization.objects(id=organization_id).first()
        if not organization:
            return JsonResponse({'error': 'Organization not found'}, status=404)

        result = add_credits(organization, request.user, amount, reason=reason)

        if result['success']:
            return JsonResponse({
                'success': True,
                'message': result['message'],
                'balance_after': result['balance_after']
            }, status=200)
        else:
            return JsonResponse({'error': result['message']}, status=500)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Admin-only: Remove Credits from Organization
# =====================
@api_view(['POST'])
@csrf_exempt
@authenticate
def remove_organization_credits(request, organization_id):
    """Only admin can remove credits from organizations"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can remove credits'}, status=403)

    try:
        data = json.loads(request.body)
        amount = data.get('amount')
        reason = data.get('reason', 'Credit deduction by admin')

        if not amount or amount <= 0:
            return JsonResponse({'error': 'Valid amount is required'}, status=400)

        organization = Organization.objects(id=organization_id).first()
        if not organization:
            return JsonResponse({'error': 'Organization not found'}, status=404)

        result = deduct_credits(
            organization, request.user, amount, reason=reason)

        if result['success']:
            return JsonResponse({
                'success': True,
                'message': result['message'],
                'balance_after': result['balance_after']
            }, status=200)
        else:
            return JsonResponse({'error': result['message']}, status=400)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Admin-only: Remove User from Organization
# =====================
@api_view(['DELETE'])
@csrf_exempt
@authenticate
def remove_user_from_organization(request, organization_id, user_id):
    """Only admin can remove users from organizations"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can remove users from organizations'}, status=403)

    try:
        organization = Organization.objects(id=organization_id).first()
        if not organization:
            return JsonResponse({'error': 'Organization not found'}, status=404)

        user = User.objects(id=user_id).first()
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)

        # Check if user is the owner
        if str(organization.owner.id) == str(user.id):
            return JsonResponse({'error': 'Cannot remove organization owner'}, status=400)

        # Check if user is actually in this organization
        if not user.organization or str(user.organization.id) != str(organization.id):
            return JsonResponse({'error': 'User is not a member of this organization'}, status=400)

        # Remove user from organization members list
        if user in organization.members:
            organization.members.remove(user)
            organization.save()

        # Clear user's organization reference
        user.organization = None
        user.organization_role = None
        user.updated_at = datetime.utcnow()
        user.save()

        # Delete OrgRole entries for this user-organization combination
        OrgRole.objects(user=user, organization=organization).delete()

        return JsonResponse({
            'success': True,
            'message': 'User removed from organization successfully'
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
