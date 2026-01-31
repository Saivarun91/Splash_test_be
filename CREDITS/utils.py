"""
Utility functions for credit management and global AI model settings.
"""
from .models import CreditLedger, CreditSettings, CreditReminderSent
from organization.models import Organization
from users.models import User
from datetime import datetime, timedelta
from mongoengine import Q


def get_credit_settings():
    """
    Get current credit deduction and global image model settings.
    Returns default values if settings don't exist.

    Returns:
        dict: {
            'credits_per_image_generation': int,
            'credits_per_regeneration': int,
            'default_image_model_name': str,
            'credit_reminder_threshold_1': int,
            'credit_reminder_threshold_2': int,
        }
    """
    try:
        settings = CreditSettings.get_settings()
        return {
            'credits_per_image_generation': settings.credits_per_image_generation,
            'credits_per_regeneration': settings.credits_per_regeneration,
            'default_image_model_name': getattr(
                settings,
                'default_image_model_name',
                'gemini-3-pro-image-preview'
            ),
            'credit_reminder_threshold_1': getattr(settings, 'credit_reminder_threshold_1', 20),
            'credit_reminder_threshold_2': getattr(settings, 'credit_reminder_threshold_2', 10),
        }
    except Exception:
        # Return sane defaults on error
        return {
            'credits_per_image_generation': 2,
            'credits_per_regeneration': 1,
            'default_image_model_name': 'gemini-3-pro-image-preview',
            'credit_reminder_threshold_1': 20,
            'credit_reminder_threshold_2': 10,
        }


REMINDER_COOLDOWN_DAYS = 7  # Don't send same threshold reminder again within 7 days


def _should_send_reminder(user, organization, threshold):
    """Check if we already sent this threshold reminder recently (within cooldown)."""
    since = datetime.utcnow() - timedelta(days=REMINDER_COOLDOWN_DAYS)
    if organization:
        q = Q(organization=organization, threshold=threshold, sent_at__gte=since)
    else:
        q = Q(user=user, threshold=threshold, sent_at__gte=since) & (Q(organization=None) | Q(organization__exists=False))
    return not CreditReminderSent.objects(q).first()


def _record_reminder_sent(user, organization, threshold):
    """Record that we sent a reminder for this user/org and threshold."""
    try:
        CreditReminderSent(user=user, organization=organization, threshold=threshold).save()
    except Exception as e:
        print(f"Failed to record credit reminder sent: {e}")


def maybe_send_credit_reminder(organization, user, balance_after):
    """
    If balance_after is at or below a configured threshold and we haven't sent
    that threshold reminder recently, send recharge reminder to org owner and record it.
    """
    try:
        settings = CreditSettings.get_settings()
        t1 = getattr(settings, 'credit_reminder_threshold_1', 20)
        t2 = getattr(settings, 'credit_reminder_threshold_2', 10)
        thresholds = [t1, t2]
        # Dedupe and sort descending so we only send for the lowest applicable threshold if both hit
        thresholds = sorted(set(thresholds), reverse=True)
        recipient_email = organization.owner.email if organization.owner else None
        recipient_name = (organization.owner.full_name or organization.owner.username) if organization.owner else ""
        if not recipient_email:
            return
        for th in thresholds:
            if balance_after <= th and _should_send_reminder(organization.owner, organization, th):
                from common.email_utils import send_credits_recharge_reminder_email
                send_credits_recharge_reminder_email(
                    recipient_email,
                    recipient_name,
                    balance_after,
                    th,
                    is_organization=True,
                    organization_name=organization.name,
                )
                _record_reminder_sent(organization.owner, organization, th)
                break  # Only one reminder per deduction
    except Exception as e:
        print(f"Credit reminder check failed: {e}")


def maybe_send_credit_reminder_user(user, balance_after):
    """
    If balance_after is at or below a configured threshold and we haven't sent
    that threshold reminder recently, send recharge reminder to user and record it.
    """
    try:
        settings = CreditSettings.get_settings()
        t1 = getattr(settings, 'credit_reminder_threshold_1', 20)
        t2 = getattr(settings, 'credit_reminder_threshold_2', 10)
        thresholds = sorted(set([t1, t2]), reverse=True)
        recipient_email = getattr(user, 'email', None)
        if not recipient_email:
            return
        for th in thresholds:
            if balance_after <= th and _should_send_reminder(user, None, th):
                from common.email_utils import send_credits_recharge_reminder_email
                send_credits_recharge_reminder_email(
                    recipient_email,
                    getattr(user, 'full_name', None) or getattr(user, 'username', 'User'),
                    balance_after,
                    th,
                    is_organization=False,
                )
                _record_reminder_sent(user, None, th)
                break
    except Exception as e:
        print(f"Credit reminder check failed: {e}")


def get_image_model_name(default_model: str = "gemini-3-pro-image-preview") -> str:
    """
    Get the active AI model name for image generation.

    This reads from CreditSettings.default_image_model_name, falling back to
    the provided default_model if not configured.
    """
    try:
        settings = CreditSettings.get_settings()
        model_name = getattr(settings, "default_image_model_name", None)
        if not model_name:
            return default_model
        return model_name
    except Exception:
        return default_model

