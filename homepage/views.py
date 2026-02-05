"""
Homepage Content API views
Admin-only endpoints for managing homepage content (Before/After images)
"""
from django.http import JsonResponse
from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt
import json
import os
from mongoengine.errors import DoesNotExist, ValidationError
from .models import BeforeAfterImage
from users.models import User, Role
from common.middleware import authenticate
from datetime import datetime
from django.conf import settings
import cloudinary.uploader


def is_admin(user):
    """Check if user is admin"""
    return user.role == Role.ADMIN


# =====================
# Get All Before/After Images
# =====================
@api_view(['GET'])
@csrf_exempt
def get_before_after_images(request):
    """
    Get all before/after images
    Public endpoint - can be used by frontend to display images
    """
    try:
        # Get all active images ordered by order field
        images = BeforeAfterImage.objects(is_active='true').order_by('order', '-created_at')
        
        image_list = []
        for img in images:
            image_list.append({
                'id': str(img.id),
                'before_image_url': img.before_image_url,
                'after_image_url': img.after_image_url,
                'order': img.order,
                'created_at': img.created_at.isoformat() if img.created_at else None,
                'updated_at': img.updated_at.isoformat() if img.updated_at else None,
            })
        
        return JsonResponse({
            'success': True,
            'images': image_list
        }, status=200)
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =====================
# Get All Before/After Images (Admin)
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def get_all_before_after_images(request):
    """
    Get all before/after images including inactive ones
    Admin-only endpoint
    """
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can access this endpoint'}, status=403)
    
    try:
        # Get all images ordered by order field
        images = BeforeAfterImage.objects().order_by('order', '-created_at')
        
        image_list = []
        for img in images:
            image_list.append({
                'id': str(img.id),
                'before_image_url': img.before_image_url,
                'after_image_url': img.after_image_url,
                'before_image_path': img.before_image_path or '',
                'after_image_path': img.after_image_path or '',
                'order': img.order,
                'is_active': img.is_active,
                'created_at': img.created_at.isoformat() if img.created_at else None,
                'updated_at': img.updated_at.isoformat() if img.updated_at else None,
            })
        
        return JsonResponse({
            'success': True,
            'images': image_list
        }, status=200)
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =====================
# Upload Before/After Images
# =====================
@api_view(['POST'])
@csrf_exempt
@authenticate
def upload_before_after_images(request):
    """
    Upload before/after image pairs
    Admin-only endpoint
    Expects: multipart/form-data with 'before_image' and 'after_image' files
    """
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can upload images'}, status=403)
    
    try:
        before_file = request.FILES.get('before_image')
        after_file = request.FILES.get('after_image')
        
        if not before_file or not after_file:
            return JsonResponse({
                'success': False,
                'error': 'Both before_image and after_image are required'
            }, status=400)
        
        # Get the highest order number
        max_order = 0
        existing_images = BeforeAfterImage.objects()
        if existing_images:
            max_order = max([img.order for img in existing_images] or [0])
        
        # Upload to Cloudinary
        before_upload = cloudinary.uploader.upload(
            before_file,
            folder="homepage/before_after",
            overwrite=True
        )
        before_url = before_upload.get("secure_url")
        
        after_upload = cloudinary.uploader.upload(
            after_file,
            folder="homepage/before_after",
            overwrite=True
        )
        after_url = after_upload.get("secure_url")
        
        # Save locally (optional)
        local_dir = os.path.join(settings.MEDIA_ROOT, "homepage", "before_after")
        os.makedirs(local_dir, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        before_filename = f"before_{timestamp}_{before_file.name}"
        after_filename = f"after_{timestamp}_{after_file.name}"
        
        before_path = os.path.join(local_dir, before_filename)
        after_path = os.path.join(local_dir, after_filename)
        
        with open(before_path, "wb") as f:
            for chunk in before_file.chunks():
                f.write(chunk)
        
        with open(after_path, "wb") as f:
            for chunk in after_file.chunks():
                f.write(chunk)
        
        # Create database entry
        before_after_image = BeforeAfterImage(
            before_image_url=before_url,
            after_image_url=after_url,
            before_image_path=before_path,
            after_image_path=after_path,
            order=max_order + 1,
            is_active='true',
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        before_after_image.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Images uploaded successfully',
            'image': {
                'id': str(before_after_image.id),
                'before_image_url': before_after_image.before_image_url,
                'after_image_url': before_after_image.after_image_url,
                'order': before_after_image.order,
                'is_active': before_after_image.is_active,
            }
        }, status=200)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =====================
# Update Before/After Image
# =====================
@api_view(['PUT'])
@csrf_exempt
@authenticate
def update_before_after_image(request, image_id):
    """
    Update a before/after image (order, is_active)
    Admin-only endpoint
    """
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can update images'}, status=403)
    
    try:
        data = json.loads(request.body)
        
        before_after_image = BeforeAfterImage.objects.get(id=image_id)
        
        # Update order if provided
        if 'order' in data:
            before_after_image.order = int(data['order'])
        
        # Update is_active if provided
        if 'is_active' in data:
            before_after_image.is_active = str(data['is_active']).lower()
        
        before_after_image.updated_at = datetime.utcnow()
        before_after_image.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Image updated successfully',
            'image': {
                'id': str(before_after_image.id),
                'before_image_url': before_after_image.before_image_url,
                'after_image_url': before_after_image.after_image_url,
                'order': before_after_image.order,
                'is_active': before_after_image.is_active,
            }
        }, status=200)
    
    except DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Image not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =====================
# Delete Before/After Image
# =====================
@api_view(['DELETE'])
@csrf_exempt
@authenticate
def delete_before_after_image(request, image_id):
    """
    Delete a before/after image
    Admin-only endpoint
    """
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can delete images'}, status=403)
    
    try:
        before_after_image = BeforeAfterImage.objects.get(id=image_id)
        before_after_image.delete()
        
        return JsonResponse({
            'success': True,
            'message': 'Image deleted successfully'
        }, status=200)
    
    except DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Image not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
