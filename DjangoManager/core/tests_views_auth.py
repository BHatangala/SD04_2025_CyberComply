"""
tests_views_auth.py — Group 1: Authentication View Tests
=========================================================
Covers:
  POST /api/signup/
  POST /api/login/
  POST /api/verify-otp/
  POST /api/session-token/
  POST /api/logout/

Run with:
  python manage.py test core.tests_views_auth --verbosity=2

All external calls that would hit real services are patched:
  - send_otp_email  → mocked so no real AWS SES calls are made
  - _delete_s3_keys → mocked so logout does not hit real S3

How the Bearer token works in tests
-------------------------------------
The real app uses django.core.signing.dumps/loads with salt="session-token".
In tests we call the real issue_session_token endpoint to get a valid token
(same as the frontend does), then pass it as HTTP_AUTHORIZATION.
A helper method _get_token(email) is provided on every TestCase class so
every test can get a token in one line.
"""

import json
import hashlib
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.core import signing

from core.models import (
    UserProfile,
    OtpVerification,
    LoginHistory,
    AuditLog,
    Document,
)


# ─────────────────────────────────────────────────────────────────────────────
# Shared test data constants
# ─────────────────────────────────────────────────────────────────────────────

VALID_PASSWORD   = "Str0ng!Pass99"       # passes Django's password validators
GENERAL_EMAIL    = "vivek.test@gmail.com"
GENERAL_NAME     = "Vivek Silva"
ADMIN_EMAIL      = "admin.test@sliit.lk" # org domain — passes validate_org_email
ADMIN_NAME       = "Admin User"


# ─────────────────────────────────────────────────────────────────────────────
# Helper — create a verified user + get a real session token
# ─────────────────────────────────────────────────────────────────────────────

def _make_verified_user(email=GENERAL_EMAIL, name=GENERAL_NAME,
                        role=UserProfile.Role.GENERAL, password=VALID_PASSWORD):
    """
    Directly creates a verified UserProfile in the DB (bypasses signup flow).
    This is the fast path: use it whenever a test needs a logged-in user but
    is NOT specifically testing the signup or OTP flow itself.
    """
    auth_user = User.objects.create_user(
        username=email, email=email, password=password
    )
    profile = UserProfile.objects.create(
        auth_user=auth_user,
        full_name=name,
        role=role,
        is_verified=True,
        otp_is_enabled=False,
    )
    return profile


# ─────────────────────────────────────────────────────────────────────────────
# 1. SIGNUP TESTS
# ─────────────────────────────────────────────────────────────────────────────