def deduct_credits(organization, user, amount, reason="Image generation", project=None, metadata=None):
    try:
        from CREDITS.models import CreditLedger

        OrgModel = organization.__class__   # <-- THIS fixes your import issue

        # ✅ ATOMIC conditional decrement
        updated = OrgModel.objects(
            id=organization.id,
            credit_balance__gte=amount
        ).update_one(
            dec__credit_balance=amount,
            set__updated_at=datetime.utcnow()
        )

        if updated == 0:
            organization.reload()
            return {
                'success': False,
                'message': f'Insufficient credits. Available: {organization.credit_balance}, Required: {amount}',
                'balance_after': organization.credit_balance
            }

        # Reload after atomic update
        organization.reload()

        # ✅ Ledger entry
        CreditLedger(
            user=user,
            organization=organization,
            project=project,
            change_type="debit",
            credits_changed=amount,
            balance_after=organization.credit_balance,
            reason=reason,
            metadata=metadata or {},
            created_by=user,
            updated_by=user,
            updated_at=datetime.utcnow()
        ).save()

        # Credits low reminder (admin-configured thresholds)
        maybe_send_credit_reminder(organization, user, organization.credit_balance)

        return {
            'success': True,
            'message': 'Credits deducted successfully',
            'balance_after': organization.credit_balance
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'Error deducting credits: {str(e)}',
            'balance_after': organization.credit_balance if organization else 0
        }
def add_credits(organization, user, amount, reason="Credit top-up", metadata=None):
    """
    Add credits to an organization's balance.
    
    Args:
        organization: Organization instance
        user: User instance who initiated the action (usually admin)
        amount: Number of credits to add
        reason: Reason for credit addition
        metadata: Optional metadata dict
    
    Returns:
        dict: {'success': bool, 'message': str, 'balance_after': int}
    """
    try:
        # Reload organization to get latest balance
        organization.reload()
        
        # Add credits
        organization.credit_balance += amount
        organization.updated_at = datetime.utcnow()
        organization.save()
        
        # Create ledger entry
        ledger_entry = CreditLedger(
            user=user,
            organization=organization,
            change_type="credit",
            credits_changed=amount,
            balance_after=organization.credit_balance,
            reason=reason,
            metadata=metadata or {},
            created_by=user,
            updated_by=user
        )
        ledger_entry.save()
        
        return {
            'success': True,
            'message': f'Credits added successfully',
            'balance_after': organization.credit_balance
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'Error adding credits: {str(e)}',
            'balance_after': organization.credit_balance if organization else 0
        }


def get_organization_credits(organization):
    """
    Get current credit balance for an organization.
    
    Args:
        organization: Organization instance
    
    Returns:
        int: Current credit balance
    """
    try:
        organization.reload()
        return organization.credit_balance
    except Exception as e:
        return 0


def get_user_organization(user):
    """
    Get the organization for a user.
    
    Args:
        user: User instance
    
    Returns:
        Organization instance or None
    """
    try:
        if user.organization:
            return user.organization
        return None
    except Exception as e:
        return None


def deduct_user_credits(user, amount, reason="Image generation", project=None, metadata=None):
    """
    Deduct credits from a single user (not in any organization).
    
    Args:
        user: User instance
        amount: Number of credits to deduct
        reason: Reason for credit deduction
        project: Optional project reference
        metadata: Optional metadata dict
    
    Returns:
        dict: {'success': bool, 'message': str, 'balance_after': int}
    """
    try:
        from CREDITS.models import CreditLedger
        
        # Reload user to get latest balance
        user.reload()
        
        # Check if user has sufficient credits
        if (user.credit_balance or 0) < amount:
            return {
                'success': False,
                'message': f'Insufficient credits. Available: {user.credit_balance or 0}, Required: {amount}',
                'balance_after': user.credit_balance or 0
            }
        
        # Deduct credits atomically
        User.objects(id=user.id).update_one(
            dec__credit_balance=amount,
            set__updated_at=datetime.utcnow()
        )
        
        # Reload after atomic update
        user.reload()
        
        # Create ledger entry (organization is None for single users)
        CreditLedger(
            user=user,
            organization=None,  # Single user, no organization
            project=project,
            change_type="debit",
            credits_changed=amount,
            balance_after=user.credit_balance or 0,
            reason=reason,
            metadata=metadata or {},
            created_by=user,
            updated_by=user,
            updated_at=datetime.utcnow()
        ).save()

        # Credits low reminder (admin-configured thresholds)
        maybe_send_credit_reminder_user(user, user.credit_balance or 0)
        
        return {
            'success': True,
            'message': 'Credits deducted successfully',
            'balance_after': user.credit_balance or 0
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': f'Error deducting credits: {str(e)}',
            'balance_after': user.credit_balance if user else 0
        }