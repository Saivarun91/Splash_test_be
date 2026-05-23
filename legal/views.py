"""
Legal Compliance API views
Admin-only endpoints for managing legal compliance documents
"""
from django.http import JsonResponse
from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt
import json
from mongoengine.errors import DoesNotExist, ValidationError
from .models import LegalCompliance
from users.models import User, Role
from common.middleware import authenticate
from datetime import datetime


def is_admin(user):
    """Check if user is admin"""
    return user.role == Role.ADMIN


# =====================
# Get All Legal Content
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def get_all_legal_content(request):
    """
    Get all legal compliance content (terms, privacy, gdpr)
    Admin-only endpoint
    """
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can access legal content'}, status=403)
    
    try:
        # Get all legal compliance documents
        legal_docs = LegalCompliance.objects()
        
        # Organize by content_type
        content_dict = {}
        for doc in legal_docs:
            content_dict[doc.content_type] = {
                'title': doc.title,
                'content': doc.content,
                'version': doc.version,
                'created_at': doc.created_at.isoformat() if doc.created_at else None,
                'updated_at': doc.updated_at.isoformat() if doc.updated_at else None,
            }
        
        # Ensure all content types exist (with defaults if not found)
        for content_type in ['terms', 'privacy', 'gdpr']:
            if content_type not in content_dict:
                content_dict[content_type] = {
                    'title': '',
                    'content': '',
                    'version': '1.0',
                    'created_at': None,
                    'updated_at': None,
                }
        
        return JsonResponse({
            'success': True,
            'content': content_dict
        }, status=200)
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =====================
# Update Legal Content
# =====================
@api_view(['PUT'])
@csrf_exempt
@authenticate
def update_legal_content(request, content_type):
    """
    Update legal compliance content for a specific type
    Admin-only endpoint
    
    Args:
        content_type: 'terms', 'privacy', or 'gdpr'
    """
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can update legal content'}, status=403)
    
    # Validate content_type
    if content_type not in ['terms', 'privacy', 'gdpr']:
        return JsonResponse({
            'success': False,
            'error': f'Invalid content_type. Must be one of: terms, privacy, gdpr'
        }, status=400)
    
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        title = data.get('title', '')
        content = data.get('content', '')
        version = data.get('version', '1.0')
        
        # Try to get existing document
        try:
            legal_doc = LegalCompliance.objects.get(content_type=content_type)
            # Update existing document
            legal_doc.title = title
            legal_doc.content = content
            legal_doc.version = version
            legal_doc.updated_at = datetime.utcnow()
            legal_doc.save()
        except DoesNotExist:
            # Create new document if it doesn't exist
            legal_doc = LegalCompliance(
                content_type=content_type,
                title=title,
                content=content,
                version=version,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            legal_doc.save()
        
        return JsonResponse({
            'success': True,
            'message': f'{content_type} updated successfully',
            'version': legal_doc.version,
            'content': {
                'title': legal_doc.title,
                'content': legal_doc.content,
                'version': legal_doc.version,
                'updated_at': legal_doc.updated_at.isoformat() if legal_doc.updated_at else None,
            }
        }, status=200)
    
    except ValidationError as e:
        return JsonResponse({
            'success': False,
            'error': f'Validation error: {str(e)}'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =====================
# Get Single Legal Content (Public endpoint for frontend display)
# =====================
@api_view(['GET'])
@csrf_exempt
def get_legal_content(request, content_type):
    """
    Get legal compliance content for a specific type
    Public endpoint - can be used by frontend to display legal pages
    """
    # Validate content_type
    if content_type not in ['terms', 'privacy', 'gdpr']:
        return JsonResponse({
            'success': False,
            'error': f'Invalid content_type. Must be one of: terms, privacy, gdpr'
        }, status=400)
    
    try:
        legal_doc = LegalCompliance.objects.get(content_type=content_type)
        
        return JsonResponse({
            'success': True,
            'content': {
                'title': legal_doc.title,
                'content': legal_doc.content,
                'version': legal_doc.version,
                'updated_at': legal_doc.updated_at.isoformat() if legal_doc.updated_at else None,
            }
        }, status=200)
    
    except DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': f'{content_type} content not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
