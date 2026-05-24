"""
reset_verification.py  —  Development / CI helper

Flips the is_verified flag on a user account in the Django DB.
Used by Playwright tests that need to test the FIRST_LOGIN OTP flow
against an existing account without deleting any of its data.

SETUP
  1. Place this file at your Django project root (next to manage.py).
  2. Edit the two lines marked EDIT below.

Usage:
  Set account to UNVERIFIED before the test:
    python reset_verification.py <email> unverified

  Restore account to VERIFIED after the test:
    python reset_verification.py <email> verified

NEVER deploy or enable this in production.
"""

import os
import sys
import django
from importlib import import_module

# ── Edit these two values to match your project ────────────────────────────────
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cybercomply.settings")  
APP_NAME = "core"  
# ──────────────────────────────────────────────────────────────────────────────

django.setup()

models_module = import_module(f"{APP_NAME}.models")
UserProfile = models_module.UserProfile


def reset_verification(email: str, state: str) -> None:
    # Validate the state argument
    if state not in ("verified", "unverified"):
        print(f"[reset_verification] ERROR: state must be 'verified' or 'unverified', got: {state!r}")
        sys.exit(1)

    # Look up the user profile
    try:
        profile = UserProfile.objects.select_related("auth_user").get(
            auth_user__username=email.strip().lower()
        )
    except UserProfile.DoesNotExist:
        print(f"[reset_verification] ERROR: User not found: {email}")
        sys.exit(1)

    # Flip the flag
    target = (state == "verified")
    profile.is_verified = target
    profile.save(update_fields=["is_verified"])

    # Log the result
    if target:
        status = "VERIFIED — account restored to normal"
    else:
        status = "UNVERIFIED — ready for FIRST_LOGIN OTP test"

    print(f"[reset_verification] {email} - {status}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python reset_verification.py <email> <verified|unverified>")
        sys.exit(1)

    reset_verification(sys.argv[1], sys.argv[2])