"""
Credit usage tracking views
"""
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt
from .models import CreditLedger
from organization.models import Organization
from users.models import User, Role
from common.middleware import authenticate
from datetime import datetime, timedelta
from mongoengine import Q


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
    """
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can view all organizations credit usage'}, status=403)
    
    try:
        # Get query parameters
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        organization_id = request.GET.get('organization_id')
        
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
            
            # Get ledger entries for this organization
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
                    'entry_count': len(usage_entries)
                },
                'usage_data': usage_entries
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
