"""
Payment views for Razorpay integration
"""
from django.http import JsonResponse
from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt
from common.middleware import authenticate
from organization.models import Organization
from users.models import User, Role
from plans.models import Plan
from .models import PaymentTransaction
from CREDITS.utils import add_credits
import json
import traceback
from django.conf import settings
import hmac
import hashlib
from datetime import datetime, timedelta
from calendar import monthrange


def is_admin(user):
    """Check if user is admin"""
    return user.role == Role.ADMIN

# Import razorpay with error handling
try:
    import razorpay
except ImportError:
    razorpay = None


# Initialize Razorpay client
def get_razorpay_client():
    """Get Razorpay client instance"""
    if razorpay is None:
        raise Exception("Razorpay package not installed. Please install it using: pip install razorpay")
    
    razorpay_key_id = getattr(settings, 'RAZORPAY_KEY_ID', None)
    razorpay_key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', None)
    
    if not razorpay_key_id or not razorpay_key_secret:
        raise Exception("Razorpay credentials not configured. Please set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in your .env file")
    
    return razorpay.Client(auth=(razorpay_key_id, razorpay_key_secret))


def is_organization_owner(user, organization):
    """Check if user is owner of the organization"""
    if not user.organization or str(user.organization.id) != str(organization.id):
        return False
    return user.organization_role == "owner" or str(organization.owner.id) == str(user.id)


# =====================
# Create Razorpay Order
# =====================
@api_view(['POST'])
@csrf_exempt
@authenticate
def create_razorpay_order(request):
    """Create a Razorpay order for credit purchase"""
    try:
        data = json.loads(request.body)
        organization_id = data.get('organization_id')
        amount = float(data.get('amount', 0))
        credits = int(data.get('credits', 0))
        plan_id = data.get('plan_id')  # Optional - for plan subscriptions
        
        if not organization_id or amount <= 0:
            return JsonResponse({'error': 'organization_id and amount are required'}, status=400)
        
        # If plan_id is provided, get plan details
        plan = None
        if plan_id:
            plan = Plan.objects(id=plan_id).first()
            if not plan:
                return JsonResponse({'error': 'Plan not found'}, status=404)
            # Use plan's credits if credits not specified
            if credits <= 0:
                credits = plan.credits_per_month
        
        if credits <= 0:
            return JsonResponse({'error': 'credits are required'}, status=400)
        
        # Get organization
        organization = Organization.objects(id=organization_id).first()
        if not organization:
            return JsonResponse({'error': 'Organization not found'}, status=404)
        
        # Check permission - only owner can purchase credits/plans
        if not is_organization_owner(request.user, organization):
            return JsonResponse({'error': 'Only organization owner can purchase credits/plans'}, status=403)
        
        # Create Razorpay order
        client = get_razorpay_client()
        
        # Generate a shorter receipt ID (max 40 chars for Razorpay)
        # Format: org_<org_id_short>_<timestamp_short>
        org_id_short = str(organization.id)[:8]  # First 8 chars of org ID
        timestamp_short = str(int(datetime.utcnow().timestamp()))[-8:]  # Last 8 digits of timestamp
        receipt_id = f'org_{org_id_short}_{timestamp_short}'
        
        # Ensure receipt is max 40 characters
        if len(receipt_id) > 40:
            receipt_id = receipt_id[:40]
        
        order_notes = {
            'organization_id': str(organization.id),
            'organization_name': organization.name,
            'user_id': str(request.user.id),
            'credits': credits
        }
        
        if plan_id:
            order_notes['plan_id'] = str(plan_id)
            order_notes['plan_name'] = plan.name
        
        order_data = {
            'amount': int(amount * 100),  # Convert to paise
            'currency': 'USD',
            'receipt': receipt_id,
            'notes': order_notes
        }
        
        razorpay_order = client.order.create(data=order_data)
        
        # Create payment transaction record
        payment_transaction = PaymentTransaction(
            organization=organization,
            user=request.user,
            plan=plan,
            amount=amount,
            credits=credits,
            currency=order_data['currency'],
            razorpay_order_id=razorpay_order['id'],
            status='pending',
            metadata=json.dumps({
                'razorpay_order': razorpay_order,
                'created_by': str(request.user.id),
                'plan_id': str(plan_id) if plan_id else None
            })
        )
        payment_transaction.save()
        
        return JsonResponse({
            'success': True,
            'order_id': razorpay_order['id'],
            'amount': amount,
            'currency': 'INR',
            'key_id': getattr(settings, 'RAZORPAY_KEY_ID', ''),
            'credits': credits,
            'organization_id': str(organization.id)
        }, status=200)
        
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"Error in create_razorpay_order: {str(e)}")
        print(f"Traceback: {error_trace}")
        # In production, you might want to hide the traceback
        return JsonResponse({
            'error': str(e),
            'traceback': error_trace if settings.DEBUG else None
        }, status=500)


