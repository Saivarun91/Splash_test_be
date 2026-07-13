"""
Plan CRUD views with admin-only access control
"""
from django.http import JsonResponse
from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt
import json
from mongoengine.errors import DoesNotExist, NotUniqueError, ValidationError
from .models import Plan
from .pricing_helpers import (
    apply_pricing_payload,
    get_pricing_plans_queryset,
    seed_pricing_plans_if_empty,
    serialize_pricing_plan,
    DEFAULT_FOOTER_NOTE,
)
from users.models import User, Role
from common.middleware import authenticate
from datetime import datetime
from invoices.models import InvoiceConfig


def _get_tax_config_dict():
    config = InvoiceConfig.objects.first()
    if not config:
        config = InvoiceConfig()
        config.save()
    countries = getattr(config, "gst_enabled_countries", None) or ["India"]
    return {
        "tax_rate": float(config.tax_rate or 18.0),
        "cgst_rate": float(getattr(config, "cgst_rate", None) or 9.0),
        "sgst_rate": float(getattr(config, "sgst_rate", None) or 9.0),
        "home_state": getattr(config, "home_state", None) or "Telangana",
        "gst_enabled_countries": countries,
        "pricing_footer_note": getattr(config, "pricing_footer_note", None) or DEFAULT_FOOTER_NOTE,
    }


# =====================
# Public pricing cards (Starter / Growth / Custom)
# =====================
@api_view(['GET'])
@csrf_exempt
def list_pricing_plans(request):
    """List active public pricing cards for marketing and checkout."""
    try:
        seed_pricing_plans_if_empty()
        active_only = request.GET.get('active_only', 'true').lower() != 'false'
        plans = get_pricing_plans_queryset(active_only=active_only)
        tax_config = _get_tax_config_dict()
        return JsonResponse({
            'success': True,
            'plans': [serialize_pricing_plan(p) for p in plans],
            'tax_config': {
                'tax_rate': tax_config['tax_rate'],
                'cgst_rate': tax_config['cgst_rate'],
                'sgst_rate': tax_config['sgst_rate'],
                'home_state': tax_config['home_state'],
                'gst_enabled_countries': tax_config['gst_enabled_countries'],
            },
            'footer_note': tax_config['pricing_footer_note'],
            'count': len(plans),
        }, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['POST'])
@csrf_exempt
@authenticate
def create_pricing_plan(request):
    """Admin: create a public pricing card."""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can create pricing plans'}, status=403)
    try:
        data = json.loads(request.body)
        name = data.get('name')
        if not name:
            return JsonResponse({'error': 'Plan name is required'}, status=400)
        if Plan.objects(name=name).first():
            return JsonResponse({'error': 'Plan with this name already exists'}, status=400)
        slug = data.get('slug')
        if slug and Plan.objects(slug=slug).first():
            return JsonResponse({'error': 'Plan with this slug already exists'}, status=400)

        plan = Plan(
            name=name,
            price=float(data.get('price', 0) or 0),
            plan_type='pricing',
            slug=slug or name.lower().replace(' ', '-'),
            created_by=request.user,
            updated_by=request.user,
        )
        apply_pricing_payload(plan, data, request.user)
        plan.save()
        return JsonResponse({
            'success': True,
            'message': 'Pricing plan created',
            'plan': serialize_pricing_plan(plan),
        }, status=201)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['PUT'])
@csrf_exempt
@authenticate
def update_pricing_plan(request, plan_id):
    """Admin: update a public pricing card."""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can update pricing plans'}, status=403)
    try:
        plan = Plan.objects.get(id=plan_id)
        data = json.loads(request.body)
        if 'name' in data:
            existing = Plan.objects(name=data['name']).first()
            if existing and str(existing.id) != str(plan_id):
                return JsonResponse({'error': 'Plan with this name already exists'}, status=400)
        if 'slug' in data and data['slug']:
            existing_slug = Plan.objects(slug=data['slug']).first()
            if existing_slug and str(existing_slug.id) != str(plan_id):
                return JsonResponse({'error': 'Plan with this slug already exists'}, status=400)
        apply_pricing_payload(plan, data, request.user)
        plan.save()
        return JsonResponse({
            'success': True,
            'message': 'Pricing plan updated',
            'plan': serialize_pricing_plan(plan),
        }, status=200)
    except DoesNotExist:
        return JsonResponse({'error': 'Plan not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['DELETE'])
@csrf_exempt
@authenticate
def delete_pricing_plan(request, plan_id):
    """Admin: delete a public pricing card."""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can delete pricing plans'}, status=403)
    try:
        plan = Plan.objects.get(id=plan_id)
        plan.delete()
        return JsonResponse({'success': True, 'message': 'Pricing plan deleted'}, status=200)
    except DoesNotExist:
        return JsonResponse({'error': 'Plan not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['PUT'])
@csrf_exempt
@authenticate
def update_pricing_tax_config(request):
    """Admin: update GST settings used on pricing/checkout pages."""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can update tax configuration'}, status=403)
    try:
        data = json.loads(request.body)
        config = InvoiceConfig.objects.first()
        if not config:
            config = InvoiceConfig()
        if 'tax_rate' in data:
            config.tax_rate = float(data['tax_rate'])
        if 'cgst_rate' in data:
            config.cgst_rate = float(data['cgst_rate'])
        if 'sgst_rate' in data:
            config.sgst_rate = float(data['sgst_rate'])
        if 'home_state' in data:
            config.home_state = data['home_state']
        if 'gst_enabled_countries' in data:
            config.gst_enabled_countries = data['gst_enabled_countries']
        if 'pricing_footer_note' in data:
            config.pricing_footer_note = data['pricing_footer_note']
        config.save()
        return JsonResponse({'success': True, 'tax_config': _get_tax_config_dict()}, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


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
