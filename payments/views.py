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
from .models import PaymentTransaction, ContactSalesSubmission
from invoices.models import InvoiceConfig
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
    """Create a Razorpay order for credit purchase (organization or single user).

    This endpoint now:
    - looks up current GST percentage from InvoiceConfig
    - accepts optional billing details (name, address, phone, gst_number, billing_type)
    - stores tax breakdown on PaymentTransaction
    """
    try:
        data = json.loads(request.body)
        organization_id = data.get('organization_id')  # Optional for single users
        # Base amount before GST
        amount = float(data.get('amount', 0))
        credits = int(data.get('credits', 0))
        plan_id = data.get('plan_id')  # Optional - for plan subscriptions

        # Optional billing details provided from frontend "billing details" step
        billing_name = data.get('billing_name')
        billing_address = data.get('billing_address')
        billing_phone = data.get('billing_phone')
        billing_gst_number = data.get('billing_gst_number')
        billing_type = data.get('billing_type') or 'individual'
        
        if amount <= 0:
            return JsonResponse({'error': 'amount is required and must be greater than 0'}, status=400)
        
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
        
        organization = None
        is_single_user = False
        
        if organization_id:
            # Organization payment
            organization = Organization.objects(id=organization_id).first()
            if not organization:
                return JsonResponse({'error': 'Organization not found'}, status=404)
            
            # Check permission - only owner can purchase credits/plans
            if not is_organization_owner(request.user, organization):
                return JsonResponse({'error': 'Only organization owner can purchase credits/plans'}, status=403)
        else:
            # Single user payment
            is_single_user = True
        
        # Calculate GST using current invoice configuration
        invoice_config = InvoiceConfig.objects.first()
        tax_rate = float(getattr(invoice_config, "tax_rate", 18.0))
        tax_amount = round((amount * tax_rate) / 100.0, 2)
        total_amount = round(amount + tax_amount, 2)

        # Create Razorpay order
        client = get_razorpay_client()
        
        # Generate a shorter receipt ID (max 40 chars for Razorpay)
        if organization:
            # Format: org_<org_id_short>_<timestamp_short>
            org_id_short = str(organization.id)[:8]  # First 8 chars of org ID
            timestamp_short = str(int(datetime.utcnow().timestamp()))[-8:]  # Last 8 digits of timestamp
            receipt_id = f'org_{org_id_short}_{timestamp_short}'
        else:
            # Format: user_<user_id_short>_<timestamp_short>
            user_id_short = str(request.user.id)[:8]  # First 8 chars of user ID
            timestamp_short = str(int(datetime.utcnow().timestamp()))[-8:]  # Last 8 digits of timestamp
            receipt_id = f'user_{user_id_short}_{timestamp_short}'
        
        # Ensure receipt is max 40 characters
        if len(receipt_id) > 40:
            receipt_id = receipt_id[:40]
        
        order_notes = {
            'user_id': str(request.user.id),
            'credits': credits
        }
        
        if organization:
            order_notes['organization_id'] = str(organization.id)
            order_notes['organization_name'] = organization.name
        else:
            order_notes['user_name'] = request.user.full_name or request.user.username
        
        if plan_id:
            order_notes['plan_id'] = str(plan_id)
            order_notes['plan_name'] = plan.name
        
        order_data = {
            # Razorpay expects final amount including GST, in paise
            'amount': int(total_amount * 100),
            'currency': 'USD',
            'receipt': receipt_id,
            'notes': order_notes
        }
        
        razorpay_order = client.order.create(data=order_data)
        
        # Create payment transaction record
        payment_transaction = PaymentTransaction(
            organization=organization,  # None for single users
            user=request.user,
            plan=plan,
            amount=amount,
            credits=credits,
            currency=order_data['currency'],
            billing_name=billing_name,
            billing_address=billing_address,
            billing_phone=billing_phone,
            billing_gst_number=billing_gst_number,
            billing_type=billing_type,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            total_amount=total_amount,
            razorpay_order_id=razorpay_order['id'],
            status='pending',
            metadata=json.dumps({
                'razorpay_order': razorpay_order,
                'created_by': str(request.user.id),
                'plan_id': str(plan_id) if plan_id else None
            })
        )
        payment_transaction.save()
        
        response_data = {
            'success': True,
            'order_id': razorpay_order['id'],
            # Return both base amount and final amount for UI display if needed
            'amount': amount,
            'tax_rate': tax_rate,
            'tax_amount': tax_amount,
            'total_amount': total_amount,
            'currency': 'USD',
            'key_id': getattr(settings, 'RAZORPAY_KEY_ID', ''),
            'credits': credits,
            'is_single_user': is_single_user
        }
        
        if organization:
            response_data['organization_id'] = str(organization.id)
        
        return JsonResponse(response_data, status=200)
        
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
        # Support both our internal field names and Razorpay's default names
        order_id = data.get('order_id') or data.get('razorpay_order_id')
        payment_id = data.get('payment_id') or data.get('razorpay_payment_id')
        signature = data.get('signature') or data.get('razorpay_signature')
        print("order_id", order_id)
        print("payment_id", payment_id)
        print("signature", signature)
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
            
            # Payment successful - add credits to organization or user
            if payment_transaction.organization:
                # Organization payment
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
                    
                    balance_after = result['balance_after']
                else:
                    payment_transaction.status = 'failed'
                    payment_transaction.save()
                    return JsonResponse({'error': f'Failed to add credits: {result["message"]}'}, status=500)
            else:
                # Single user payment - add credits directly to user
                user = payment_transaction.user
                user.credit_balance = (user.credit_balance or 0) + payment_transaction.credits
                
                # If this is a plan subscription, update user's plan
                if payment_transaction.plan:
                    user.plan = payment_transaction.plan
                
                user.save()
                balance_after = user.credit_balance
            
            # Update payment transaction
            payment_transaction.razorpay_payment_id = payment_id
            payment_transaction.razorpay_signature = signature
            payment_transaction.status = 'completed'
            payment_transaction.updated_at = datetime.utcnow()
            payment_transaction.save()

            # Payment success emails (user + admin)
            try:
                from common.email_utils import send_payment_success_user_email, send_payment_success_admin_email
                user = payment_transaction.user
                user_email = getattr(user, 'email', None)
                user_name = getattr(user, 'full_name', None) or getattr(user, 'username', 'User')
                credits_added = payment_transaction.credits
                total_amount = float(getattr(payment_transaction, 'total_amount', payment_transaction.amount))
                is_org = payment_transaction.organization is not None
                org_name = payment_transaction.organization.name if payment_transaction.organization else None
                if user_email:
                    send_payment_success_user_email(
                        user_email, user_name, credits_added, balance_after, total_amount,
                        is_organization=is_org, organization_name=org_name
                    )
                send_payment_success_admin_email(
                    user_email or '', user_name, credits_added, total_amount,
                    is_organization=is_org, organization_name=org_name
                )
            except Exception as e:
                print(f"Failed to send payment success emails: {e}")

            response_data = {
                'success': True,
                'message': 'Payment verified and credits added successfully',
                'credits_added': payment_transaction.credits,
                'balance_after': balance_after,
                'payment_id': payment_id,
                'plan_id': str(payment_transaction.plan.id) if payment_transaction.plan else None,
                'is_single_user': payment_transaction.organization is None
            }
            
            return JsonResponse(response_data, status=200)
                
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
    """Get payment history for an organization or individual user"""
    try:
        organization_id = request.GET.get('organization_id')
        
        if organization_id:
            # Get organization
            organization = Organization.objects(id=organization_id).first()
            if not organization:
                return JsonResponse({'error': 'Organization not found'}, status=404)
            
            # Check permission
            if not is_organization_owner(request.user, organization):
                return JsonResponse({'error': 'Only organization owner can view payment history'}, status=403)
            
            # Get payment transactions for organization
            transactions = PaymentTransaction.objects(organization=organization).order_by('-created_at')
            is_single_user = False
        else:
            # Single user - get their payment transactions
            transactions = PaymentTransaction.objects(
                user=request.user,
                organization=None
            ).order_by('-created_at')
            is_single_user = True
        
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
                # Billing / tax details for invoices
                'billing_name': getattr(txn, 'billing_name', None),
                'billing_address': getattr(txn, 'billing_address', None),
                'billing_phone': getattr(txn, 'billing_phone', None),
                'billing_gst_number': getattr(txn, 'billing_gst_number', None),
                'billing_type': getattr(txn, 'billing_type', None),
                'tax_rate': getattr(txn, 'tax_rate', None),
                'tax_amount': getattr(txn, 'tax_amount', None),
                'total_amount': getattr(txn, 'total_amount', None),
                'plan_id': str(txn.plan.id) if txn.plan else None,
                'plan_name': plan_name,
                'user_email': txn.user.email if hasattr(txn.user, 'email') else None,
                'user_name': txn.user.full_name if hasattr(txn.user, 'full_name') and txn.user.full_name else txn.user.username if hasattr(txn.user, 'username') else None,
                'created_at': txn.created_at.isoformat() if txn.created_at else None,
                'updated_at': txn.updated_at.isoformat() if txn.updated_at else None
            })
        
        response_data = {
            'transactions': transactions_list,
            'total_count': len(transactions_list),
            'is_single_user': is_single_user
        }
        
        if not is_single_user:
            response_data['organization_id'] = str(organization.id)
            response_data['organization_name'] = organization.name
        else:
            response_data['user_id'] = str(request.user.id)
            response_data['user_name'] = request.user.full_name or request.user.username
        
        return JsonResponse(response_data, status=200)
        
    except Exception as e:
        print(f"Error in get_payment_history: {str(e)}")
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
            
            transaction_data = {
                'id': str(txn.id),
                'organization_id': str(txn.organization.id) if txn.organization else None,
                'organization_name': txn.organization.name if txn.organization else None,
                'user_id': str(txn.user.id),
                'user_email': txn.user.email if hasattr(txn.user, 'email') else 'N/A',
                'user_name': txn.user.full_name if hasattr(txn.user, 'full_name') and txn.user.full_name else txn.user.username if hasattr(txn.user, 'username') else 'N/A',
                'plan_id': str(txn.plan.id) if txn.plan else None,
                'plan_name': plan_name,
                'amount': txn.amount,
                'credits': txn.credits,
                'currency': txn.currency,
                'status': txn.status,
                'razorpay_order_id': txn.razorpay_order_id,
                'razorpay_payment_id': txn.razorpay_payment_id,
                # Billing / tax details for admin invoice view
                'billing_name': getattr(txn, 'billing_name', None),
                'billing_address': getattr(txn, 'billing_address', None),
                'billing_phone': getattr(txn, 'billing_phone', None),
                'billing_gst_number': getattr(txn, 'billing_gst_number', None),
                'billing_type': getattr(txn, 'billing_type', None),
                'tax_rate': getattr(txn, 'tax_rate', None),
                'tax_amount': getattr(txn, 'tax_amount', None),
                'total_amount': getattr(txn, 'total_amount', None),
                'created_at': txn.created_at.isoformat() if txn.created_at else None,
                'updated_at': txn.updated_at.isoformat() if txn.updated_at else None,
                'is_single_user': txn.organization is None,
            }
            transactions_list.append(transaction_data)
        
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
            'currency': 'USD'
        }, status=200)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =====================
