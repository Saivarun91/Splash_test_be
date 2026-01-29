"""
Plan CRUD views with admin-only access control
"""
from django.http import JsonResponse
from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt
import json
from mongoengine.errors import DoesNotExist, NotUniqueError, ValidationError
from .models import Plan
from users.models import User, Role
from common.middleware import authenticate
from datetime import datetime


def is_admin(user):
    """Check if user is admin"""
    return user.role == Role.ADMIN


# =====================
# List All Plans (Public - for home page and user pages)
# =====================
@api_view(['GET'])
@csrf_exempt
def list_plans(request):
    """List all active plans - public endpoint"""
    try:
        # Get query parameters
        active_only = request.GET.get('active_only', 'false').lower() == 'true'
        
        if active_only:
            plans = Plan.objects(is_active=True).order_by('price')
        else:
            plans = Plan.objects().order_by('price')
        
        plans_data = []
        for plan in plans:
            cs = plan.custom_settings or {}
            # Normalize credit_options for Pro plan: [{amount, credits}, ...]
            credit_options = cs.get('credit_options')
            if not credit_options and (plan.name or '').lower() == 'pro':
                credit_options = [{'amount': 50, 'credits': 50}, {'amount': 100, 'credits': 100}, {'amount': 300, 'credits': 300}]
            plan_dict = {
                'id': str(plan.id),
                'name': plan.name,
                'description': plan.description or '',
                'price': plan.price,
                'original_price': plan.original_price,
                'currency': getattr(plan, 'currency', 'USD'),
                'billing_cycle': plan.billing_cycle,
                'credits_per_month': plan.credits_per_month,
                'max_projects': plan.max_projects,
                'ai_features_enabled': plan.ai_features_enabled,
                'features': plan.features or [],
                'is_active': plan.is_active,
                'is_popular': plan.is_popular,
                'custom_settings': {**cs, 'credit_options': credit_options or cs.get('credit_options')},
                'credit_options': credit_options or cs.get('credit_options') or [],
                'amount_display': cs.get('amount_display', 'As you go'),
                'cta_text': cs.get('cta_text'),
                'created_at': plan.created_at.isoformat() if plan.created_at else None,
                'updated_at': plan.updated_at.isoformat() if plan.updated_at else None,
            }
            plans_data.append(plan_dict)
        
        return JsonResponse({
            'success': True,
            'plans': plans_data,
            'count': len(plans_data)
        }, status=200)
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Get Single Plan (Public)
# =====================
@api_view(['GET'])
@csrf_exempt
def get_plan(request, plan_id):
    """Get single plan details - public endpoint"""
    try:
        plan = Plan.objects.get(id=plan_id)
        cs = plan.custom_settings or {}
        credit_options = cs.get('credit_options')
        if not credit_options and (plan.name or '').lower() == 'pro':
            credit_options = [{'amount': 50, 'credits': 50}, {'amount': 100, 'credits': 100}, {'amount': 300, 'credits': 300}]
        plan_dict = {
            'id': str(plan.id),
            'name': plan.name,
            'description': plan.description or '',
            'price': plan.price,
            'original_price': plan.original_price,
            'currency': getattr(plan, 'currency', 'USD'),
            'billing_cycle': plan.billing_cycle,
            'credits_per_month': plan.credits_per_month,
            'max_projects': plan.max_projects,
            'ai_features_enabled': plan.ai_features_enabled,
            'features': plan.features or [],
            'is_active': plan.is_active,
            'is_popular': plan.is_popular,
            'custom_settings': {**cs, 'credit_options': credit_options or cs.get('credit_options')},
            'credit_options': credit_options or cs.get('credit_options') or [],
            'amount_display': cs.get('amount_display', 'As you go'),
            'cta_text': cs.get('cta_text'),
            'created_at': plan.created_at.isoformat() if plan.created_at else None,
            'updated_at': plan.updated_at.isoformat() if plan.updated_at else None,
        }
        
        return JsonResponse({
            'success': True,
            'plan': plan_dict
        }, status=200)
    
    except DoesNotExist:
        return JsonResponse({'error': 'Plan not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Admin-only: Create Plan
# =====================
@api_view(['POST'])
@csrf_exempt
@authenticate
def create_plan(request):
    """Only admin can create plans"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can create plans'}, status=403)
    
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        name = data.get('name')
        price = data.get('price')
        
        if not name:
            return JsonResponse({'error': 'Plan name is required'}, status=400)
        if price is None:
            return JsonResponse({'error': 'Plan price is required'}, status=400)
        
        # Check if plan name already exists
        if Plan.objects(name=name).first():
            return JsonResponse({'error': 'Plan with this name already exists'}, status=400)
        
        # Create plan
        plan = Plan(
            name=name,
            description=data.get('description', ''),
            price=float(price),
            original_price=float(data.get('original_price')) if data.get('original_price') else None,
            currency=data.get('currency', 'USD'),
            billing_cycle=data.get('billing_cycle', 'monthly'),
            credits_per_month=int(data.get('credits_per_month', 1000)),
            max_projects=int(data.get('max_projects', 10)),
            ai_features_enabled=data.get('ai_features_enabled', True),
            features=data.get('features', []),
            is_active=data.get('is_active', True),
            is_popular=data.get('is_popular', False),
            custom_settings=data.get('custom_settings', {}),
            created_by=request.user,
            updated_by=request.user,
        )
        plan.save()
        
        plan_dict = {
            'id': str(plan.id),
            'name': plan.name,
            'description': plan.description or '',
            'price': plan.price,
            'original_price': plan.original_price,
            'currency': getattr(plan, 'currency', 'USD'),
            'billing_cycle': plan.billing_cycle,
            'credits_per_month': plan.credits_per_month,
            'max_projects': plan.max_projects,
            'ai_features_enabled': plan.ai_features_enabled,
            'features': plan.features or [],
            'is_active': plan.is_active,
            'is_popular': plan.is_popular,
            'created_at': plan.created_at.isoformat() if plan.created_at else None,
            'updated_at': plan.updated_at.isoformat() if plan.updated_at else None,
        }
        
        return JsonResponse({
            'success': True,
            'message': 'Plan created successfully',
            'plan': plan_dict
        }, status=201)
    
    except NotUniqueError:
        return JsonResponse({'error': 'Plan with this name already exists'}, status=400)
    except ValidationError as e:
        return JsonResponse({'error': f'Validation error: {str(e)}'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Admin-only: Update Plan
# =====================
@api_view(['PUT'])
@csrf_exempt
@authenticate
def update_plan(request, plan_id):
    """Only admin can update plans"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can update plans'}, status=403)
    
    try:
        plan = Plan.objects.get(id=plan_id)
        data = json.loads(request.body)
        
        # Update fields
        if 'name' in data:
            # Check if new name conflicts with existing plan
            existing_plan = Plan.objects(name=data['name']).first()
            if existing_plan and str(existing_plan.id) != str(plan_id):
                return JsonResponse({'error': 'Plan with this name already exists'}, status=400)
            plan.name = data['name']
        
        if 'description' in data:
            plan.description = data['description']
        
        if 'price' in data:
            plan.price = float(data['price'])
        
        if 'original_price' in data:
            plan.original_price = float(data['original_price']) if data['original_price'] else None
        
        if 'currency' in data:
            plan.currency = data['currency']
        
        if 'billing_cycle' in data:
            plan.billing_cycle = data['billing_cycle']
        
        if 'credits_per_month' in data:
            plan.credits_per_month = int(data['credits_per_month'])
        
        if 'max_projects' in data:
            plan.max_projects = int(data['max_projects'])
        
        if 'ai_features_enabled' in data:
            plan.ai_features_enabled = bool(data['ai_features_enabled'])
        
        if 'features' in data:
            plan.features = data['features']
        
        if 'is_active' in data:
            plan.is_active = bool(data['is_active'])
        
        if 'is_popular' in data:
            plan.is_popular = bool(data['is_popular'])
        
        if 'custom_settings' in data:
            plan.custom_settings = data['custom_settings']
        
        plan.updated_by = request.user
        plan.updated_at = datetime.utcnow()
        plan.save()
        
        plan_dict = {
            'id': str(plan.id),
            'name': plan.name,
            'description': plan.description or '',
            'price': plan.price,
            'original_price': plan.original_price,
            'currency': getattr(plan, 'currency', 'USD'),
            'billing_cycle': plan.billing_cycle,
            'credits_per_month': plan.credits_per_month,
            'max_projects': plan.max_projects,
            'ai_features_enabled': plan.ai_features_enabled,
            'features': plan.features or [],
            'is_active': plan.is_active,
            'is_popular': plan.is_popular,
            'created_at': plan.created_at.isoformat() if plan.created_at else None,
            'updated_at': plan.updated_at.isoformat() if plan.updated_at else None,
        }
        
        return JsonResponse({
            'success': True,
            'message': 'Plan updated successfully',
            'plan': plan_dict
        }, status=200)
    
    except DoesNotExist:
        return JsonResponse({'error': 'Plan not found'}, status=404)
    except NotUniqueError:
        return JsonResponse({'error': 'Plan with this name already exists'}, status=400)
    except ValidationError as e:
        return JsonResponse({'error': f'Validation error: {str(e)}'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Admin-only: Delete Plan
# =====================
@api_view(['DELETE'])
@csrf_exempt
@authenticate
def delete_plan(request, plan_id):
    """Only admin can delete plans"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can delete plans'}, status=403)
    
    try:
        plan = Plan.objects.get(id=plan_id)
        plan_name = plan.name
        plan.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Plan "{plan_name}" deleted successfully'
        }, status=200)
    
    except DoesNotExist:
        return JsonResponse({'error': 'Plan not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
