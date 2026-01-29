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
from common.email_utils import send_organization_invite_email, send_invite_organizer_confirmation, generate_random_password
from probackendapp.models import Project, ImageGenerationHistory
from imgbackendapp.mongo_models import OrnamentMongo
from mongoengine import Q


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
# Organization Owner: Add User to Organization
# =====================
@api_view(['POST'])
@csrf_exempt
@authenticate
def add_organization_user(request, organization_id):
    """Organization owner can add users to their organization by email and role"""
    try:
        organization = Organization.objects(id=organization_id).first()
        if not organization:
            return JsonResponse({'error': 'Organization not found'}, status=404)

        # Check if user is organization owner or admin
        if not (is_admin(request.user) or is_organization_owner(request.user, organization)):
            return JsonResponse({'error': 'Only organization owner or admin can add users'}, status=403)

        data = json.loads(request.body)
        user_email = data.get('email')
        organization_role = data.get('role', 'member')

        if not user_email:
            return JsonResponse({'error': 'Email is required'}, status=400)

        # Validate organization role
        valid_roles = ['owner', 'chief_editor', 'creative_head', 'member']
        if organization_role not in valid_roles:
            return JsonResponse({'error': f'Invalid role. Must be one of: {", ".join(valid_roles)}'}, status=400)

        # Check if user already exists
        user = User.objects(email=user_email).first()
        user_created = False

        if not user:
            # Create new user with random 16-digit password
            random_password = generate_random_password(16)
            hashed_password = make_password(random_password)

            # Generate username from email
            username = user_email.split('@')[0]
            base_username = username
            counter = 1
            while User.objects(username=username).first():
                username = f"{base_username}{counter}"
                counter += 1

            # Create user
            user = User(
                email=user_email,
                password=hashed_password,
                username=username,
                role=Role.USER,
                organization=organization,
                organization_role=organization_role,
                profile_completed=False,  # User needs to complete profile
            )
            try:
                user.save()
                user_created = True
            except NotUniqueError:
                return JsonResponse({'error': 'User with this email or username already exists'}, status=400)

            # Send email with password
            try:
                send_organization_invite_email(
                    user_email,
                    random_password,
                    organization.name,
                    organization_role,
                    request.user.full_name or request.user.username,
                    is_new_user=True
                )
                send_invite_organizer_confirmation(
                    request.user.email,
                    user_email,
                    organization.name,
                    organization_role,
                )
            except Exception as e:
                print(f"Failed to send organization invite email: {e}")
                # Don't fail if email fails, but log it
        else:
            # User exists, check if already in this organization
            if user.organization and str(user.organization.id) == str(organization.id):
                return JsonResponse({'error': 'User is already a member of this organization'}, status=400)
            
            # Check if user is already in another organization
            if user.organization and str(user.organization.id) != str(organization.id):
                existing_org = user.organization
                return JsonResponse({
                    'error': f'This Member is already in another organization',
                    'existing_organization': existing_org.name,
                    'existing_organization_id': str(existing_org.id)
                }, status=400)

            user.organization = organization
            user.organization_role = organization_role
            user.profile_completed = False  # Reset profile completion if user is being added to new org
            user.updated_at = datetime.utcnow()
            user.save()

            # Send notification email to existing user
            try:
                send_organization_invite_email(
                    user_email,
                    None,  # No password for existing users
                    organization.name,
                    organization_role,
                    request.user.full_name or request.user.username,
                    is_new_user=False
                )
                send_invite_organizer_confirmation(
                    request.user.email,
                    user_email,
                    organization.name,
                    organization_role,
                )
            except Exception as e:
                print(f"Failed to send organization notification email: {e}")
                # Don't fail if email fails, but log it

        # Add to members list if not already
        if user not in organization.members:
            organization.members.append(user)
            organization.save()

        # Create OrgRole entry
        role_mapping = {
            'owner': OrgRoleType.BUSSINESS_OWNER,
            'chief_editor': OrgRoleType.CHIEF_EDITOR,
            'creative_head': OrgRoleType.CREATIVE_HEAD,
            'member': OrgRoleType.MEMBER,
        }
        role_enum = role_mapping.get(organization_role, OrgRoleType.MEMBER)

        # Delete existing OrgRole if any
        OrgRole.objects(user=user, organization=organization).delete()

        org_role = OrgRole(
            user=user,
            organization=organization,
            role=role_enum,
            created_by=request.user,
            updated_by=request.user
        )
        org_role.save()

        return JsonResponse({
            'success': True,
            'message': 'User added to organization successfully',
            'user_created': user_created,
            'user': {
                'id': str(user.id),
                'email': user.email,
                'organization_role': organization_role,
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
        # Query projects directly by organization instead of using organization.projects
        organization_projects = Project.objects(organization=organization)
        projects_list = []
        
        for project in organization_projects:
            try:
                # Get image count for this project
                project_images_count = ImageGenerationHistory.objects(project=project).count()
                
                # Get team members
                team_members_data = []
                if project.team_members:
                    for member in project.team_members:
                        try:
                            user_obj = member.user
                            team_members_data.append({
                                'user_name': user_obj.full_name or user_obj.username or '',
                                'email': user_obj.email,
                                'role': member.role
                            })
                        except (DoesNotExist, AttributeError):
                            continue

                projects_list.append({
                    'id': str(project.id),
                    'name': project.name,
                    'about': project.about,
                    'status': project.status,
                    'created_at': project.created_at.isoformat() if project.created_at else None,
                    'updated_at': project.updated_at.isoformat() if project.updated_at else None,
                    'organization': str(project.organization.id) if project.organization else None,
                    'organization_id': str(project.organization.id) if project.organization else None,
                    'totalImages': project_images_count,
                    'members': team_members_data
                })
            except (DoesNotExist, AttributeError, TypeError) as e:
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
# Admin and Organization Owner: Remove User from Organization
# =====================
@api_view(['DELETE'])
@csrf_exempt
@authenticate
def remove_user_from_organization(request, organization_id, user_id):
    """Admin and organization owner can remove users from organizations"""
    try:
        organization = Organization.objects(id=organization_id).first()
        if not organization:
            return JsonResponse({'error': 'Organization not found'}, status=404)

        # Check if user is organization owner or admin
        if not (is_admin(request.user) or is_organization_owner(request.user, organization)):
            return JsonResponse({'error': 'Only organization owner or admin can remove users'}, status=403)

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


# =====================
# Organization Owner: Remove User from Organization
# =====================
@api_view(['DELETE'])
@csrf_exempt
@authenticate
def remove_organization_user(request, organization_id, user_id):
    """Organization owner can remove users from their organization"""
    try:
        organization = Organization.objects(id=organization_id).first()
        if not organization:
            return JsonResponse({'error': 'Organization not found'}, status=404)

        # Check if user is organization owner or admin
        if not (is_admin(request.user) or is_organization_owner(request.user, organization)):
            return JsonResponse({'error': 'Only organization owner or admin can remove users'}, status=403)

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


# =====================
# Get Organization Images
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def get_organization_images(request, organization_id):
    """Get all images generated under an organization - owner/admin only"""
    try:
        organization = Organization.objects(id=organization_id).first()
        if not organization:
            return JsonResponse({'error': 'Organization not found'}, status=404)

        # Check permission - only owner or admin can view
        if not (is_admin(request.user) or is_organization_owner(request.user, organization)):
            return JsonResponse({'error': 'Only organization owner or admin can view images'}, status=403)

        # Get query parameters
        image_type = request.GET.get('image_type')  # Optional filter
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        limit = int(request.GET.get('limit', 100))
        offset = int(request.GET.get('offset', 0))

        # Get all organization members
        organization_members = organization.members if organization.members else []
        member_ids = [str(member.id) for member in organization_members]
        
        # Also include the owner
        if organization.owner:
            owner_id = str(organization.owner.id)
            if owner_id not in member_ids:
                member_ids.append(owner_id)

        # Get all projects for this organization
        organization_projects = Project.objects(organization=organization)
        project_ids = [str(p.id) for p in organization_projects]

        # Build query for project-based images (ImageGenerationHistory)
        project_query = Q(project__in=organization_projects)

        if image_type:
            project_query &= Q(image_type=image_type)

        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                project_query &= Q(created_at__gte=start_dt)
            except:
                pass

        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                project_query &= Q(created_at__lte=end_dt)
            except:
                pass

        # Get project-based images
        project_images = ImageGenerationHistory.objects(project_query).order_by('-created_at')
        project_total = ImageGenerationHistory.objects(project_query).count()

        # Build query for individual images (OrnamentMongo)
        # Filter by organization members
        individual_query = None
        
        if member_ids:
            # Query by user_id (string field)
            individual_query = Q(user_id__in=member_ids)
            
            # Also check created_by reference field
            member_refs = []
            for mid in member_ids:
                user = User.objects(id=mid).first()
                if user:
                    member_refs.append(user)
            
            if member_refs:
                # Combine queries: user_id in member_ids OR created_by in member_refs
                individual_query = individual_query | Q(created_by__in=member_refs)
        else:
            # If no members, return empty result for individual images
            individual_query = Q(id__in=[])  # Empty query

        if individual_query is not None:
            if image_type:
                # Map image types to OrnamentMongo types
                type_mapping = {
                    'white_background': 'white_background',
                    'background_change': 'background_change',
                    'model_with_ornament': 'model_with_ornament',
                    'real_model_with_ornament': 'real_model_with_ornament',
                    'campaign_shot_advanced': 'campaign_shot_advanced'
                }
                if image_type in type_mapping:
                    individual_query &= Q(type=type_mapping[image_type])

            if start_date:
                try:
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    individual_query &= Q(created_at__gte=start_dt)
                except:
                    pass

            if end_date:
                try:
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    individual_query &= Q(created_at__lte=end_dt)
                except:
                    pass

            # Get individual images
            individual_images = OrnamentMongo.objects(individual_query).order_by('-created_at')
            individual_total = OrnamentMongo.objects(individual_query).count()
        else:
            individual_images = []
            individual_total = 0

        # Combine and format response
        images_list = []
        
        # Add project-based images
        for img in project_images:
            images_list.append({
                'id': str(img.id),
                'image_url': img.image_url,
                'image_type': img.image_type,
                'prompt': img.prompt,
                'original_prompt': img.original_prompt,
                'user_id': img.user_id,
                'project_id': str(img.project.id) if img.project else None,
                'collection_id': str(img.collection.id) if img.collection else None,
                'created_at': img.created_at.isoformat() if img.created_at else None,
                'metadata': img.metadata or {},
                'source': 'project'  # Indicate this is from a project
            })
        
        # Add individual images
        for img in individual_images:
            images_list.append({
                'id': str(img.id),
                'image_url': img.generated_image_url,
                'image_type': img.type,
                'prompt': img.prompt,
                'original_prompt': img.original_prompt,
                'user_id': img.user_id or (str(img.created_by.id) if img.created_by else None),
                'project_id': None,
                'collection_id': None,
                'created_at': img.created_at.isoformat() if img.created_at else None,
                'metadata': {
                    'uploaded_image_url': img.uploaded_image_url,
                    'model_image_url': img.model_image_url,
                    'parent_image_id': str(img.parent_image_id) if img.parent_image_id else None
                },
                'source': 'individual'  # Indicate this is an individual image
            })

        # Sort all images by created_at (newest first)
        images_list.sort(key=lambda x: x['created_at'] or '', reverse=True)
        
        # Apply pagination
        total_count = project_total + individual_total
        paginated_images = images_list[offset:offset + limit]

        return JsonResponse({
            'organization_id': str(organization.id),
            'organization_name': organization.name,
            'total_count': total_count,
            'project_images_count': project_total,
            'individual_images_count': individual_total,
            'images': paginated_images
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Get Organization Stats
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def get_organization_stats(request, organization_id):
    """Get organization statistics - owner/admin only"""
    try:
        organization = Organization.objects(id=organization_id).first()
        if not organization:
            return JsonResponse({'error': 'Organization not found'}, status=404)

        # Check permission
        if not (is_admin(request.user) or is_organization_owner(request.user, organization)):
            return JsonResponse({'error': 'Only organization owner or admin can view stats'}, status=403)

        # Get all organization members
        organization_members = organization.members if organization.members else []
        member_ids = [str(member.id) for member in organization_members]
        
        # Also include the owner
        if organization.owner:
            owner_id = str(organization.owner.id)
            if owner_id not in member_ids:
                member_ids.append(owner_id)

        # Get projects
        projects = Project.objects(organization=organization)
        project_ids = [str(p.id) for p in projects]

        # Get project-based images
        project_images_count = ImageGenerationHistory.objects(project__in=projects).count()

        # Get individual images count
        individual_images_count = 0
        if member_ids:
            member_refs = []
            for mid in member_ids:
                user = User.objects(id=mid).first()
                if user:
                    member_refs.append(user)
            
            if member_refs:
                individual_query = Q(user_id__in=member_ids) | Q(created_by__in=member_refs)
                individual_images_count = OrnamentMongo.objects(individual_query).count()

        # Total images (project + individual)
        total_images = project_images_count + individual_images_count

        # Get images by type (project-based)
        images_by_type = {}
        for img_type in ['white_background', 'background_change', 'model_with_ornament', 'campaign_shot_advanced']:
            count = ImageGenerationHistory.objects(project__in=projects, image_type=img_type).count()
            # Also count individual images of this type
            if member_ids:
                member_refs = []
                for mid in member_ids:
                    user = User.objects(id=mid).first()
                    if user:
                        member_refs.append(user)
                if member_refs:
                    individual_count = OrnamentMongo.objects(
                        (Q(user_id__in=member_ids) | Q(created_by__in=member_refs)) & Q(type=img_type)
                    ).count()
                    count += individual_count
            if count > 0:
                images_by_type[img_type] = count

        # Get member count
        member_count = len(organization.members) if organization.members else 0

        # Get recent activity (last 30 days)
        from datetime import timedelta
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_project_images = ImageGenerationHistory.objects(
            project__in=projects,
            created_at__gte=thirty_days_ago
        ).count()
        
        # Get recent individual images (last 30 days)
        recent_individual_images = 0
        if member_ids:
            member_refs = []
            for mid in member_ids:
                user = User.objects(id=mid).first()
                if user:
                    member_refs.append(user)
            if member_refs:
                recent_individual_images = OrnamentMongo.objects(
                    (Q(user_id__in=member_ids) | Q(created_by__in=member_refs)) &
                    Q(created_at__gte=thirty_days_ago)
                ).count()
        
        recent_images = recent_project_images + recent_individual_images

        return JsonResponse({
            'organization_id': str(organization.id),
            'organization_name': organization.name,
            'stats': {
                'total_projects': len(projects),
                'total_images': total_images,
                'project_images': project_images_count,
                'individual_images': individual_images_count,
                'recent_images_30d': recent_images,
                'total_members': member_count,
                'credit_balance': organization.credit_balance,
                'images_by_type': images_by_type
            }
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Get Organization Members
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def get_organization_members(request, organization_id):
    """Get all members of an organization - owner/admin only"""
    try:
        organization = Organization.objects(id=organization_id).first()
        if not organization:
            return JsonResponse({'error': 'Organization not found'}, status=404)

        # Check permission
        if not (is_admin(request.user) or is_organization_owner(request.user, organization)):
            return JsonResponse({'error': 'Only organization owner or admin can view members'}, status=403)

        members_list = []
        for member in organization.members:
            # Get user's project count
            user_projects = Project.objects(organization=organization, created_by=member)
            projects_count = user_projects.count()
            
            # Get user's images count (project-based + individual)
            project_images_count = ImageGenerationHistory.objects(
                project__in=user_projects,
                user_id=str(member.id)
            ).count()
            
            # Get individual images count
            individual_images_count = OrnamentMongo.objects(
                Q(user_id=str(member.id)) | Q(created_by=member)
            ).count()
            
            total_images = project_images_count + individual_images_count
            
            members_list.append({
                'id': str(member.id),
                'email': member.email,
                'full_name': member.full_name or '',
                'username': member.username or '',
                'organization_role': member.organization_role or 'member',
                'created_at': member.created_at.isoformat() if member.created_at else None,
                'projects_count': projects_count,
                'images_generated': total_images
            })
        
        # Also include owner if not in members list
        if organization.owner:
            owner_in_members = any(str(m.id) == str(organization.owner.id) for m in organization.members)
            if not owner_in_members:
                owner = organization.owner
                owner_projects = Project.objects(organization=organization, created_by=owner)
                owner_projects_count = owner_projects.count()
                
                owner_project_images = ImageGenerationHistory.objects(
                    project__in=owner_projects,
                    user_id=str(owner.id)
                ).count()
                
                owner_individual_images = OrnamentMongo.objects(
                    Q(user_id=str(owner.id)) | Q(created_by=owner)
                ).count()
                
                owner_total_images = owner_project_images + owner_individual_images
                
                members_list.append({
                    'id': str(owner.id),
                    'email': owner.email,
                    'full_name': owner.full_name or '',
                    'username': owner.username or '',
                    'organization_role': 'owner',
                    'created_at': owner.created_at.isoformat() if owner.created_at else None,
                    'projects_count': owner_projects_count,
                    'images_generated': owner_total_images
                })

        return JsonResponse({
            'organization_id': str(organization.id),
            'organization_name': organization.name,
            'members': members_list,
            'total_members': len(members_list)
        }, status=200)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
