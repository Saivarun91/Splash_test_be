"""
Email utility functions for sending various types of emails
"""
from django.core.mail import send_mail
from django.conf import settings
import secrets
import string
from datetime import datetime, timedelta


def generate_random_password(length=16):
    """Generate a random password with letters, digits, and special characters"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(alphabet) for i in range(length))
    return password


def send_registration_email(user_email, user_name=None):
    """Send welcome email after user registration"""
    subject = 'Welcome to Splash!'
    name = user_name or 'User'
    message = f"""
Hello {name},

Welcome to Splash! Your account has been successfully created.

You can now log in and start using our platform.

If you have any questions, please don't hesitate to contact us.

Best regards,
The Splash Team
"""
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user_email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending registration email: {e}")
        return False


def send_password_reset_email(user_email, reset_token, user_name=None):
    """Send password reset email with reset link"""
    subject = 'Password Reset Request - Splash'
    name = user_name or 'User'
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
    
    message = f"""
Hello {name},

You requested to reset your password for your Splash account.

Click the following link to reset your password:
{reset_link}

This link will expire in 24 hours.

If you did not request this password reset, please ignore this email.

Best regards,
The Splash Team
"""
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user_email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending password reset email: {e}")
        return False


def send_organization_invite_email(user_email, password, organization_name, role, inviter_name=None, is_new_user=True):
    """Send email to user when they are added to an organization"""
    subject = f'You have been added to {organization_name} on Splash'
    inviter = inviter_name or 'Organization Owner'
    
    if is_new_user:
        message = f"""
Hello,

You have been added to the organization "{organization_name}" on Splash by {inviter}.

Your account details:
- Email: {user_email}
- Temporary Password: {password}
- Role: {role}

Please log in and complete your profile setup. You will be required to:
1. Set a new password
2. Complete your profile information

Login URL: {settings.FRONTEND_URL}/login

Important: Please change your password immediately after logging in.

Best regards,
The Splash Team
"""
    else:
        message = f"""
Hello,

You have been added to the organization "{organization_name}" on Splash by {inviter}.

Your role in this organization: {role}

Please log in to access your organization dashboard.

Login URL: {settings.FRONTEND_URL}/login

Best regards,
The Splash Team
"""
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user_email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending organization invite email: {e}")
        return False
