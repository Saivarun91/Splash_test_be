"""
Email utility functions for sending various types of emails.
Uses MailTemplate from DB when available; falls back to built-in defaults.
"""
import re
from django.core.mail import send_mail
from django.conf import settings
import secrets
import string
from datetime import datetime


def generate_random_password(length=16):
    """Generate a random password with letters, digits, and special characters"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(alphabet) for _ in range(length))
    return password


def _get_template(slug):
    """Get mail template from DB if it exists."""
    try:
        from common.mail_models import MailTemplate, ensure_default_templates
        ensure_default_templates()
        return MailTemplate.objects(slug=slug).first()
    except Exception:
        return None


def _render_template(body_plain, context):
    """Simple template render: {{var}} and {{#var}}...{{/var}}."""
    if not body_plain:
        return ""
    text = body_plain
    # Replace {{#key}}...{{/key}} blocks: include content only if context[key] is truthy
    for key in context:
        pattern = r"\{\{#" + re.escape(key) + r"\}\}(.*?)\{\{/" + re.escape(key) + r"\}\}"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            block = match.group(1) if context.get(key) else ""
            text = re.sub(pattern, block, text, flags=re.DOTALL)
    # Replace {{var}}
    for key, value in context.items():
        text = text.replace("{{" + key + "}}", str(value or ""))
    return text


def _send_from_template(slug, recipient_list, context, fallback_subject, fallback_body):
    """Send email using template from DB, or fallback subject/body."""
    t = _get_template(slug)
    if t:
        subject = _render_template(t.subject, context)
        body = _render_template(t.body_plain, context)
    else:
        subject = fallback_subject
        body = fallback_body
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            recipient_list,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending email ({slug}): {e}")
        return False


def send_registration_email(user_email, user_name=None):
    """Send welcome email after user registration (uses template if set)."""
    name = user_name or "User"
    context = {"user_name": name}
    fallback_subject = "Welcome to Splash!"
    fallback_body = f"""
Hello {name},

Welcome to Splash! Your account has been successfully created.

You can now log in and start using our platform.

If you have any questions, please don't hesitate to contact us.

Best regards,
The Splash Team
"""
    return _send_from_template(
        "registration_user", [user_email], context, fallback_subject, fallback_body
    )


def send_registration_admin_email(user_email, user_name=None, user_username=None):
    """Notify admin(s) that a new user registered. Sends to all admin users."""
    try:
        from users.models import User, Role
        admin_users = User.objects(role=Role.ADMIN)
        admin_emails = [u.email for u in admin_users if getattr(u, "email", None)]
        if not admin_emails:
            admin_emails = getattr(settings, "ADMIN_EMAILS", [])
        if isinstance(admin_emails, str):
            admin_emails = [admin_emails]
        if not admin_emails:
            return True
    except Exception as e:
        print(f"Could not get admin emails for registration notification: {e}")
        return True
    context = {
        "user_email": user_email or "",
        "user_name": user_name or "",
        "user_username": user_username or "",
        "registered_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }
    fallback_subject = "New user registered on Splash"
    fallback_body = f"""
Hello,

A new user has registered:

- Email: {user_email}
- Name: {user_name or 'N/A'}
- Username: {user_username or 'N/A'}
- Registered at: {context['registered_at']}

Best regards,
Splash System
"""
    return _send_from_template(
        "registration_admin", admin_emails, context, fallback_subject, fallback_body
    )


def send_password_reset_email(user_email, reset_token, user_name=None):
    """Send password reset email with reset link (uses template if set)."""
    reset_link = f"{getattr(settings, 'FRONTEND_URL', '')}/reset-password?token={reset_token}"
    name = user_name or "User"
    context = {"user_name": name, "reset_link": reset_link}
    fallback_subject = "Password Reset Request - Splash"
    fallback_body = f"""
Hello {name},

You requested to reset your password for your Splash account.

Click the following link to reset your password:
{reset_link}

This link will expire in 24 hours.

If you did not request this password reset, please ignore this email.

Best regards,
The Splash Team
"""
    return _send_from_template(
        "forgot_password", [user_email], context, fallback_subject, fallback_body
    )


def send_organization_invite_email(user_email, password, organization_name, role, inviter_name=None, is_new_user=True):
    """Send email to user when they are added to an organization (uses template if set)."""
    login_url = getattr(settings, "FRONTEND_URL", "") + "/login"
    inviter = inviter_name or "Organization Owner"
    accept_link = login_url  # Same as login for now; can be invite-accept URL later
    context = {
        "organization_name": organization_name,
        "inviter_name": inviter,
        "role": role,
        "password": password or "",
        "is_new_user": is_new_user,
        "login_url": login_url,
        "accept_link": accept_link,
    }
    fallback_subject = f"You have been added to {organization_name} on Splash"
    if is_new_user:
        fallback_body = f"""
Hello,

You have been added to the organization "{organization_name}" on Splash by {inviter}.

Your account details:
- Email: {user_email}
- Temporary Password: {password}
- Role: {role}

Please log in and complete your profile setup.
Login URL: {login_url}

Important: Please change your password immediately after logging in.

Best regards,
The Splash Team
"""
    else:
        fallback_body = f"""
Hello,

You have been added to the organization "{organization_name}" on Splash by {inviter}.

Your role in this organization: {role}

Please log in to access your organization dashboard.
Login URL: {login_url}

Best regards,
The Splash Team
"""
    return _send_from_template(
        "invite_organization_user", [user_email], context, fallback_subject, fallback_body
    )


def send_invite_organizer_confirmation(organizer_email, invitee_email, organization_name, role):
    """Notify organizer that invite was sent (uses template if set)."""
    context = {
        "organizer_name": "",  # Could pass if needed
        "invitee_email": invitee_email,
        "organization_name": organization_name,
        "role": role,
    }
    fallback_subject = f"Invite sent to {invitee_email}"
    fallback_body = f"""
Hello,

You have successfully sent an invite to {invitee_email} for the organization "{organization_name}".

Role: {role}

Best regards,
The Splash Team
"""
    return _send_from_template(
        "invite_organization_organizer", [organizer_email], context, fallback_subject, fallback_body
    )


def send_contact_sales_admin_email(submission_data):
    """Notify admin(s) about a new Contact Sales / Enterprise lead submission."""
    try:
        from users.models import User, Role
        admin_users = User.objects(role=Role.ADMIN)
        admin_emails = [u.email for u in admin_users if getattr(u, "email", None)]
        if not admin_emails:
            admin_emails = getattr(settings, "ADMIN_EMAILS", [])
        if isinstance(admin_emails, str):
            admin_emails = [admin_emails]
        if not admin_emails:
            return True
    except Exception as e:
        print(f"Could not get admin emails for contact sales notification: {e}")
        return True
    context = {
        "first_name": submission_data.get("first_name", ""),
        "last_name": submission_data.get("last_name", ""),
        "work_email": submission_data.get("work_email", ""),
        "phone": submission_data.get("phone", ""),
        "company_website": submission_data.get("company_website", ""),
        "problems_trying_to_solve": submission_data.get("problems_trying_to_solve", ""),
        "users_to_onboard": submission_data.get("users_to_onboard", ""),
        "timeline": submission_data.get("timeline", ""),
        "submitted_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }
    fallback_subject = "New Contact Sales / Enterprise lead"
    fallback_body = f"""
Hello,

A new Contact Sales / Enterprise lead has been submitted:

Contact details:
- First name: {context['first_name']}
- Last name: {context['last_name']}
- Work email: {context['work_email']}
- Phone: {context['phone']}
- Company website: {context['company_website']}

What problems are they trying to solve: {context['problems_trying_to_solve']}
Users to onboard: {context['users_to_onboard']}
Timeline: {context['timeline']}

Submitted at: {context['submitted_at']}

Best regards,
Splash System
"""
    return _send_from_template(
        "contact_sales_admin", admin_emails, context, fallback_subject, fallback_body
    )