# Contact Sales (Enterprise lead form)
# =====================
@api_view(['POST'])
@csrf_exempt
def submit_contact_sales(request):
    """Save Contact Sales form submission to DB and email admin. No auth required."""
    try:
        data = json.loads(request.body)
        first_name = (data.get('first_name') or '').strip()
        last_name = (data.get('last_name') or '').strip()
        work_email = (data.get('work_email') or '').strip()
        phone = (data.get('phone') or '').strip()
        company_website = (data.get('company_website') or '').strip()
        problems_trying_to_solve = (data.get('problems_trying_to_solve') or '').strip()
        users_to_onboard = (data.get('users_to_onboard') or '').strip()
        timeline = (data.get('timeline') or '').strip()

        if not first_name:
            return JsonResponse({'error': 'First name is required'}, status=400)
        if not last_name:
            return JsonResponse({'error': 'Last name is required'}, status=400)
        if not work_email:
            return JsonResponse({'error': 'Work email is required'}, status=400)
        if not phone:
            return JsonResponse({'error': 'Phone number is required'}, status=400)
        if not company_website:
            return JsonResponse({'error': "Company's website is required"}, status=400)

        submission = ContactSalesSubmission(
            first_name=first_name,
            last_name=last_name,
            work_email=work_email,
            phone=phone,
            company_website=company_website,
            problems_trying_to_solve=problems_trying_to_solve,
            users_to_onboard=users_to_onboard,
            timeline=timeline,
        )
        submission.save()

        submission_data = {
            'first_name': first_name,
            'last_name': last_name,
            'work_email': work_email,
            'phone': phone,
            'company_website': company_website,
            'problems_trying_to_solve': problems_trying_to_solve,
            'users_to_onboard': users_to_onboard,
            'timeline': timeline,
        }
        from common.email_utils import send_contact_sales_admin_email
        try:
            send_contact_sales_admin_email(submission_data)
        except Exception as e:
            print(f"Failed to send contact sales admin email: {e}")
            # Do not fail the request; data is already saved

        return JsonResponse({'success': True, 'message': 'Thank you. Our team will get back to you shortly.'})
    except json.JSONDecodeError as e:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
