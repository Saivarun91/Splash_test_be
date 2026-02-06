"""
Email utility functions for sending various types of emails.
Uses MailTemplate from DB when available; falls back to built-in defaults.
Includes a shared HTML base template with portal colors and logo.
"""
import re
from django.core.mail import send_mail
from django.conf import settings
import secrets
import string
from datetime import datetime

# Portal color palette and branding for emails
EMAIL_PRIMARY = "#6d28d9"
EMAIL_PRIMARY_LIGHT = "#8b5cf6"
EMAIL_BG = "#f8fafc"
EMAIL_CARD_BG = "#ffffff"
EMAIL_TEXT = "#171717"
EMAIL_TEXT_MUTED = "#64748b"
EMAIL_BORDER = "#e2e8f0"
PORTAL_NAME = "Splash"

# common/email_utils.py
import random
from django.core.mail import send_mail
from django.conf import settings

def generate_otp():
    return str(random.randint(100000, 999999))


def send_email_otp(email, otp, name=None):
    subject = "Verify your email"
    message = f"""
Hi {name or ''},

Your email verification OTP is: {otp}

This OTP is valid for 10 minutes.
Do not share it with anyone.

Thanks,
Team
"""
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )

def get_logo_url():
    """Base URL for logo image in emails (must be absolute)."""
    base = getattr(settings, "FRONTEND_URL", "") or "http://localhost:3000"
    return base.rstrip("/") + "/images/logo-splash.png"


def get_base_email_html(content_body, title=""):
    """
    Wrap content in a consistent HTML email layout with portal colors and logo.
    content_body: HTML string for the main body.
    title: Optional heading above the body (e.g. "Payment Successful").
    """
    logo_url = get_logo_url()
    frontend_url = getattr(settings, "FRONTEND_URL", "") or ""
    title_block = f'<h2 style="color: {EMAIL_TEXT}; font-size: 20px; margin: 0 0 16px 0;">{title}</h2>' if title else ""
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{PORTAL_NAME}</title>
</head>
<body style="margin: 0; padding: 0; background-color: {EMAIL_BG}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: {EMAIL_BG};">
    <tr>
      <td align="center" style="padding: 32px 16px;">
        <table role="presentation" width="100%" style="max-width: 560px; background-color: {EMAIL_CARD_BG}; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid {EMAIL_BORDER};">
          <tr>
            <td style="padding: 24px 24px 16px 24px; border-bottom: 1px solid {EMAIL_BORDER};">
              <a href="{frontend_url}" style="text-decoration: none;">
                <img src="{logo_url}" alt="{PORTAL_NAME}" style="max-height: 40px; display: block;" />
              </a>
            </td>
          </tr>
          <tr>
            <td style="padding: 24px; color: {EMAIL_TEXT}; font-size: 16px; line-height: 1.6;">
              {title_block}
              <div style="color: {EMAIL_TEXT};">
                {content_body}
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding: 16px 24px; border-top: 1px solid {EMAIL_BORDER}; font-size: 12px; color: {EMAIL_TEXT_MUTED};">
              This email was sent by {PORTAL_NAME}. If you have questions, contact support.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _send_html_email(subject, body_plain, body_html, recipient_list):
    """Send email with both plain and HTML parts."""
    try:
        send_mail(
            subject,
            body_plain,
            settings.DEFAULT_FROM_EMAIL,
            recipient_list,
            fail_silently=False,
            html_message=body_html,
        )
        return True
    except Exception as e:
        print(f"Error sending HTML email: {e}")
        return False


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


def send_payment_success_user_email(user_email, user_name, credits_added, balance_after, total_amount, is_organization=False, organization_name=None):
    """Send payment success email to the user who made the payment (HTML + plain)."""
    context = {
        "user_name": user_name or "User",
        "credits_added": credits_added,
        "balance_after": balance_after,
        "total_amount": total_amount,
        "is_organization": is_organization,
        "organization_name": organization_name or "",
    }
    subject = f"Payment successful – {credits_added} credits added to your account"
    body_plain = f"""
Hello {context['user_name']},

Your payment was successful.

Credits added: {credits_added}
Current balance: {balance_after}
Amount paid: ${total_amount:.2f}
"""
    if is_organization and organization_name:
        body_plain += f"\nOrganization: {organization_name}\n"
    body_plain += "\nThank you for using Splash.\n\nBest regards,\nThe Splash Team"

    body_html_content = f"""
<p>Hello {context['user_name']},</p>
<p>Your payment was successful.</p>
<table style="border-collapse: collapse; margin: 16px 0;">
  <tr><td style="padding: 6px 12px 6px 0; color: {EMAIL_TEXT_MUTED};">Credits added</td><td style="padding: 6px 0;"><strong>{credits_added}</strong></td></tr>
  <tr><td style="padding: 6px 12px 6px 0; color: {EMAIL_TEXT_MUTED};">Current balance</td><td style="padding: 6px 0;"><strong>{balance_after}</strong></td></tr>
  <tr><td style="padding: 6px 12px 6px 0; color: {EMAIL_TEXT_MUTED};">Amount paid</td><td style="padding: 6px 0;"><strong>${total_amount:.2f}</strong></td></tr>
</table>
"""
    if is_organization and organization_name:
        body_html_content += f"<p style='color: {EMAIL_TEXT_MUTED};'>Organization: <strong>{organization_name}</strong></p>"
    body_html_content += "<p>Thank you for using Splash.</p><p>Best regards,<br>The Splash Team</p>"

    html = get_base_email_html(body_html_content, "Payment successful")
    return _send_html_email(subject, body_plain, html, [user_email])


