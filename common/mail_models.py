"""
Mail template models for admin-editable email templates.
Uses MongoEngine for consistency with users/organization.
"""
from mongoengine import Document, StringField, DateTimeField
import datetime

# Template slugs - used in code and API
SLUG_REGISTRATION_USER = "registration_user"
SLUG_REGISTRATION_ADMIN = "registration_admin"
SLUG_FORGOT_PASSWORD = "forgot_password"
SLUG_INVITE_ORGANIZATION_USER = "invite_organization_user"
SLUG_INVITE_ORGANIZATION_ORGANIZER = "invite_organization_organizer"
SLUG_INVITE_PROJECT_USER = "invite_project_user"
SLUG_INVITE_PROJECT_ORGANIZER = "invite_project_organizer"
SLUG_PAYMENT_SUCCESS_USER = "payment_success_user"
SLUG_PAYMENT_SUCCESS_ADMIN = "payment_success_admin"
SLUG_CREDITS_RECHARGE_REMINDER = "credits_recharge_reminder"

MAIL_TEMPLATE_SLUGS = [
    SLUG_REGISTRATION_USER,
    SLUG_REGISTRATION_ADMIN,
    SLUG_FORGOT_PASSWORD,
    SLUG_INVITE_ORGANIZATION_USER,
    SLUG_INVITE_ORGANIZATION_ORGANIZER,
    SLUG_INVITE_PROJECT_USER,
    SLUG_INVITE_PROJECT_ORGANIZER,
    SLUG_PAYMENT_SUCCESS_USER,
    SLUG_PAYMENT_SUCCESS_ADMIN,
    SLUG_CREDITS_RECHARGE_REMINDER,
]


def get_default_templates():
    """Default content for each template. Variables: {{variable_name}}."""
    return {
        SLUG_REGISTRATION_USER: {
            "name": "Registration – Thank you (to user)",
            "description": "Sent to the user after they register.",
            "subject": "Welcome to Splash!",
            "body_plain": """Hello {{user_name}},

Welcome to Splash! Your account has been successfully created.

You can now log in and start using our platform.

If you have any questions, please don't hesitate to contact us.

Best regards,
The Splash Team""",
        },
        SLUG_REGISTRATION_ADMIN: {
            "name": "Registration – New user notification (to admin)",
            "description": "Sent to admin when a new user registers.",
            "subject": "New user registered on Splash",
            "body_plain": """Hello,

A new user has registered:

- Email: {{user_email}}
- Name: {{user_name}}
- Username: {{user_username}}
- Registered at: {{registered_at}}

Best regards,
Splash System""",
        },
        SLUG_FORGOT_PASSWORD: {
            "name": "Forgot password – Reset link",
            "description": "Sent to user with password reset link.",
            "subject": "Password Reset Request - Splash",
            "body_plain": """Hello {{user_name}},

You requested to reset your password for your Splash account.

Click the following link to reset your password:
{{reset_link}}

This link will expire in 24 hours.

If you did not request this password reset, please ignore this email.

Best regards,
The Splash Team""",
        },
        SLUG_INVITE_ORGANIZATION_USER: {
            "name": "Organization invite (to invited user)",
            "description": "Sent to user when they are invited to an organization. Use Accept button link.",
            "subject": "You have been invited to {{organization_name}} on Splash",
            "body_plain": """Hello,

You have been invited to the organization "{{organization_name}}" on Splash by {{inviter_name}}.

Your role: {{role}}

{{#is_new_user}}
Your temporary password: {{password}}
Please log in and change your password.
{{/is_new_user}}

Accept invite: {{accept_link}}

Login URL: {{login_url}}

Best regards,
The Splash Team""",
        },
        SLUG_INVITE_ORGANIZATION_ORGANIZER: {
            "name": "Organization invite sent (to organizer)",
            "description": "Sent to organization owner when an invite is sent.",
            "subject": "Invite sent to {{invitee_email}}",
            "body_plain": """Hello {{organizer_name}},

You have successfully sent an invite to {{invitee_email}} for the organization "{{organization_name}}".

Role: {{role}}

Best regards,
The Splash Team""",
        },
        SLUG_INVITE_PROJECT_USER: {
            "name": "Project collaboration invite (to invited user)",
            "description": "Sent to user when invited to a project.",
            "subject": "You have been invited to project {{project_name}} on Splash",
            "body_plain": """Hello,

You have been invited to the project "{{project_name}}" by {{inviter_name}}.

Accept invite: {{accept_link}}

Best regards,
The Splash Team""",
        },
        SLUG_INVITE_PROJECT_ORGANIZER: {
            "name": "Project invite sent (to organizer)",
            "description": "Sent to project owner when a collaboration invite is sent.",
            "subject": "Project invite sent to {{invitee_email}}",
            "body_plain": """Hello {{organizer_name}},

You have sent a project collaboration invite to {{invitee_email}} for the project "{{project_name}}".

Best regards,
The Splash Team""",
        },
        SLUG_PAYMENT_SUCCESS_USER: {
            "name": "Payment successful (to user)",
            "description": "Sent to the user after a successful credit purchase.",
            "subject": "Payment successful – {{credits_added}} credits added to your account",
            "body_plain": """Hello {{user_name}},

Your payment was successful.

Credits added: {{credits_added}}
Current balance: {{balance_after}}
Amount paid: ${{total_amount}}

Thank you for using Splash.

Best regards,
The Splash Team""",
        },
        SLUG_PAYMENT_SUCCESS_ADMIN: {
            "name": "Payment successful (to admin)",
            "description": "Sent to admin when a user completes a credit purchase.",
            "subject": "Payment successful – credits purchased",
            "body_plain": """Hello,

A payment was completed:

User: {{user_name}} ({{user_email}})
Credits: {{credits_added}}
Amount: ${{total_amount}}

Time: {{payment_time}}

Splash System""",
        },
        SLUG_CREDITS_RECHARGE_REMINDER: {
            "name": "Credits running low – Recharge reminder",
            "description": "Sent to user when their credit balance is at or below a threshold (thresholds set below).",
            "subject": "Credits running low – only {{current_balance}} left",
            "body_plain": """Hello {{user_name}},

Your credit balance is now {{current_balance}} (at or below the {{threshold}} credit reminder threshold).

Please recharge your credits to continue using Splash without interruption.

Best regards,
The Splash Team""",
        },
    }


class MailTemplate(Document):
    slug = StringField(required=True, unique=True)
    name = StringField(required=True)
    description = StringField(default="")
    subject = StringField(required=True)
    body_plain = StringField(required=True)
    body_html = StringField(required=False)  # optional HTML version
    updated_at = DateTimeField(default=datetime.datetime.utcnow)

    meta = {
        "collection": "mail_templates",
        "indexes": ["slug"],
    }

    def __str__(self):
        return f"{self.slug}: {self.name}"


def ensure_default_templates():
    """Create or update mail templates with defaults if missing."""
    defaults = get_default_templates()
    for slug in MAIL_TEMPLATE_SLUGS:
        if slug not in defaults:
            continue
        d = defaults[slug]
        t = MailTemplate.objects(slug=slug).first()
        if not t:
            MailTemplate(
                slug=slug,
                name=d["name"],
                description=d.get("description", ""),
                subject=d["subject"],
                body_plain=d["body_plain"],
            ).save()
