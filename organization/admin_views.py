"""
Admin-specific API views for dashboard and analytics
"""
from django.http import JsonResponse
from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt
from common.middleware import authenticate
from .models import Organization
from users.models import User, Role
from CREDITS.models import CreditLedger
from probackendapp.models import Project, Collection, ImageGenerationHistory
from datetime import datetime, timedelta
from mongoengine import Q


def is_admin(user):
    """Check if user is admin"""
    return user.role == Role.ADMIN


# =====================
# Admin Dashboard Stats
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def admin_dashboard_stats(request):
    """Get dashboard statistics for admin - only admin can access"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can access dashboard stats'}, status=403)
    
    try:
        # Get time range parameter (default: last 30 days)
        time_range = request.GET.get('range', '30')
        try:
            days = int(time_range)
        except:
            days = 30
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Total Organizations
        total_organizations = Organization.objects.count()
        
        # Total Users
        total_users = User.objects.count()
        
        # Total Credits (sum of all organization credit balances)
        organizations = Organization.objects.all()
        total_credits = sum(org.credit_balance for org in organizations)
        
        # Active Subscriptions (organizations with credit balance > 0)
        active_subscriptions = Organization.objects(credit_balance__gt=0).count()
        
        # Total Images Generated (from ImageGenerationHistory)
        # Count images generated in the time range
        image_history = ImageGenerationHistory.objects(
            created_at__gte=start_date,
            created_at__lte=end_date
        )
        total_images = image_history.count()
        
        # Calculate growth rate (compare with previous period)
        prev_start_date = start_date - timedelta(days=days)
        prev_image_history = ImageGenerationHistory.objects(
            created_at__gte=prev_start_date,
            created_at__lt=start_date
        )
        prev_total_images = prev_image_history.count()
        
        if prev_total_images > 0:
            growth_rate = ((total_images - prev_total_images) / prev_total_images) * 100
        else:
            growth_rate = 0 if total_images == 0 else 100
        
        return JsonResponse({
            'success': True,
            'stats': {
                'totalOrganizations': total_organizations,
                'totalUsers': total_users,
                'totalImages': total_images,
                'totalCredits': total_credits,
                'activeSubscriptions': active_subscriptions,
                'growthRate': round(growth_rate, 2)
            },
            'timeRange': {
                'days': days,
                'startDate': start_date.isoformat(),
                'endDate': end_date.isoformat()
            }
        }, status=200)
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Admin Dashboard Image Generation Data
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def admin_dashboard_images(request):
    """Get image generation data for charts - only admin can access"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can access dashboard images'}, status=403)
    
    try:
        range_type = request.GET.get('range', 'day')  # day, week, month
        
        end_date = datetime.utcnow()
        
        if range_type == 'day':
            # Last 7 days
            start_date = end_date - timedelta(days=7)
            data = []
            current = start_date
            while current <= end_date:
                day_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start + timedelta(days=1)
                
                count = ImageGenerationHistory.objects(
                    created_at__gte=day_start,
                    created_at__lt=day_end
                ).count()
                
                data.append({
                    'date': day_start.strftime('%Y-%m-%d'),
                    'count': count
                })
                current += timedelta(days=1)
        
        elif range_type == 'week':
            # Last 4 weeks
            start_date = end_date - timedelta(weeks=4)
            data = []
            current = start_date
            week_num = 1
            while current <= end_date:
                week_end = min(current + timedelta(weeks=1), end_date)
                
                count = ImageGenerationHistory.objects(
                    created_at__gte=current,
                    created_at__lt=week_end
                ).count()
                
                data.append({
                    'week': f'Week {week_num}',
                    'images': count
                })
                current = week_end
                week_num += 1
        
        else:  # month
            # Last 6 months
            start_date = end_date - timedelta(days=180)
            data = []
            current = start_date
            month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            month_count = {}
            
            # Group by month
            image_history = ImageGenerationHistory.objects(
                created_at__gte=start_date,
                created_at__lte=end_date
            )
            
            for entry in image_history:
                if entry.created_at:
                    month_key = entry.created_at.strftime('%Y-%m')
                    if month_key not in month_count:
                        month_count[month_key] = 0
                    month_count[month_key] += 1
            
            # Format data
            for month_key in sorted(month_count.keys()):
                month_date = datetime.strptime(month_key, '%Y-%m')
                data.append({
                    'month': month_names[month_date.month - 1],
                    'images': month_count[month_key]
                })
        
        return JsonResponse({
            'success': True,
            'range': range_type,
            'data': data
        }, status=200)
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Admin Dashboard All Chart Data (Day, Week, Month)
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def admin_dashboard_all_charts(request):
    """Get all chart data (daily, weekly, monthly) for dashboard - only admin can access"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can access dashboard charts'}, status=403)
    
    try:
        end_date = datetime.utcnow()
        
        # Daily data - Last 7 days
        daily_start = end_date - timedelta(days=7)
        daily_data = []
        current = daily_start
        while current <= end_date:
            day_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            
            count = ImageGenerationHistory.objects(
                created_at__gte=day_start,
                created_at__lt=day_end
            ).count()
            
            daily_data.append({
                'date': day_start.strftime('%Y-%m-%d'),
                'count': count
            })
            current += timedelta(days=1)
        
        # Weekly data - Last 4 weeks
        weekly_start = end_date - timedelta(weeks=4)
        weekly_data = []
        current = weekly_start
        week_num = 1
        while current <= end_date:
            week_end = min(current + timedelta(weeks=1), end_date)
            
            count = ImageGenerationHistory.objects(
                created_at__gte=current,
                created_at__lt=week_end
            ).count()
            
            weekly_data.append({
                'week': f'Week {week_num}',
                'images': count
            })
            current = week_end
            week_num += 1
        
        # Monthly data - Last 6 months
        monthly_start = end_date - timedelta(days=180)
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        month_count = {}
        
        image_history = ImageGenerationHistory.objects(
            created_at__gte=monthly_start,
            created_at__lte=end_date
        )
        
        for entry in image_history:
            if entry.created_at:
                month_key = entry.created_at.strftime('%Y-%m')
                if month_key not in month_count:
                    month_count[month_key] = 0
                month_count[month_key] += 1
        
        monthly_data = []
        for month_key in sorted(month_count.keys()):
            month_date = datetime.strptime(month_key, '%Y-%m')
            monthly_data.append({
                'month': month_names[month_date.month - 1],
                'images': month_count[month_key]
            })
        
        return JsonResponse({
            'success': True,
            'daily': daily_data,
            'weekly': weekly_data,
            'monthly': monthly_data
        }, status=200)
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