def send_payment_success_admin_email(user_email, user_name, credits_added, total_amount, is_organization=False, organization_name=None):
    """Notify admin(s) that a payment was completed (HTML + plain)."""
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
        print(f"Could not get admin emails for payment success notification: {e}")
        return True

    subject = "Payment successful – credits purchased"
    body_plain = f"""
A payment was completed:

User: {user_name} ({user_email})
Credits: {credits_added}
Amount: ${total_amount:.2f}
"""
    if is_organization and organization_name:
        body_plain += f"Organization: {organization_name}\n"
    body_plain += f"\nTime: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\nSplash System"

    body_html_content = f"""
<p>A payment was completed:</p>
<table style="border-collapse: collapse; margin: 16px 0;">
  <tr><td style="padding: 6px 12px 6px 0; color: {EMAIL_TEXT_MUTED};">User</td><td style="padding: 6px 0;">{user_name} ({user_email})</td></tr>
  <tr><td style="padding: 6px 12px 6px 0; color: {EMAIL_TEXT_MUTED};">Credits</td><td style="padding: 6px 0;"><strong>{credits_added}</strong></td></tr>
  <tr><td style="padding: 6px 12px 6px 0; color: {EMAIL_TEXT_MUTED};">Amount</td><td style="padding: 6px 0;"><strong>${total_amount:.2f}</strong></td></tr>
"""
    if is_organization and organization_name:
        body_html_content += f"  <tr><td style='padding: 6px 12px 6px 0; color: {EMAIL_TEXT_MUTED};'>Organization</td><td style='padding: 6px 0;'>{organization_name}</td></tr>"
    body_html_content += f"""
</table>
<p style="color: {EMAIL_TEXT_MUTED}; font-size: 14px;">Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
<p>Splash System</p>
"""
    html = get_base_email_html(body_html_content, "Payment successful (admin)")
    return _send_html_email(subject, body_plain, html, admin_emails)


def send_credits_recharge_reminder_email(user_email, user_name, current_balance, threshold, is_organization=False, organization_name=None):
    """Send credits low / recharge reminder to the user (HTML + plain)."""
    subject = f"Credits running low – only {current_balance} left"
    body_plain = f"""
Hello {user_name or 'User'},

Your credit balance is now {current_balance} (at or below the {threshold} credit reminder threshold).
"""
    if is_organization and organization_name:
        body_plain += f"\nOrganization: {organization_name}\n"
    body_plain += """
Please recharge your credits to continue using Splash without interruption.

Best regards,
The Splash Team
"""

    body_html_content = f"""
<p>Hello {user_name or 'User'},</p>
<p>Your credit balance is now <strong>{current_balance}</strong> (at or below the {threshold} credit reminder threshold).</p>
"""
    if is_organization and organization_name:
        body_html_content += f"<p style='color: {EMAIL_TEXT_MUTED};'>Organization: <strong>{organization_name}</strong></p>"
    body_html_content += f"""
<p>Please <a href="{getattr(settings, 'FRONTEND_URL', '')}" style="color: {EMAIL_PRIMARY}; font-weight: 600;">recharge your credits</a> to continue using Splash without interruption.</p>
<p>Best regards,<br>The Splash Team</p>
"""
    html = get_base_email_html(body_html_content, "Credits running low")
    return _send_html_email(subject, body_plain, html, [user_email])


def send_contact_admin_email(submission_data):
    """Notify admin(s) about a new Contact form submission."""
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
        print(f"Could not get admin emails for contact notification: {e}")
        return True
    
    context = {
        "name": submission_data.get("name", ""),
        "mobile": submission_data.get("mobile", ""),
        "email": submission_data.get("email", ""),
        "reason": submission_data.get("reason", ""),
        "submitted_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }
    
    fallback_subject = "New Contact Form Submission - Footer"
    fallback_body = f"""
Hello,

A new contact form submission has been received:

- Name: {context['name']}
- Mobile: {context['mobile']}
- Email: {context['email']}
- Reason: {context['reason']}

Submitted at: {context['submitted_at']}

Best regards,
Splash System
"""

    return _send_from_template(
        "footer_contact_admin", admin_emails, context, fallback_subject, fallback_body
    )
