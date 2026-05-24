from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def send_otp_email(email: str, otp: str, purpose: str = "verification") -> bool:
    try:
        app_name = "CyberComply"

        purpose_config = {
            "verification": {
                "subject": f"{app_name} First Login Verification Code",
                "title": "First Login Verification Code",
                "intro": "We received a request to verify your identity for your CyberComply account.",
                "instruction": "Use the verification code below to continue.",
            },
            "login": {
                "subject": f"{app_name} Login Verification Code",
                "title": "Login Verification Code",
                "intro": "We received a login attempt that requires additional verification.",
                "instruction": "Use the verification code below to complete your sign in.",
            },
            "password_reset": {
                "subject": f"{app_name} Password Reset Code",
                "title": "Password Reset Code",
                "intro": "We received a request to reset your password.",
                "instruction": "Use the verification code below to continue resetting your password.",
            },
            "delete_account": {
                "subject": f"{app_name} Account Deletion Verification Code",
                "title": "Account Deletion Verification Code",
                "intro": "We received a request to delete your account.",
                "instruction": "Use the verification code below to confirm account deletion.",
            },
            "email_change": {
                "subject": f"{app_name} Email Change Verification Code",
                "title": "Email Change Verification Code",
                "intro": "We received a request to change your email address.",
                "instruction": "Use the verification code below to confirm your new email address.",
            },
            "admin_access": {
                "subject": f"{app_name} Administrative Access Verification Code",
                "title": "Administrative Access Verification Code",
                "intro": "We received a request to grant administrative access to your CyberComply account.",
                "instruction": "Use the verification code below to verify your organisation email and complete the request.",
            },
        }

        selected = purpose_config.get(purpose, purpose_config["verification"])

        context = {
            "app_name": app_name,
            "otp": otp,
            "expiry_minutes": 5,
            "title": selected["title"],
            "intro": selected["intro"],
            "instruction": selected["instruction"],
        }

        text_content = render_to_string("emails/otp_email.txt", context)
        html_content = render_to_string("emails/otp_email.html", context)

        message = EmailMultiAlternatives(
            subject=selected["subject"],
            body=text_content,
            from_email=f"{app_name} <{settings.DEFAULT_FROM_EMAIL}>",
            to=[email],
        )
        message.attach_alternative(html_content, "text/html")
        message.send()

        return True

    except Exception as e:
        print(f"ERROR sending OTP email to {email}: {e}")
        return False


def send_report_ready_email(email: str, report_name: str) -> bool:
    """Send a 'your compliance report is ready' notification email via AWS SES."""
    try:
        app_name = "CyberComply"

        context = {
            "app_name": app_name,
            "report_name": report_name,
        }

        text_content = render_to_string("emails/report_ready_email.txt", context)
        html_content = render_to_string("emails/report_ready_email.html", context)

        message = EmailMultiAlternatives(
            subject=f"{app_name} — Your Compliance Report Is Ready",
            body=text_content,
            from_email=f"{app_name} <{settings.DEFAULT_FROM_EMAIL}>",
            to=[email],
        )
        message.attach_alternative(html_content, "text/html")
        message.send()

        return True

    except Exception as e:
        print(f"ERROR sending report-ready email to {email}: {e}")
        return False