class SignupViewTest(TestCase):
    """
    Tests for POST /api/signup/

    The signup view:
      - Validates name, email, password, and role
      - Rejects duplicate emails (409)
      - Rejects admin signups with non-org emails
      - Creates an UNVERIFIED UserProfile on success (201)
      - Does NOT send any email itself — that happens on first login
    """

    def setUp(self):
        self.client = Client()
        self.url    = "/api/signup/"

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    # ── Happy path ────────────────────────────────────────────────────────

    def test_signup_general_user_returns_201(self):
        # A valid general user signup should succeed with 201
        resp = self._post({
            "name":     GENERAL_NAME,
            "email":    GENERAL_EMAIL,
            "password": VALID_PASSWORD,
            "role":     "General user",
        })
        self.assertEqual(resp.status_code, 201)
        data = json.loads(resp.content)
        self.assertIn("Account created", data["detail"])

    def test_signup_creates_unverified_profile(self):
        # The created profile must NOT be verified yet (requires OTP on first login)
        self._post({
            "name":     GENERAL_NAME,
            "email":    GENERAL_EMAIL,
            "password": VALID_PASSWORD,
            "role":     "General user",
        })
        profile = UserProfile.objects.get(auth_user__username=GENERAL_EMAIL)
        self.assertFalse(profile.is_verified)

    def test_signup_role_stored_correctly(self):
        # Role should be stored as GENERAL in the DB
        self._post({
            "name":     GENERAL_NAME,
            "email":    GENERAL_EMAIL,
            "password": VALID_PASSWORD,
            "role":     "General user",
        })
        profile = UserProfile.objects.get(auth_user__username=GENERAL_EMAIL)
        self.assertEqual(profile.role, UserProfile.Role.GENERAL)

    def test_signup_email_stored_lowercase(self):
        # Email must be normalised to lowercase regardless of input
        self._post({
            "name":     GENERAL_NAME,
            "email":    "VIVEK.TEST@GMAIL.COM",
            "password": VALID_PASSWORD,
            "role":     "General user",
        })
        self.assertTrue(User.objects.filter(username=GENERAL_EMAIL).exists())

    # ── Duplicate email ────────────────────────────────────────────────────

    def test_signup_duplicate_email_returns_409(self):
        # Registering the same email twice should return 409
        self._post({
            "name":     GENERAL_NAME,
            "email":    GENERAL_EMAIL,
            "password": VALID_PASSWORD,
            "role":     "General user",
        })
        resp = self._post({
            "name":     "Other Person",
            "email":    GENERAL_EMAIL,
            "password": VALID_PASSWORD,
            "role":     "General user",
        })
        self.assertEqual(resp.status_code, 409)

    # ── Missing / invalid fields ───────────────────────────────────────────

    def test_signup_missing_name_returns_400(self):
        resp = self._post({
            "email":    GENERAL_EMAIL,
            "password": VALID_PASSWORD,
            "role":     "General user",
        })
        self.assertEqual(resp.status_code, 400)

    def test_signup_missing_email_returns_400(self):
        resp = self._post({
            "name":     GENERAL_NAME,
            "password": VALID_PASSWORD,
            "role":     "General user",
        })
        self.assertEqual(resp.status_code, 400)

    def test_signup_missing_password_returns_400(self):
        resp = self._post({
            "name":  GENERAL_NAME,
            "email": GENERAL_EMAIL,
            "role":  "General user",
        })
        self.assertEqual(resp.status_code, 400)

    def test_signup_missing_role_returns_400(self):
        resp = self._post({
            "name":     GENERAL_NAME,
            "email":    GENERAL_EMAIL,
            "password": VALID_PASSWORD,
        })
        self.assertEqual(resp.status_code, 400)

    def test_signup_invalid_role_returns_400(self):
        resp = self._post({
            "name":     GENERAL_NAME,
            "email":    GENERAL_EMAIL,
            "password": VALID_PASSWORD,
            "role":     "Super Admin",  # not in the allowed role_map
        })
        self.assertEqual(resp.status_code, 400)

    # ── Name validation ────────────────────────────────────────────────────

    def test_signup_single_word_name_returns_400(self):
        # Must be at least first + last name
        resp = self._post({
            "name":     "Vivek",
            "email":    GENERAL_EMAIL,
            "password": VALID_PASSWORD,
            "role":     "General user",
        })
        self.assertEqual(resp.status_code, 400)

    def test_signup_name_with_numbers_returns_400(self):
        resp = self._post({
            "name":     "Vivek 123",
            "email":    GENERAL_EMAIL,
            "password": VALID_PASSWORD,
            "role":     "General user",
        })
        self.assertEqual(resp.status_code, 400)

    # ── Email validation ───────────────────────────────────────────────────

    def test_signup_invalid_email_format_returns_400(self):
        resp = self._post({
            "name":     GENERAL_NAME,
            "email":    "not-an-email",
            "password": VALID_PASSWORD,
            "role":     "General user",
        })
        self.assertEqual(resp.status_code, 400)

    # ── Password validation ────────────────────────────────────────────────

    def test_signup_weak_password_returns_400(self):
        # Django's validators should reject "password" as too common/short
        resp = self._post({
            "name":     GENERAL_NAME,
            "email":    GENERAL_EMAIL,
            "password": "password",
            "role":     "General user",
        })
        self.assertEqual(resp.status_code, 400)

    def test_signup_short_password_returns_400(self):
        resp = self._post({
            "name":     GENERAL_NAME,
            "email":    GENERAL_EMAIL,
            "password": "Ab1!",
            "role":     "General user",
        })
        self.assertEqual(resp.status_code, 400)

    # ── Admin role validation ──────────────────────────────────────────────

    def test_signup_admin_with_gmail_returns_400(self):
        # Admin signup requires an organisational email, not gmail/hotmail etc.
        resp = self._post({
            "name":     ADMIN_NAME,
            "email":    "admin@gmail.com",
            "password": VALID_PASSWORD,
            "role":     "Administrative user",
        })
        self.assertEqual(resp.status_code, 400)

    def test_signup_admin_with_org_email_returns_201(self):
        # A valid org email (e.g. sliit.lk) should be accepted for admin signup
        resp = self._post({
            "name":     ADMIN_NAME,
            "email":    ADMIN_EMAIL,
            "password": VALID_PASSWORD,
            "role":     "Administrative user",
        })
        self.assertEqual(resp.status_code, 201)

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_signup_get_request_returns_405(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 2. LOGIN TESTS
# ─────────────────────────────────────────────────────────────────────────────

class LoginViewTest(TestCase):
    """
    Tests for POST /api/login/

    The login view has several branches:
      1. User not found / wrong password → 401
      2. Account soft-deleted → 401
      3. Account locked → 423
      4. Unverified account → sends FIRST_LOGIN OTP, returns requires_otp
      5. Verified + 2FA enabled → sends LOGIN_2FA OTP, returns requires_otp
      6. Verified + no 2FA → returns Login successful immediately
      7. 5 wrong passwords → locks account (423)

    send_otp_email is patched on every test to prevent real SES calls.
    """

    def setUp(self):
        self.client  = Client()
        self.url     = "/api/login/"
        # A ready-to-use verified profile with no 2FA (the common case)
        self.profile = _make_verified_user()

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    # ── Happy path — no 2FA ────────────────────────────────────────────────

    def test_login_valid_credentials_returns_200(self):
        resp = self._post({"email": GENERAL_EMAIL, "password": VALID_PASSWORD})
        self.assertEqual(resp.status_code, 200)

    def test_login_response_contains_email_role_name(self):
        resp   = self._post({"email": GENERAL_EMAIL, "password": VALID_PASSWORD})
        data   = json.loads(resp.content)
        self.assertIn("email",     data)
        self.assertIn("role",      data)
        self.assertIn("full_name", data)

    def test_login_updates_last_login_at(self):
        before = timezone.now()
        self._post({"email": GENERAL_EMAIL, "password": VALID_PASSWORD})
        self.profile.refresh_from_db()
        last_login = self.profile.last_login_at
        self.assertIsNotNone(last_login)
        assert last_login is not None  # narrows type for Pylance
        self.assertTrue(last_login >= before)

    def test_login_resets_failed_login_count(self):
        # Give the profile some failed attempts first, then a successful login
        self.profile.failed_login_count = 3
        self.profile.save(update_fields=["failed_login_count"])
        self._post({"email": GENERAL_EMAIL, "password": VALID_PASSWORD})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.failed_login_count, 0)

    def test_login_records_success_in_login_history(self):
        self._post({"email": GENERAL_EMAIL, "password": VALID_PASSWORD})
        exists = LoginHistory.objects.filter(
            user=self.profile,
            status=LoginHistory.Status.SUCCESS,
        ).exists()
        self.assertTrue(exists)

    # ── Wrong credentials ──────────────────────────────────────────────────

    def test_login_wrong_password_returns_401(self):
        resp = self._post({"email": GENERAL_EMAIL, "password": "WrongPass999!"})
        self.assertEqual(resp.status_code, 401)

    def test_login_unknown_email_returns_401(self):
        resp = self._post({"email": "nobody@example.com", "password": VALID_PASSWORD})
        self.assertEqual(resp.status_code, 401)

    def test_login_wrong_password_increments_failed_count(self):
        self._post({"email": GENERAL_EMAIL, "password": "WrongPass999!"})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.failed_login_count, 1)

    # ── Account lockout ────────────────────────────────────────────────────

    def test_login_5_wrong_passwords_locks_account(self):
        # After 5 failed attempts the account must be locked (423)
        # Use a list comprehension so Pylance knows the element type is never None
        responses = [
            self._post({"email": GENERAL_EMAIL, "password": "WrongPass999!"})
            for _ in range(5)
        ]
        self.assertEqual(responses[-1].status_code, 423)

    def test_login_locked_account_returns_423(self):
        # Manually lock the account and verify the view blocks it
        self.profile.locked_until = timezone.now() + timedelta(minutes=15)
        self.profile.save(update_fields=["locked_until"])
        resp = self._post({"email": GENERAL_EMAIL, "password": VALID_PASSWORD})
        self.assertEqual(resp.status_code, 423)

    def test_login_expired_lock_auto_unlocks(self):
        # A lock that has already expired should be cleared automatically
        self.profile.locked_until       = timezone.now() - timedelta(minutes=1)
        self.profile.failed_login_count = 5
        self.profile.save(update_fields=["locked_until", "failed_login_count"])
        resp = self._post({"email": GENERAL_EMAIL, "password": VALID_PASSWORD})
        self.assertEqual(resp.status_code, 200)

    # ── Soft-deleted account ───────────────────────────────────────────────

    def test_login_deleted_account_returns_401(self):
        self.profile.deleted_at = timezone.now()
        self.profile.save(update_fields=["deleted_at"])
        resp = self._post({"email": GENERAL_EMAIL, "password": VALID_PASSWORD})
        self.assertEqual(resp.status_code, 401)

    # ── Unverified account (first login) ──────────────────────────────────

    @patch("core.views.send_otp_email", return_value=True)
    def test_login_unverified_user_triggers_otp_flow(self, mock_email):
        # Create an unverified user (as signup produces)
        auth = User.objects.create_user(
            username="unverified@example.com",
            email="unverified@example.com",
            password=VALID_PASSWORD,
        )
        UserProfile.objects.create(
            auth_user=auth,
            full_name="Unverified User",
            role=UserProfile.Role.GENERAL,
            is_verified=False,
        )
        resp = self._post({"email": "unverified@example.com", "password": VALID_PASSWORD})
        data = json.loads(resp.content)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data.get("requires_otp"))

    @patch("core.views.send_otp_email", return_value=True)
    def test_login_unverified_user_creates_first_login_otp(self, mock_email):
        auth = User.objects.create_user(
            username="unverified2@example.com",
            email="unverified2@example.com",
            password=VALID_PASSWORD,
        )
        profile = UserProfile.objects.create(
            auth_user=auth,
            full_name="Unverified Two",
            role=UserProfile.Role.GENERAL,
            is_verified=False,
        )
        self._post({"email": "unverified2@example.com", "password": VALID_PASSWORD})
        exists = OtpVerification.objects.filter(
            user=profile,
            purpose=OtpVerification.Purpose.FIRST_LOGIN,
        ).exists()
        self.assertTrue(exists)

    # ── 2FA enabled account ────────────────────────────────────────────────

    @patch("core.views.send_otp_email", return_value=True)
    def test_login_2fa_enabled_triggers_otp_flow(self, mock_email):
        self.profile.otp_is_enabled = True
        self.profile.save(update_fields=["otp_is_enabled"])
        resp = self._post({"email": GENERAL_EMAIL, "password": VALID_PASSWORD})
        data = json.loads(resp.content)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data.get("requires_otp"))

    @patch("core.views.send_otp_email", return_value=True)
    def test_login_2fa_enabled_creates_login_2fa_otp(self, mock_email):
        self.profile.otp_is_enabled = True
        self.profile.save(update_fields=["otp_is_enabled"])
        self._post({"email": GENERAL_EMAIL, "password": VALID_PASSWORD})
        exists = OtpVerification.objects.filter(
            user=self.profile,
            purpose=OtpVerification.Purpose.LOGIN_2FA,
        ).exists()
        self.assertTrue(exists)

    # ── Missing fields ─────────────────────────────────────────────────────

    def test_login_missing_email_returns_400(self):
        resp = self._post({"password": VALID_PASSWORD})
        self.assertEqual(resp.status_code, 400)

    def test_login_missing_password_returns_400(self):
        resp = self._post({"email": GENERAL_EMAIL})
        self.assertEqual(resp.status_code, 400)

    def test_login_invalid_email_format_returns_400(self):
        resp = self._post({"email": "bad-email", "password": VALID_PASSWORD})
        self.assertEqual(resp.status_code, 400)

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_login_get_request_returns_405(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 3. VERIFY OTP TESTS
# ─────────────────────────────────────────────────────────────────────────────

class VerifyOtpViewTest(TestCase):
    """
    Tests for POST /api/verify-otp/

    This endpoint handles two cases:
      - FIRST_LOGIN OTP  → verifies account (is_verified = True)
      - LOGIN_2FA OTP    → completes 2FA login

    Key logic to test:
      - Correct OTP → 200 + Login successful
      - Wrong OTP → 401 + increments attempt_count
      - Expired OTP → 401
      - Brute-force guard: 5 wrong attempts → OTP invalidated
      - OTP reuse: used OTP → 401
      - Non-OTP account submitting OTP → 400
    """

    def setUp(self):
        self.client = Client()
        self.url    = "/api/verify-otp/"

        # An unverified user waiting for FIRST_LOGIN OTP
        auth = User.objects.create_user(
            username="otp.user@example.com",
            email="otp.user@example.com",
            password=VALID_PASSWORD,
        )
        self.profile = UserProfile.objects.create(
            auth_user=auth,
            full_name="OTP Test User",
            role=UserProfile.Role.GENERAL,
            is_verified=False,
        )
        # Pre-create a valid FIRST_LOGIN OTP
        self.raw_otp  = "482910"
        self.otp_row  = OtpVerification.objects.create(
            user=self.profile,
            otp_hash=hashlib.sha256(self.raw_otp.encode()).hexdigest(),
            purpose=OtpVerification.Purpose.FIRST_LOGIN,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    # ── Correct OTP (FIRST_LOGIN) ──────────────────────────────────────────

    def test_verify_otp_correct_returns_200(self):
        resp = self._post({"email": "otp.user@example.com", "otp": self.raw_otp})
        self.assertEqual(resp.status_code, 200)

    def test_verify_otp_correct_marks_profile_as_verified(self):
        self._post({"email": "otp.user@example.com", "otp": self.raw_otp})
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_verified)

    def test_verify_otp_correct_marks_otp_as_used(self):
        self._post({"email": "otp.user@example.com", "otp": self.raw_otp})
        self.otp_row.refresh_from_db()
        self.assertIsNotNone(self.otp_row.used_at)

    def test_verify_otp_correct_response_contains_login_fields(self):
        resp = self._post({"email": "otp.user@example.com", "otp": self.raw_otp})
        data = json.loads(resp.content)
        self.assertIn("email",     data)
        self.assertIn("role",      data)
        self.assertIn("full_name", data)

    def test_verify_otp_correct_records_success_in_history(self):
        self._post({"email": "otp.user@example.com", "otp": self.raw_otp})
        exists = LoginHistory.objects.filter(
            user=self.profile,
            status=LoginHistory.Status.SUCCESS,
        ).exists()
        self.assertTrue(exists)

    # ── Wrong OTP ─────────────────────────────────────────────────────────

    def test_verify_otp_wrong_code_returns_401(self):
        resp = self._post({"email": "otp.user@example.com", "otp": "000000"})
        self.assertEqual(resp.status_code, 401)

    def test_verify_otp_wrong_code_increments_attempt_count(self):
        self._post({"email": "otp.user@example.com", "otp": "000000"})
        self.otp_row.refresh_from_db()
        self.assertEqual(self.otp_row.attempt_count, 1)

    # ── OTP reuse ─────────────────────────────────────────────────────────

    def test_verify_otp_reuse_blocked(self):
        # Use the OTP once correctly — profile becomes verified + no 2FA.
        # A second OTP submission hits the "OTP not required for this account"
        # guard, which returns 400 (not 401). Both statuses prove reuse is blocked.
        self._post({"email": "otp.user@example.com", "otp": self.raw_otp})
        resp = self._post({"email": "otp.user@example.com", "otp": self.raw_otp})
        self.assertIn(resp.status_code, [400, 401])

    # ── Expired OTP ────────────────────────────────────────────────────────

    def test_verify_otp_expired_returns_401(self):
        self.otp_row.expires_at = timezone.now() - timedelta(minutes=1)
        self.otp_row.save(update_fields=["expires_at"])
        resp = self._post({"email": "otp.user@example.com", "otp": self.raw_otp})
        self.assertEqual(resp.status_code, 401)

    # ── Brute-force guard ─────────────────────────────────────────────────

    def test_verify_otp_brute_force_guard_invalidates_after_5_attempts(self):
        # Set attempt_count to MAX already, next call should lock out
        self.otp_row.attempt_count = 5
        self.otp_row.save(update_fields=["attempt_count"])
        resp = self._post({"email": "otp.user@example.com", "otp": self.raw_otp})
        self.assertEqual(resp.status_code, 401)

    def test_verify_otp_brute_force_marks_otp_used(self):
        self.otp_row.attempt_count = 5
        self.otp_row.save(update_fields=["attempt_count"])
        self._post({"email": "otp.user@example.com", "otp": self.raw_otp})
        self.otp_row.refresh_from_db()
        self.assertIsNotNone(self.otp_row.used_at)

    # ── OTP not required for this account ─────────────────────────────────

    def test_verify_otp_not_required_returns_400(self):
        # A verified user with no 2FA should be rejected when submitting an OTP
        verified_profile = _make_verified_user(
            email="no2fa@example.com", name="No TFA User"
        )
        resp = self._post({"email": "no2fa@example.com", "otp": "123456"})
        self.assertEqual(resp.status_code, 400)

    # ── Input validation ───────────────────────────────────────────────────

    def test_verify_otp_non_digit_otp_returns_401(self):
        resp = self._post({"email": "otp.user@example.com", "otp": "ABCDEF"})
        self.assertEqual(resp.status_code, 401)

    def test_verify_otp_short_otp_returns_401(self):
        resp = self._post({"email": "otp.user@example.com", "otp": "123"})
        self.assertEqual(resp.status_code, 401)

    def test_verify_otp_missing_email_returns_400(self):
        resp = self._post({"otp": self.raw_otp})
        self.assertEqual(resp.status_code, 400)

    def test_verify_otp_missing_otp_returns_400(self):
        resp = self._post({"email": "otp.user@example.com"})
        self.assertEqual(resp.status_code, 400)

    def test_verify_otp_unknown_email_returns_401(self):
        resp = self._post({"email": "ghost@example.com", "otp": self.raw_otp})
        self.assertEqual(resp.status_code, 401)

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_verify_otp_get_request_returns_405(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)

    # ── 2FA OTP (LOGIN_2FA) ────────────────────────────────────────────────

    def test_verify_otp_2fa_correct_returns_200(self):
        # Set up a verified user with 2FA enabled and a LOGIN_2FA OTP
        auth = User.objects.create_user(
            username="twofa@example.com",
            email="twofa@example.com",
            password=VALID_PASSWORD,
        )
        profile_2fa = UserProfile.objects.create(
            auth_user=auth,
            full_name="Two FA User",
            role=UserProfile.Role.GENERAL,
            is_verified=True,
            otp_is_enabled=True,
        )
        raw_2fa = "774411"
        OtpVerification.objects.create(
            user=profile_2fa,
            otp_hash=hashlib.sha256(raw_2fa.encode()).hexdigest(),
            purpose=OtpVerification.Purpose.LOGIN_2FA,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        resp = self._post({"email": "twofa@example.com", "otp": raw_2fa})
        self.assertEqual(resp.status_code, 200)

    def test_verify_otp_2fa_does_not_change_is_verified(self):
        # is_verified should remain True — not be toggled — for a 2FA login
        auth = User.objects.create_user(
            username="twofa2@example.com",
            email="twofa2@example.com",
            password=VALID_PASSWORD,
        )
        profile_2fa = UserProfile.objects.create(
            auth_user=auth,
            full_name="Two FA User Two",
            role=UserProfile.Role.GENERAL,
            is_verified=True,
            otp_is_enabled=True,
        )
        raw_2fa = "881122"
        OtpVerification.objects.create(
            user=profile_2fa,
            otp_hash=hashlib.sha256(raw_2fa.encode()).hexdigest(),
            purpose=OtpVerification.Purpose.LOGIN_2FA,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        self._post({"email": "twofa2@example.com", "otp": raw_2fa})
        profile_2fa.refresh_from_db()
        self.assertTrue(profile_2fa.is_verified)


# ─────────────────────────────────────────────────────────────────────────────
# 4. SESSION TOKEN TESTS
# ─────────────────────────────────────────────────────────────────────────────

class IssueSessionTokenViewTest(TestCase):
    """
    Tests for POST /api/session-token/

    This is called by the frontend immediately after a successful login or OTP
    verification to obtain the Bearer token that protects all other endpoints.

    Rules:
      - Verified user → 200 + token + role
      - Unverified user → 403
      - Deleted account → 404
      - Unknown email → 404
    """

    def setUp(self):
        self.client  = Client()
        self.url     = "/api/session-token/"
        self.profile = _make_verified_user()

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    # ── Happy path ─────────────────────────────────────────────────────────

    def test_session_token_verified_user_returns_200(self):
        resp = self._post({"email": GENERAL_EMAIL})
        self.assertEqual(resp.status_code, 200)

    def test_session_token_response_contains_token_and_role(self):
        resp = self._post({"email": GENERAL_EMAIL})
        data = json.loads(resp.content)
        self.assertIn("token", data)
        self.assertIn("role",  data)

    def test_session_token_is_a_valid_signed_token(self):
        # The token must be loadable with the correct salt — proves it's real
        resp  = self._post({"email": GENERAL_EMAIL})
        token = json.loads(resp.content)["token"]
        data  = signing.loads(token, salt="session-token", max_age=86400)
        self.assertIn("uid", data)

    def test_session_token_uid_matches_profile(self):
        resp  = self._post({"email": GENERAL_EMAIL})
        token = json.loads(resp.content)["token"]
        data  = signing.loads(token, salt="session-token", max_age=86400)
        self.assertEqual(data["uid"], str(self.profile.user_id))

    def test_session_token_role_matches_profile(self):
        resp = self._post({"email": GENERAL_EMAIL})
        data = json.loads(resp.content)
        self.assertEqual(data["role"], self.profile.role)

    # ── Unverified user ────────────────────────────────────────────────────

    def test_session_token_unverified_user_returns_403(self):
        auth = User.objects.create_user(
            username="unverified.token@example.com",
            email="unverified.token@example.com",
            password=VALID_PASSWORD,
        )
        UserProfile.objects.create(
            auth_user=auth,
            full_name="Unverified Token",
            role=UserProfile.Role.GENERAL,
            is_verified=False,
        )
        resp = self._post({"email": "unverified.token@example.com"})
        self.assertEqual(resp.status_code, 403)

    # ── Deleted account ────────────────────────────────────────────────────

    def test_session_token_deleted_account_returns_404(self):
        self.profile.deleted_at = timezone.now()
        self.profile.save(update_fields=["deleted_at"])
        resp = self._post({"email": GENERAL_EMAIL})
        self.assertEqual(resp.status_code, 404)

    # ── Unknown email ──────────────────────────────────────────────────────

    def test_session_token_unknown_email_returns_404(self):
        resp = self._post({"email": "nobody@example.com"})
        self.assertEqual(resp.status_code, 404)

    # ── Missing field ──────────────────────────────────────────────────────

    def test_session_token_missing_email_returns_400(self):
        resp = self._post({})
        self.assertEqual(resp.status_code, 400)

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_session_token_get_request_returns_405(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 5. LOGOUT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class LogoutViewTest(TestCase):
    """
    Tests for POST /api/logout/

    Logout behaviour:
      - Always returns 200 (even with no token — expired tokens should still
        allow the frontend to clear its state)
      - Soft-deletes any documents with status UPLOADED that were never analysed
      - Records an LOGOUT AuditLog entry

    _delete_s3_keys is mocked to avoid real S3 calls.
    """

    def setUp(self):
        self.client  = Client()
        self.url     = "/api/logout/"
        self.profile = _make_verified_user()
        # Get a real token via issue_session_token
        self.token   = self._get_token(GENERAL_EMAIL)

    def _get_token(self, email):
        resp  = self.client.post(
            "/api/session-token/",
            data=json.dumps({"email": email}),
            content_type="application/json",
        )
        return json.loads(resp.content)["token"]

    def _post(self, token=None):
        headers = {}
        if token:
            headers["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        return self.client.post(self.url, **headers)

    # ── Always-200 contract ────────────────────────────────────────────────

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_logout_with_valid_token_returns_200(self, mock_s3):
        resp = self._post(token=self.token)
        self.assertEqual(resp.status_code, 200)

    def test_logout_with_no_token_still_returns_200(self):
        # Frontend must be able to clear its state even when already logged out
        resp = self._post(token=None)
        self.assertEqual(resp.status_code, 200)

    def test_logout_with_invalid_token_still_returns_200(self):
        resp = self._post(token="totally.invalid.token")
        self.assertEqual(resp.status_code, 200)

    # ── Soft-deletes unanalysed documents ─────────────────────────────────

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_logout_soft_deletes_uploaded_documents(self, mock_s3):
        # Create a document in UPLOADED status (never analysed)
        doc = Document.objects.create(
            user=self.profile,
            original_filename="pending.pdf",
            file_type="PDF",
            s3_key="pending.pdf",
            status=Document.Status.UPLOADED,
        )
        self._post(token=self.token)
        doc.refresh_from_db()
        self.assertIsNotNone(doc.deleted_at)
        self.assertEqual(doc.status, Document.Status.DELETED)

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_logout_does_not_soft_delete_completed_documents(self, mock_s3):
        # Documents that have been analysed (COMPLETED) should NOT be touched
        doc = Document.objects.create(
            user=self.profile,
            original_filename="done.pdf",
            file_type="PDF",
            s3_key="done.pdf",
            status=Document.Status.COMPLETED,
        )
        self._post(token=self.token)
        doc.refresh_from_db()
        self.assertIsNone(doc.deleted_at)
        self.assertEqual(doc.status, Document.Status.COMPLETED)

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_logout_calls_s3_delete_with_correct_keys(self, mock_s3):
        Document.objects.create(
            user=self.profile,
            original_filename="to_delete.pdf",
            file_type="PDF",
            s3_key="to_delete.pdf",
            status=Document.Status.UPLOADED,
        )
        self._post(token=self.token)
        # Verify _delete_s3_keys was called with the key from above
        called_keys = mock_s3.call_args[0][0]
        self.assertIn("to_delete.pdf", called_keys)

    # ── Audit log ─────────────────────────────────────────────────────────

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_logout_records_logout_audit_log(self, mock_s3):
        self._post(token=self.token)
        exists = AuditLog.objects.filter(
            user=self.profile,
            action_type="LOGOUT",
        ).exists()
        self.assertTrue(exists)

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_logout_get_request_returns_405(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 6. TOKEN AUTHENTICATION GUARD TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TokenAuthGuardTest(TestCase):
    """
    Tests for the _get_profile_from_token helper — which is used by every
    protected endpoint in the system.

    NOTE: /api/profile/ uses ?email= query param authentication, NOT Bearer
    token. We use /api/analysis/history/ instead — it strictly requires a
    valid Bearer token and returns 401/403 without one.

    This is the pattern all team members should follow when testing auth
    rejection: pick an endpoint that uses _get_profile_from_token and has
    no alternative auth path.
    """

    # Endpoint that is genuinely protected by Bearer token
    PROTECTED_URL = "/api/analysis/history/"

    def setUp(self):
        self.client  = Client()
        self.profile = _make_verified_user()
        self.token   = self._get_valid_token()

    def _get_valid_token(self):
        resp = self.client.post(
            "/api/session-token/",
            data=json.dumps({"email": GENERAL_EMAIL}),
            content_type="application/json",
        )
        return json.loads(resp.content)["token"]

    # ── Missing / malformed token ──────────────────────────────────────────

    def test_no_auth_header_returns_401(self):
        resp = self.client.get(self.PROTECTED_URL)
        self.assertEqual(resp.status_code, 401)

    def test_malformed_bearer_token_returns_401(self):
        resp = self.client.get(
            self.PROTECTED_URL,
            HTTP_AUTHORIZATION="Bearer not.a.real.token",
        )
        self.assertEqual(resp.status_code, 401)

    def test_empty_bearer_value_returns_401(self):
        resp = self.client.get(
            self.PROTECTED_URL,
            HTTP_AUTHORIZATION="Bearer ",
        )
        self.assertEqual(resp.status_code, 401)

    # ── Valid token works ──────────────────────────────────────────────────

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_valid_token_allows_access_to_protected_endpoint(self, mock_s3):
        resp = self.client.get(
            self.PROTECTED_URL,
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        # 200 proves the token was accepted by _get_profile_from_token
        self.assertEqual(resp.status_code, 200)

    # ── Deleted account token ──────────────────────────────────────────────

    def test_deleted_account_token_returns_401(self):
        # Even with a valid token, a soft-deleted account must be blocked
        self.profile.deleted_at = timezone.now()
        self.profile.save(update_fields=["deleted_at"])
        resp = self.client.get(
            self.PROTECTED_URL,
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(resp.status_code, 401)