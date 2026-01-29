"""
Credit usage tracking views
"""
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt
from .models import CreditLedger, CreditSettings
from organization.models import Organization
from users.models import User, Role
from common.middleware import authenticate
from datetime import datetime, timedelta
from mongoengine import Q
import json
from collections import defaultdict


def is_admin(user):
    """Check if user is admin"""
    return user.role == Role.ADMIN


def is_organization_member(user, organization):
    """Check if user is a member of the organization"""
    if not user.organization:
        return False
    return str(user.organization.id) == str(organization.id)


# =====================
# Organization Credit Usage (for organization members)
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def organization_credit_usage(request, organization_id):
    """
    Get credit usage for an organization in tabular format.
    Only organization members or admin can view.
    """
    try:
        organization = Organization.objects(id=organization_id).first()
        if not organization:
            return JsonResponse({'error': 'Organization not found'}, status=404)
        
        # Check permission
        if not (is_admin(request.user) or is_organization_member(request.user, organization)):
            return JsonResponse({'error': 'You do not have permission to view this organization\'s credit usage'}, status=403)
        
        # Get query parameters
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        change_type = request.GET.get('change_type')  # 'debit', 'credit', or None for all
        
        # Build query
        query = Q(organization=organization)
        
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                query &= Q(created_at__gte=start_dt)
            except:
                pass
        
        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                query &= Q(created_at__lte=end_dt)
            except:
                pass
        
        if change_type and change_type in ['debit', 'credit']:
            query &= Q(change_type=change_type)
        
        # Get ledger entries
        ledger_entries = CreditLedger.objects(query).order_by('-created_at')
        
        # Format response
        usage_data = []
        total_debits = 0
        total_credits = 0
        
        for entry in ledger_entries:
            usage_data.append({
                'id': str(entry.id),
                'date': entry.created_at.isoformat() if entry.created_at else None,
                'change_type': entry.change_type,
                'credits_changed': entry.credits_changed,
                'balance_after': entry.balance_after,
                'reason': entry.reason,
                'user_email': entry.user.email if entry.user else None,
                'project_id': str(entry.project.id) if entry.project else None,
                'metadata': entry.metadata or {}
            })
            
            if entry.change_type == 'debit':
                total_debits += entry.credits_changed
            else:
                total_credits += entry.credits_changed
        
        return JsonResponse({
            'organization': {
                'id': str(organization.id),
                'name': organization.name,
                'current_balance': organization.credit_balance
            },
            'summary': {
                'total_debits': total_debits,
                'total_credits': total_credits,
                'net_usage': total_debits - total_credits,
                'entry_count': len(usage_data)
            },
            'usage_data': usage_data
        }, status=200)
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# All Organizations Credit Usage (Admin only)
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def all_organizations_credit_usage(request):
    """
    Get credit usage for all organizations in tabular format.
    Admin only.
    Optimized to only return summary data by default (summary_only=true).
    Set summary_only=false to include full usage_data (slower).
    """
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can view all organizations credit usage'}, status=403)
    
    try:
        # Get query parameters
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        organization_id = request.GET.get('organization_id')
        summary_only = request.GET.get('summary_only', 'true').lower() == 'true'
        
        # Get all organizations
        if organization_id:
            organizations = Organization.objects(id=organization_id)
        else:
            organizations = Organization.objects.all()
        
        organizations_data = []
        
        for organization in organizations:
            # Build query for this organization
            query = Q(organization=organization)
            
            if start_date:
                try:
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    query &= Q(created_at__gte=start_dt)
                except:
                    pass
            
            if end_date:
                try:
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    query &= Q(created_at__lte=end_dt)
                except:
                    pass
            
            # Optimized: Use aggregation to calculate totals without loading all entries
            if summary_only:
                # Use efficient query with only() to fetch minimal data
                ledger_entries = CreditLedger.objects(query).only('change_type', 'credits_changed')
                
                # Calculate totals efficiently
                total_debits = 0
                total_credits = 0
                entry_count = 0
                
                for entry in ledger_entries:
                    entry_count += 1
                    if entry.change_type == 'debit':
                        total_debits += entry.credits_changed
                    else:
                        total_credits += entry.credits_changed
                
                usage_entries = []
            else:
                # Legacy: Load all entries (slower, only if summary_only=false)
                ledger_entries = CreditLedger.objects(query).order_by('-created_at')
                
                # Calculate totals
                total_debits = 0
                total_credits = 0
                usage_entries = []
                
                for entry in ledger_entries:
                    usage_entries.append({
                        'id': str(entry.id),
                        'date': entry.created_at.isoformat() if entry.created_at else None,
                        'change_type': entry.change_type,
                        'credits_changed': entry.credits_changed,
                        'balance_after': entry.balance_after,
                        'reason': entry.reason,
                        'user_email': entry.user.email if entry.user else None,
                        'project_id': str(entry.project.id) if entry.project else None,
                        'metadata': entry.metadata or {}
                    })
                    
                    if entry.change_type == 'debit':
                        total_debits += entry.credits_changed
                    else:
                        total_credits += entry.credits_changed
                
                entry_count = len(usage_entries)
            
            organizations_data.append({
                'organization': {
                    'id': str(organization.id),
                    'name': organization.name,
                    'owner_email': organization.owner.email if organization.owner else None,
                    'current_balance': organization.credit_balance,
                    'member_count': len(organization.members) if organization.members else 0
                },
                'summary': {
                    'total_debits': total_debits,
                    'total_credits': total_credits,
                    'net_usage': total_debits - total_credits,
                    'entry_count': entry_count
                },
                'usage_data': usage_entries if not summary_only else []
            })
        
        # Calculate overall summary
        overall_debits = sum(org['summary']['total_debits'] for org in organizations_data)
        overall_credits = sum(org['summary']['total_credits'] for org in organizations_data)
        
        return JsonResponse({
            'overall_summary': {
                'total_organizations': len(organizations_data),
                'total_debits': overall_debits,
                'total_credits': overall_credits,
                'net_usage': overall_debits - overall_credits
            },
            'organizations': organizations_data
        }, status=200)
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# User Credit Usage (single user, not scoped to organization)
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def user_credit_usage(request):
    """
    Return credit ledger entries for the current user (both org and personal),
    mainly for showing a simple credits deduction log on the frontend.
    """
    try:
        user = request.user
        # Most recent first
        ledger_entries = CreditLedger.objects(user=user).order_by('-created_at')[:200]

        entries = []
        for entry in ledger_entries:
            entries.append({
                'id': str(entry.id),
                'created_at': entry.created_at.isoformat() if entry.created_at else None,
                'change_type': entry.change_type,
                'credits_changed': entry.credits_changed,
                'balance_after': entry.balance_after,
                'reason': entry.reason,
            })

        return JsonResponse({'entries': entries}, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Organization Credit Summary (Quick stats)
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def organization_credit_summary(request, organization_id):
    """
    Get quick credit summary for an organization.
    """
    try:
        organization = Organization.objects(id=organization_id).first()
        if not organization:
            return JsonResponse({'error': 'Organization not found'}, status=404)
        
        # Check permission
        if not (is_admin(request.user) or is_organization_member(request.user, organization)):
            return JsonResponse({'error': 'You do not have permission to view this organization'}, status=403)
        
        # Get date range (default: last 30 days)
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)
        
        # Get ledger entries for last 30 days
        recent_entries = CreditLedger.objects(
            organization=organization,
            created_at__gte=start_date,
            created_at__lte=end_date
        )
        
        total_debits = sum(entry.credits_changed for entry in recent_entries if entry.change_type == 'debit')
        total_credits = sum(entry.credits_changed for entry in recent_entries if entry.change_type == 'credit')
        
        return JsonResponse({
            'organization': {
                'id': str(organization.id),
                'name': organization.name,
                'current_balance': organization.credit_balance
            },
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'days': 30
            },
            'summary': {
                'total_debits': total_debits,
                'total_credits': total_credits,
                'net_usage': total_debits - total_credits,
                'transaction_count': len(recent_entries)
            }
        }, status=200)
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Get Credit Settings (Public - read-only)
# =====================
@api_view(['GET'])
@csrf_exempt
def get_credit_settings_public(request):
    """Get current credit deduction settings - public read-only endpoint"""
    try:
        settings = CreditSettings.get_settings()
        return JsonResponse({
            'success': True,
            'settings': {
                'credits_per_image_generation': settings.credits_per_image_generation,
                'credits_per_regeneration': settings.credits_per_regeneration,
                'default_image_model_name': getattr(
                    settings,
                    'default_image_model_name',
                    'gemini-3-pro-image-preview'
                ),
            }
        }, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Get Credit Settings (Admin only - with metadata)
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def get_credit_settings(request):
    """Get current credit deduction settings - admin only (includes metadata)"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can view credit settings'}, status=403)
    
    try:
        settings = CreditSettings.get_settings()
        return JsonResponse({
            'success': True,
            'settings': {
                'credits_per_image_generation': settings.credits_per_image_generation,
                'credits_per_regeneration': settings.credits_per_regeneration,
                'default_image_model_name': getattr(
                    settings,
                    'default_image_model_name',
                    'gemini-3-pro-image-preview'
                ),
                'updated_at': settings.updated_at.isoformat() if settings.updated_at else None,
                'updated_by': settings.updated_by.email if settings.updated_by else None,
            }
        }, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Update Credit Settings (Admin only)
# =====================
@api_view(['PUT'])
@csrf_exempt
@authenticate
def update_credit_settings(request):
    """Update credit deduction settings - admin only"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can update credit settings'}, status=403)
    
    try:
        data = json.loads(request.body)
        
        credits_per_image = data.get('credits_per_image_generation')
        credits_per_regeneration = data.get('credits_per_regeneration')
        default_image_model_name = data.get('default_image_model_name')
        
        if credits_per_image is None or credits_per_regeneration is None:
            return JsonResponse({'error': 'Both credits_per_image_generation and credits_per_regeneration are required'}, status=400)
        
        if credits_per_image < 0 or credits_per_regeneration < 0:
            return JsonResponse({'error': 'Credit values must be non-negative'}, status=400)
        
        # Get or create settings (singleton)
        settings = CreditSettings.get_settings()
        settings.credits_per_image_generation = int(credits_per_image)
        settings.credits_per_regeneration = int(credits_per_regeneration)
        if default_image_model_name:
            settings.default_image_model_name = str(default_image_model_name)
        settings.updated_by = request.user
        settings.updated_at = datetime.utcnow()
        settings.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Credit settings updated successfully',
            'settings': {
                'credits_per_image_generation': settings.credits_per_image_generation,
                'credits_per_regeneration': settings.credits_per_regeneration,
                'default_image_model_name': getattr(
                    settings,
                    'default_image_model_name',
                    'gemini-3-pro-image-preview'
                ),
                'updated_at': settings.updated_at.isoformat() if settings.updated_at else None,
                'updated_by': settings.updated_by.email if settings.updated_by else None,
            }
        }, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Monthly/Weekly/Daily Credits Usage Statistics (Admin only)
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def credits_usage_statistics(request):
    """
    Get aggregated credit usage statistics by time period (month, week, day).
    Admin only.
    Returns data grouped by time period for charting.
    """
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can view credit usage statistics'}, status=403)
    
    try:
        # Get query parameters
        time_range = request.GET.get('time_range', 'month')  # 'month', 'week', 'day'
        period_count = int(request.GET.get('period_count', '6'))  # Number of periods to return
        
        # Calculate date range based on time_range
        end_date = datetime.utcnow()
        if time_range == 'month':
            start_date = end_date - timedelta(days=period_count * 30)
        elif time_range == 'week':
            start_date = end_date - timedelta(weeks=period_count)
        else:  # day
            start_date = end_date - timedelta(days=period_count)
        
        # Get all ledger entries in the date range
        query = Q(created_at__gte=start_date, created_at__lte=end_date)
        ledger_entries = CreditLedger.objects(query).only('created_at', 'change_type', 'credits_changed')
        
        # Aggregate by time period
        period_data = defaultdict(lambda: {'debit': 0, 'credit': 0})
        
        for entry in ledger_entries:
            if entry.created_at:
                # Format date based on time range
                if time_range == 'month':
                    period_key = entry.created_at.strftime('%Y-%m')
                elif time_range == 'week':
                    # Get week number and year
                    week_num = entry.created_at.isocalendar()[1]
                    year = entry.created_at.year
                    period_key = f"{year}-W{week_num:02d}"
                else:  # day
                    period_key = entry.created_at.strftime('%Y-%m-%d')
                
                if entry.change_type == 'debit':
                    period_data[period_key]['debit'] += entry.credits_changed
                elif entry.change_type == 'credit':
                    period_data[period_key]['credit'] += entry.credits_changed
        
        # Convert to sorted list format for chart
        chart_data = []
        current_date = start_date
        
        # Generate all periods in range (even if no data)
        for i in range(period_count):
            if time_range == 'month':
                period_key = current_date.strftime('%Y-%m')
                display_key = current_date.strftime('%b')
                next_date = current_date + timedelta(days=30)
            elif time_range == 'week':
                week_num = current_date.isocalendar()[1]
                year = current_date.year
                period_key = f"{year}-W{week_num:02d}"
                display_key = f"W{week_num}"
                next_date = current_date + timedelta(weeks=1)
            else:  # day
                period_key = current_date.strftime('%Y-%m-%d')
                display_key = current_date.strftime('%d/%m')
                next_date = current_date + timedelta(days=1)
            
            data = period_data.get(period_key, {'debit': 0, 'credit': 0})
            chart_data.append({
                'period': display_key,
                'debit': data['debit'],
                'credit': data['credit'],
                'total': data['debit'] + data['credit']
            })
            
            current_date = next_date
        
        return JsonResponse({
            'success': True,
            'time_range': time_range,
            'data': chart_data
        }, status=200)
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