# =====================
# Verify Razorpay Payment
# =====================
@api_view(['POST'])
@csrf_exempt
@authenticate
def verify_razorpay_payment(request):
    """Verify Razorpay payment and add credits to organization"""
    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')
        payment_id = data.get('payment_id')
        signature = data.get('signature')
        
        if not order_id or not payment_id or not signature:
            return JsonResponse({'error': 'order_id, payment_id, and signature are required'}, status=400)
        
        # Get payment transaction
        payment_transaction = PaymentTransaction.objects(razorpay_order_id=order_id).first()
        if not payment_transaction:
            return JsonResponse({'error': 'Payment transaction not found'}, status=404)
        
        if payment_transaction.status != 'pending':
            return JsonResponse({'error': f'Payment already processed with status: {payment_transaction.status}'}, status=400)
        
        # Verify signature
        razorpay_key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', None)
        if not razorpay_key_secret:
            return JsonResponse({'error': 'Razorpay secret key not configured'}, status=500)
        
        message = f"{order_id}|{payment_id}"
        generated_signature = hmac.new(
            razorpay_key_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        if generated_signature != signature:
            payment_transaction.status = 'failed'
            payment_transaction.save()
            return JsonResponse({'error': 'Invalid payment signature'}, status=400)
        
        # Verify with Razorpay
        client = get_razorpay_client()
        try:
            payment = client.payment.fetch(payment_id)
            
            if payment['status'] != 'authorized' and payment['status'] != 'captured':
                payment_transaction.status = 'failed'
                payment_transaction.save()
                return JsonResponse({'error': f'Payment not successful. Status: {payment["status"]}'}, status=400)
            
            # Payment successful - add credits to organization
            result = add_credits(
                payment_transaction.organization,
                request.user,
                payment_transaction.credits,
                reason=f"Credit purchase via Razorpay - Order: {order_id}",
                metadata={
                    'payment_id': payment_id,
                    'order_id': order_id,
                    'amount': payment_transaction.amount
                }
            )
            
            if result['success']:
                # If this is a plan subscription, update organization's plan
                if payment_transaction.plan:
                    organization = payment_transaction.organization
                    organization.plan = payment_transaction.plan
                    organization.save()
                
                # Update payment transaction
                payment_transaction.razorpay_payment_id = payment_id
                payment_transaction.razorpay_signature = signature
                payment_transaction.status = 'completed'
                payment_transaction.updated_at = datetime.utcnow()
                payment_transaction.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Payment verified and credits added successfully',
                    'credits_added': payment_transaction.credits,
                    'balance_after': result['balance_after'],
                    'payment_id': payment_id,
                    'plan_id': str(payment_transaction.plan.id) if payment_transaction.plan else None
                }, status=200)
            else:
                payment_transaction.status = 'failed'
                payment_transaction.save()
                return JsonResponse({'error': f'Failed to add credits: {result["message"]}'}, status=500)
                
        except Exception as e:
            payment_transaction.status = 'failed'
            payment_transaction.save()
            return JsonResponse({'error': f'Razorpay verification failed: {str(e)}'}, status=500)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Get Payment History
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def get_payment_history(request):
    """Get payment history for an organization"""
    try:
        organization_id = request.GET.get('organization_id')
        
        if not organization_id:
            return JsonResponse({'error': 'organization_id is required'}, status=400)
        
        # Get organization
        organization = Organization.objects(id=organization_id).first()
        if not organization:
            return JsonResponse({'error': 'Organization not found'}, status=404)
        
        # Check permission
        if not is_organization_owner(request.user, organization):
            return JsonResponse({'error': 'Only organization owner can view payment history'}, status=403)
        
        # Get payment transactions
        transactions = PaymentTransaction.objects(organization=organization).order_by('-created_at')
        
        transactions_list = []
        for txn in transactions:
            plan_name = None
            if txn.plan:
                plan_name = txn.plan.name
            
            transactions_list.append({
                'id': str(txn.id),
                'amount': txn.amount,
                'credits': txn.credits,
                'status': txn.status,
                'razorpay_order_id': txn.razorpay_order_id,
                'razorpay_payment_id': txn.razorpay_payment_id,
                'plan_id': str(txn.plan.id) if txn.plan else None,
                'plan_name': plan_name,
                'created_at': txn.created_at.isoformat() if txn.created_at else None,
                'updated_at': txn.updated_at.isoformat() if txn.updated_at else None
            })
        
        return JsonResponse({
            'organization_id': str(organization.id),
            'organization_name': organization.name,
            'transactions': transactions_list,
            'total_count': len(transactions_list)
        }, status=200)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Admin: Get All Payment Transactions
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def get_all_payments(request):
    """Get all payment transactions - admin only"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can view all payments'}, status=403)
    
    try:
        # Get query parameters
        organization_id = request.GET.get('organization_id')
        status_filter = request.GET.get('status')
        
        # Build query
        query = {}
        if organization_id:
            organization = Organization.objects(id=organization_id).first()
            if not organization:
                return JsonResponse({'error': 'Organization not found'}, status=404)
            query['organization'] = organization
        
        if status_filter:
            query['status'] = status_filter
        
        # Get payment transactions
        transactions = PaymentTransaction.objects(**query).order_by('-created_at')
        
        transactions_list = []
        for txn in transactions:
            plan_name = None
            if txn.plan:
                plan_name = txn.plan.name
            
            transactions_list.append({
                'id': str(txn.id),
                'organization_id': str(txn.organization.id),
                'organization_name': txn.organization.name,
                'user_id': str(txn.user.id),
                'user_email': txn.user.email if hasattr(txn.user, 'email') else 'N/A',
                'plan_id': str(txn.plan.id) if txn.plan else None,
                'plan_name': plan_name,
                'amount': txn.amount,
                'credits': txn.credits,
                'currency': txn.currency,
                'status': txn.status,
                'razorpay_order_id': txn.razorpay_order_id,
                'razorpay_payment_id': txn.razorpay_payment_id,
                'created_at': txn.created_at.isoformat() if txn.created_at else None,
                'updated_at': txn.updated_at.isoformat() if txn.updated_at else None,
            })
        
        return JsonResponse({
            'success': True,
            'transactions': transactions_list,
            'total_count': len(transactions_list)
        }, status=200)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Admin: Get Revenue Statistics
# =====================
@api_view(['GET'])
@csrf_exempt
@authenticate
def get_revenue_stats(request):
    """Get revenue statistics - admin only"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Only admin can view revenue statistics'}, status=403)
    
    try:
        # Get current month start and end dates
        now = datetime.utcnow()
        current_month_start = datetime(now.year, now.month, 1)
        current_month_end = datetime(now.year, now.month, monthrange(now.year, now.month)[1], 23, 59, 59)
        
        # Get all completed payment transactions
        all_completed = PaymentTransaction.objects(status='completed')
        
        # Calculate total revenue (all time)
        total_revenue = sum(txn.amount for txn in all_completed)
        
        # Calculate monthly revenue (current month)
        monthly_transactions = all_completed.filter(
            created_at__gte=current_month_start,
            created_at__lte=current_month_end
        )
        monthly_revenue = sum(txn.amount for txn in monthly_transactions)
        
        # Get previous month for comparison
        if now.month == 1:
            prev_month_start = datetime(now.year - 1, 12, 1)
            prev_month_end = datetime(now.year - 1, 12, monthrange(now.year - 1, 12)[1], 23, 59, 59)
        else:
            prev_month_start = datetime(now.year, now.month - 1, 1)
            prev_month_end = datetime(now.year, now.month - 1, monthrange(now.year, now.month - 1)[1], 23, 59, 59)
        
        prev_month_transactions = all_completed.filter(
            created_at__gte=prev_month_start,
            created_at__lte=prev_month_end
        )
        prev_month_revenue = sum(txn.amount for txn in prev_month_transactions)
        
        # Calculate growth percentage
        growth_percentage = 0
        if prev_month_revenue > 0:
            growth_percentage = ((monthly_revenue - prev_month_revenue) / prev_month_revenue) * 100
        elif monthly_revenue > 0:
            growth_percentage = 100
        
        # Count transactions
        total_transactions = all_completed.count()
        monthly_transactions_count = monthly_transactions.count()
        
        return JsonResponse({
            'success': True,
            'total_revenue': round(total_revenue, 2),
            'monthly_revenue': round(monthly_revenue, 2),
            'prev_month_revenue': round(prev_month_revenue, 2),
            'growth_percentage': round(growth_percentage, 2),
            'total_transactions': total_transactions,
            'monthly_transactions': monthly_transactions_count,
            'currency': 'INR'
        }, status=200)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
