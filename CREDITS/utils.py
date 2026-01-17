"""
Utility functions for credit management
"""
from .models import CreditLedger
from organization.models import Organization
from users.models import User
from datetime import datetime

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


