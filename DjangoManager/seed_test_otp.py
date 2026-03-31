"""
seed_test_otp.py  —  Development / CI helper
─────────────────────────────────────────────
Injects a known, fixed OTP (123456) into the otp_verification table
so Playwright tests can complete OTP flows without reading a real inbox.

SETUP
  1. Place this file at your Django project root (next to manage.py).
  2. Edit the two lines marked ← EDIT below.
  3. Run from the project root:
       python seed_test_otp.py <email> <purpose>

     Purposes (must match OtpVerification.Purpose in models.py):
       FIRST_LOGIN | LOGIN_2FA | RESET_PASSWORD

NEVER deploy or enable this in production.
"""

import os, sys, hashlib, django
from datetime import timedelta

# ── ① Edit these two values to match your project ──────────────────────────
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cybercomply.settings")  # ← EDIT
APP_NAME = "core"   # ← EDIT  (the Django app that owns models.py)
# ───────────────────────────────────────────────────────────────────────────

django.setup()

from django.utils import timezone

# Dynamic import so APP_NAME is respected
from importlib import import_module
models_module = import_module(f"{APP_NAME}.models")
UserProfile      = models_module.UserProfile
OtpVerification  = models_module.OtpVerification

KNOWN_OTP = "123456"


def seed_otp(email: str, purpose: str) -> None:
    try:
        profile = UserProfile.objects.select_related("auth_user").get(
            auth_user__username=email.strip().lower()
        )
    except UserProfile.DoesNotExist:
        print(f"[seed_test_otp] ERROR: User not found: {email}")
        sys.exit(1)

    # Invalidate any existing live OTPs of the same purpose
    invalidated = OtpVerification.objects.filter(
        user=profile, purpose=purpose, used_at__isnull=True
    ).update(used_at=timezone.now())

    if invalidated:
        print(f"[seed_test_otp] Invalidated {invalidated} existing {purpose} OTP(s)")

    otp_hash = hashlib.sha256(KNOWN_OTP.encode()).hexdigest()
    OtpVerification.objects.create(
        user     = profile,
        otp_hash = otp_hash,
        purpose  = purpose,
        expires_at = timezone.now() + timedelta(minutes=10),  # generous buffer for tests
    )
    print(f"[seed_test_otp] ✓ Seeded OTP {KNOWN_OTP!r} for {email} / {purpose}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python seed_test_otp.py <email> <purpose>")
        print("  Purposes: FIRST_LOGIN | LOGIN_2FA | RESET_PASSWORD")
        sys.exit(1)
    seed_otp(sys.argv[1], sys.argv[2])