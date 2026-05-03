"""
tests_views_profile.py — Group 2: Profile View Tests
=====================================================
Covers:
  GET  /api/profile/
  PATCH /api/profile/update/
  POST /api/profile/twofa/
  POST /api/request-email-change/
  POST /api/verify-email-change/

Run with:
  python manage.py test core.tests_views_profile --verbosity=2

All external calls that would hit real services are patched:
  - send_otp_email → mocked so no real AWS SES calls are made

Notes on authentication
------------------------
GET /api/profile/ and PATCH /api/profile/update/ identify the user by
?email= query param / JSON body field respectively — they do NOT require
a Bearer token. POST /api/profile/twofa/ also uses an email body field.

POST /api/request-email-change/ and POST /api/verify-email-change/ are
likewise email-identified and do not require a Bearer token, but OTP
mocking is required wherever send_otp_email would be called.
"""

import json
import hashlib
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone

from core.models import (
    UserProfile,
    OtpVerification,
    LoginHistory,
)


# ─────────────────────────────────────────────────────────────────────────────
# Shared test data constants
# ─────────────────────────────────────────────────────────────────────────────

VALID_PASSWORD = "Str0ng!Pass99"
GENERAL_EMAIL  = "swarna.test@gmail.com"
GENERAL_NAME   = "Suwarnadaran Pathmanathan"
OTHER_EMAIL    = "other.test@gmail.com"
OTHER_NAME     = "Other User"


# ─────────────────────────────────────────────────────────────────────────────
# Helper — create a verified user directly (bypasses signup/OTP flow)
# ─────────────────────────────────────────────────────────────────────────────

def _make_verified_user(email=GENERAL_EMAIL, name=GENERAL_NAME,
                        role=UserProfile.Role.GENERAL, password=VALID_PASSWORD):
    """
    Directly creates a verified UserProfile in the DB (bypasses signup flow).
    Use this whenever a test needs an existing user but is NOT testing signup.
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


def _get_token(client, email):
    """
    Obtain a real Bearer session token for the given verified user.
    Needed for endpoints that use _get_profile_from_token (Bearer auth).
    """
    resp = client.post(
        "/api/session-token/",
        data=json.dumps({"email": email}),
        content_type="application/json",
    )
    return json.loads(resp.content)["token"]


# ─────────────────────────────────────────────────────────────────────────────
# 1. GET PROFILE TESTS
# ─────────────────────────────────────────────────────────────────────────────

class GetProfileViewTest(TestCase):
    """
    Tests for GET /api/profile/

    The view:
      - Requires ?email= query parameter
      - Returns full_name, email, role label, otp_is_enabled
      - Returns 404 for unknown or soft-deleted users
      - Returns 400 for missing / invalid email query param
      - Does NOT require a Bearer token (email is the identifier)
    """

    def setUp(self):
        self.client  = Client()
        self.url     = "/api/profile/"
        self.profile = _make_verified_user()

    # ── Happy path ─────────────────────────────────────────────────────────

    def test_get_profile_returns_200(self):
        resp = self.client.get(self.url, {"email": GENERAL_EMAIL})
        self.assertEqual(resp.status_code, 200)

    def test_get_profile_response_contains_full_name(self):
        resp = self.client.get(self.url, {"email": GENERAL_EMAIL})
        data = json.loads(resp.content)
        self.assertEqual(data["full_name"], GENERAL_NAME)

    def test_get_profile_response_contains_email(self):
        resp = self.client.get(self.url, {"email": GENERAL_EMAIL})
        data = json.loads(resp.content)
        self.assertEqual(data["email"], GENERAL_EMAIL)

    def test_get_profile_response_contains_role(self):
        resp = self.client.get(self.url, {"email": GENERAL_EMAIL})
        data = json.loads(resp.content)
        self.assertIn("role", data)

    def test_get_profile_response_contains_otp_flag(self):
        resp = self.client.get(self.url, {"email": GENERAL_EMAIL})
        data = json.loads(resp.content)
        self.assertIn("otp_is_enabled", data)
        self.assertFalse(data["otp_is_enabled"])

    def test_get_profile_email_is_case_insensitive(self):
        # The view normalises to lowercase — uppercase input should still find the user
        resp = self.client.get(self.url, {"email": GENERAL_EMAIL.upper()})
        self.assertEqual(resp.status_code, 200)

    # ── Not found ──────────────────────────────────────────────────────────

    def test_get_profile_unknown_email_returns_404(self):
        resp = self.client.get(self.url, {"email": "nobody@example.com"})
        self.assertEqual(resp.status_code, 404)

    def test_get_profile_soft_deleted_user_returns_404(self):
        self.profile.deleted_at = timezone.now()
        self.profile.save(update_fields=["deleted_at"])
        resp = self.client.get(self.url, {"email": GENERAL_EMAIL})
        self.assertEqual(resp.status_code, 404)

    # ── Missing / invalid input ────────────────────────────────────────────

    def test_get_profile_missing_email_param_returns_400(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 400)

    def test_get_profile_invalid_email_format_returns_400(self):
        resp = self.client.get(self.url, {"email": "not-an-email"})
        self.assertEqual(resp.status_code, 400)

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_get_profile_post_request_returns_405(self):
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 2. UPDATE PROFILE TESTS
# ─────────────────────────────────────────────────────────────────────────────

class UpdateProfileViewTest(TestCase):
    """
    Tests for PATCH /api/profile/update/

    The view:
      - Requires JSON body with 'email' and 'full_name'
      - Updates the user's full_name in the DB
      - Validates name length (>= 3 characters)
      - Returns 404 for unknown / soft-deleted users
      - Returns 400 for missing fields or name too short
      - Only accepts PATCH (405 for any other method)
    """

    def setUp(self):
        self.client  = Client()
        self.url     = "/api/profile/update/"
        self.profile = _make_verified_user()

    def _patch(self, payload):
        return self.client.patch(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    # ── Happy path ─────────────────────────────────────────────────────────

    def test_update_profile_valid_name_returns_200(self):
        resp = self._patch({"email": GENERAL_EMAIL, "full_name": "New Full Name"})
        self.assertEqual(resp.status_code, 200)

    def test_update_profile_persists_new_name_in_db(self):
        self._patch({"email": GENERAL_EMAIL, "full_name": "Updated Name"})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.full_name, "Updated Name")

    def test_update_profile_response_contains_full_name(self):
        resp = self._patch({"email": GENERAL_EMAIL, "full_name": "Return Check"})
        data = json.loads(resp.content)
        self.assertEqual(data["full_name"], "Return Check")

    def test_update_profile_updates_updated_at_timestamp(self):
        old_ts = self.profile.updated_at
        self._patch({"email": GENERAL_EMAIL, "full_name": "Timestamp Test"})
        self.profile.refresh_from_db()
        self.assertGreater(self.profile.updated_at, old_ts)

    # ── Not found ──────────────────────────────────────────────────────────

    def test_update_profile_unknown_email_returns_404(self):
        resp = self._patch({"email": "nobody@example.com", "full_name": "Ghost"})
        self.assertEqual(resp.status_code, 404)

    def test_update_profile_soft_deleted_user_returns_404(self):
        self.profile.deleted_at = timezone.now()
        self.profile.save(update_fields=["deleted_at"])
        resp = self._patch({"email": GENERAL_EMAIL, "full_name": "Ghost"})
        self.assertEqual(resp.status_code, 404)

    # ── Missing / invalid input ────────────────────────────────────────────

    def test_update_profile_missing_email_returns_400(self):
        resp = self._patch({"full_name": "No Email"})
        self.assertEqual(resp.status_code, 400)

    def test_update_profile_missing_full_name_returns_400(self):
        resp = self._patch({"email": GENERAL_EMAIL})
        self.assertEqual(resp.status_code, 400)

    def test_update_profile_name_too_short_returns_400(self):
        # Name must be at least 3 characters
        resp = self._patch({"email": GENERAL_EMAIL, "full_name": "Ab"})
        self.assertEqual(resp.status_code, 400)

    def test_update_profile_empty_name_returns_400(self):
        resp = self._patch({"email": GENERAL_EMAIL, "full_name": ""})
        self.assertEqual(resp.status_code, 400)

    def test_update_profile_invalid_json_returns_400(self):
        resp = self.client.patch(
            self.url,
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_update_profile_get_request_returns_405(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)

    def test_update_profile_post_request_returns_405(self):
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 3. TWO-FACTOR AUTHENTICATION TOGGLE TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TwoFAViewTest(TestCase):
    """
    Tests for POST /api/profile/twofa/

    The view:
      - Requires JSON body with 'email' and 'otp_is_enabled' (boolean)
      - Toggles profile.otp_is_enabled in the DB
      - Validates email format
      - Returns 404 for unknown / soft-deleted users
      - Returns 400 for missing fields or bad email format
      - Only accepts POST (405 for GET)
    """

    def setUp(self):
        self.client  = Client()
        self.url     = "/api/profile/twofa/"
        self.profile = _make_verified_user()

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    # ── Happy path ─────────────────────────────────────────────────────────

    def test_enable_twofa_returns_200(self):
        resp = self._post({"email": GENERAL_EMAIL, "otp_is_enabled": True})
        self.assertEqual(resp.status_code, 200)

    def test_enable_twofa_persists_true_in_db(self):
        self._post({"email": GENERAL_EMAIL, "otp_is_enabled": True})
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.otp_is_enabled)

    def test_disable_twofa_persists_false_in_db(self):
        # First enable
        self.profile.otp_is_enabled = True
        self.profile.save(update_fields=["otp_is_enabled"])
        # Then disable
        self._post({"email": GENERAL_EMAIL, "otp_is_enabled": False})
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.otp_is_enabled)

    def test_twofa_response_contains_otp_is_enabled_field(self):
        resp = self._post({"email": GENERAL_EMAIL, "otp_is_enabled": True})
        data = json.loads(resp.content)
        self.assertIn("otp_is_enabled", data)
        self.assertTrue(data["otp_is_enabled"])

    def test_twofa_records_login_history_entry(self):
        self._post({"email": GENERAL_EMAIL, "otp_is_enabled": True})
        exists = LoginHistory.objects.filter(
            user=self.profile,
            purpose=LoginHistory.Purpose.UPDATE_2FA,
        ).exists()
        self.assertTrue(exists)

    # ── Not found ──────────────────────────────────────────────────────────

    def test_twofa_unknown_email_returns_404(self):
        resp = self._post({"email": "nobody@example.com", "otp_is_enabled": True})
        self.assertEqual(resp.status_code, 404)

    def test_twofa_soft_deleted_user_returns_404(self):
        self.profile.deleted_at = timezone.now()
        self.profile.save(update_fields=["deleted_at"])
        resp = self._post({"email": GENERAL_EMAIL, "otp_is_enabled": True})
        self.assertEqual(resp.status_code, 404)

    # ── Missing / invalid input ────────────────────────────────────────────

    def test_twofa_missing_email_returns_400(self):
        resp = self._post({"otp_is_enabled": True})
        self.assertEqual(resp.status_code, 400)

    def test_twofa_missing_otp_is_enabled_returns_400(self):
        resp = self._post({"email": GENERAL_EMAIL})
        self.assertEqual(resp.status_code, 400)

    def test_twofa_invalid_email_format_returns_400(self):
        resp = self._post({"email": "bad-email", "otp_is_enabled": True})
        self.assertEqual(resp.status_code, 400)

    def test_twofa_invalid_json_returns_400(self):
        resp = self.client.post(
            self.url,
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_twofa_get_request_returns_405(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 4. REQUEST EMAIL CHANGE TESTS
# ─────────────────────────────────────────────────────────────────────────────

class RequestEmailChangeViewTest(TestCase):
    """
    Tests for POST /api/request-email-change/

    The view:
      - Requires JSON body with 'current_email' and 'new_email'
      - Sends an OTP to the new email address via send_otp_email (mocked)
      - Creates an OtpVerification row with purpose=EMAIL_CHANGE
      - Invalidates any prior unused EMAIL_CHANGE OTPs for the same user
      - Rejects same-email changes (400)
      - Rejects new_email already in use (409)
      - Returns 404 for unknown users
    """

    def setUp(self):
        self.client  = Client()
        self.url     = "/api/request-email-change/"
        self.profile = _make_verified_user()

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    # ── Happy path ─────────────────────────────────────────────────────────

    @patch("core.views.send_otp_email", return_value=True)
    def test_request_email_change_returns_200(self, mock_email):
        resp = self._post({"current_email": GENERAL_EMAIL, "new_email": "new@example.com"})
        self.assertEqual(resp.status_code, 200)

    @patch("core.views.send_otp_email", return_value=True)
    def test_request_email_change_creates_otp_row(self, mock_email):
        self._post({"current_email": GENERAL_EMAIL, "new_email": "new@example.com"})
        exists = OtpVerification.objects.filter(
            user=self.profile,
            purpose=OtpVerification.Purpose.EMAIL_CHANGE,
            used_at__isnull=True,
        ).exists()
        self.assertTrue(exists)

    @patch("core.views.send_otp_email", return_value=True)
    def test_request_email_change_calls_send_otp_email(self, mock_email):
        self._post({"current_email": GENERAL_EMAIL, "new_email": "new@example.com"})
        self.assertTrue(mock_email.called)

    @patch("core.views.send_otp_email", return_value=True)
    def test_request_email_change_invalidates_prior_otps(self, mock_email):
        # Create a pre-existing unused OTP
        OtpVerification.objects.create(
            user=self.profile,
            otp_hash=hashlib.sha256(b"123456").hexdigest(),
            purpose=OtpVerification.Purpose.EMAIL_CHANGE,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        self._post({"current_email": GENERAL_EMAIL, "new_email": "new@example.com"})
        # There should be exactly one active (unused) OTP after the request
        active_count = OtpVerification.objects.filter(
            user=self.profile,
            purpose=OtpVerification.Purpose.EMAIL_CHANGE,
            used_at__isnull=True,
        ).count()
        self.assertEqual(active_count, 1)

    # ── Conflict (409) ─────────────────────────────────────────────────────

    def test_request_email_change_new_email_already_in_use_returns_409(self):
        # Register another user with the target new email first
        _make_verified_user(email=OTHER_EMAIL, name=OTHER_NAME)
        resp = self._post({"current_email": GENERAL_EMAIL, "new_email": OTHER_EMAIL})
        self.assertEqual(resp.status_code, 409)

    # ── Not found ──────────────────────────────────────────────────────────

    def test_request_email_change_unknown_current_email_returns_404(self):
        resp = self._post({"current_email": "ghost@example.com", "new_email": "new@example.com"})
        self.assertEqual(resp.status_code, 404)

    def test_request_email_change_soft_deleted_user_returns_404(self):
        self.profile.deleted_at = timezone.now()
        self.profile.save(update_fields=["deleted_at"])
        resp = self._post({"current_email": GENERAL_EMAIL, "new_email": "new@example.com"})
        self.assertEqual(resp.status_code, 404)

    # ── Missing / invalid input ────────────────────────────────────────────

    def test_request_email_change_missing_current_email_returns_400(self):
        resp = self._post({"new_email": "new@example.com"})
        self.assertEqual(resp.status_code, 400)

    def test_request_email_change_missing_new_email_returns_400(self):
        resp = self._post({"current_email": GENERAL_EMAIL})
        self.assertEqual(resp.status_code, 400)

    def test_request_email_change_same_email_returns_400(self):
        resp = self._post({"current_email": GENERAL_EMAIL, "new_email": GENERAL_EMAIL})
        self.assertEqual(resp.status_code, 400)

    def test_request_email_change_invalid_current_email_format_returns_400(self):
        resp = self._post({"current_email": "not-an-email", "new_email": "new@example.com"})
        self.assertEqual(resp.status_code, 400)

    def test_request_email_change_invalid_new_email_format_returns_400(self):
        resp = self._post({"current_email": GENERAL_EMAIL, "new_email": "not-an-email"})
        self.assertEqual(resp.status_code, 400)

    def test_request_email_change_invalid_json_returns_400(self):
        resp = self.client.post(
            self.url,
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_request_email_change_get_request_returns_405(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 5. VERIFY EMAIL CHANGE TESTS
# ─────────────────────────────────────────────────────────────────────────────

class VerifyEmailChangeViewTest(TestCase):
    """
    Tests for POST /api/verify-email-change/

    The view:
      - Requires JSON body: 'otp', 'new_email', 'current_email'
      - Validates the OTP hash against the stored OtpVerification row
      - On success: updates auth_user.username + email, marks OTP as used
      - Records a LOGIN_HISTORY row with purpose=UPDATE_EMAIL
      - Rejects wrong OTP (400) and increments attempt_count
      - Locks out after 5 failed attempts (marks OTP used_at)
      - Rejects expired OTP (400)
      - Rejects new_email already taken by another user (409)
    """

    # ── Helper — seed a valid, active EMAIL_CHANGE OTP ────────────────────

    RAW_OTP = "654321"

    def _seed_otp(self):
        """Create a fresh, valid EMAIL_CHANGE OTP for self.profile."""
        otp_hash = hashlib.sha256(self.RAW_OTP.encode()).hexdigest()
        return OtpVerification.objects.create(
            user=self.profile,
            otp_hash=otp_hash,
            purpose=OtpVerification.Purpose.EMAIL_CHANGE,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

    def setUp(self):
        self.client  = Client()
        self.url     = "/api/verify-email-change/"
        self.profile = _make_verified_user()
        self.new_email = "changed@example.com"

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _valid_payload(self):
        return {
            "otp":           self.RAW_OTP,
            "new_email":     self.new_email,
            "current_email": GENERAL_EMAIL,
        }

    # ── Happy path ─────────────────────────────────────────────────────────

    def test_verify_email_change_valid_otp_returns_200(self):
        self._seed_otp()
        resp = self._post(self._valid_payload())
        self.assertEqual(resp.status_code, 200)

    def test_verify_email_change_updates_email_in_db(self):
        self._seed_otp()
        self._post(self._valid_payload())
        self.profile.auth_user.refresh_from_db()
        self.assertEqual(self.profile.auth_user.email, self.new_email)
        self.assertEqual(self.profile.auth_user.username, self.new_email)

    def test_verify_email_change_marks_otp_as_used(self):
        otp_row = self._seed_otp()
        self._post(self._valid_payload())
        otp_row.refresh_from_db()
        self.assertIsNotNone(otp_row.used_at)

    def test_verify_email_change_response_contains_new_email(self):
        self._seed_otp()
        resp = self._post(self._valid_payload())
        data = json.loads(resp.content)
        self.assertEqual(data["new_email"], self.new_email)

    def test_verify_email_change_records_login_history(self):
        self._seed_otp()
        self._post(self._valid_payload())
        exists = LoginHistory.objects.filter(
            user=self.profile,
            purpose=LoginHistory.Purpose.UPDATE_EMAIL,
        ).exists()
        self.assertTrue(exists)

    # ── Wrong OTP ──────────────────────────────────────────────────────────

    def test_verify_email_change_wrong_otp_returns_400(self):
        self._seed_otp()
        payload = self._valid_payload()
        payload["otp"] = "000000"
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 400)

    def test_verify_email_change_wrong_otp_increments_attempt_count(self):
        otp_row = self._seed_otp()
        payload = self._valid_payload()
        payload["otp"] = "000000"
        self._post(payload)
        otp_row.refresh_from_db()
        self.assertEqual(otp_row.attempt_count, 1)

    def test_verify_email_change_lockout_after_5_wrong_attempts(self):
        otp_row = self._seed_otp()
        payload = self._valid_payload()
        payload["otp"] = "000000"
        for _ in range(5):
            self._post(payload)
        otp_row.refresh_from_db()
        # After 5 bad attempts the OTP must be invalidated
        self.assertIsNotNone(otp_row.used_at)

    # ── Expired OTP ────────────────────────────────────────────────────────

    def test_verify_email_change_expired_otp_returns_400(self):
        otp_hash = hashlib.sha256(self.RAW_OTP.encode()).hexdigest()
        OtpVerification.objects.create(
            user=self.profile,
            otp_hash=otp_hash,
            purpose=OtpVerification.Purpose.EMAIL_CHANGE,
            expires_at=timezone.now() - timedelta(minutes=1),  # already expired
        )
        resp = self._post(self._valid_payload())
        self.assertEqual(resp.status_code, 400)

    # ── Conflict (409) ─────────────────────────────────────────────────────

    def test_verify_email_change_new_email_taken_returns_409(self):
        _make_verified_user(email=OTHER_EMAIL, name=OTHER_NAME)
        self._seed_otp()
        payload = self._valid_payload()
        payload["new_email"] = OTHER_EMAIL
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 409)

    # ── Not found ──────────────────────────────────────────────────────────

    def test_verify_email_change_unknown_current_email_returns_404(self):
        self._seed_otp()
        payload = self._valid_payload()
        payload["current_email"] = "ghost@example.com"
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 404)

    def test_verify_email_change_soft_deleted_user_returns_404(self):
        self._seed_otp()
        self.profile.deleted_at = timezone.now()
        self.profile.save(update_fields=["deleted_at"])
        resp = self._post(self._valid_payload())
        self.assertEqual(resp.status_code, 404)

    # ── No active OTP ──────────────────────────────────────────────────────

    def test_verify_email_change_no_otp_row_returns_400(self):
        # No OTP was seeded
        resp = self._post(self._valid_payload())
        self.assertEqual(resp.status_code, 400)

    # ── Missing / invalid input ────────────────────────────────────────────

    def test_verify_email_change_missing_otp_returns_400(self):
        resp = self._post({"new_email": self.new_email, "current_email": GENERAL_EMAIL})
        self.assertEqual(resp.status_code, 400)

    def test_verify_email_change_missing_new_email_returns_400(self):
        resp = self._post({"otp": self.RAW_OTP, "current_email": GENERAL_EMAIL})
        self.assertEqual(resp.status_code, 400)

    def test_verify_email_change_missing_current_email_returns_400(self):
        resp = self._post({"otp": self.RAW_OTP, "new_email": self.new_email})
        self.assertEqual(resp.status_code, 400)

    def test_verify_email_change_non_numeric_otp_returns_400(self):
        self._seed_otp()
        payload = self._valid_payload()
        payload["otp"] = "ABCDEF"
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 400)

    def test_verify_email_change_short_otp_returns_400(self):
        self._seed_otp()
        payload = self._valid_payload()
        payload["otp"] = "123"  # not 6 digits
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 400)

    def test_verify_email_change_same_email_returns_400(self):
        self._seed_otp()
        payload = self._valid_payload()
        payload["new_email"] = GENERAL_EMAIL  # same as current
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 400)

    def test_verify_email_change_invalid_new_email_format_returns_400(self):
        self._seed_otp()
        payload = self._valid_payload()
        payload["new_email"] = "bad-email"
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 400)

    def test_verify_email_change_invalid_json_returns_400(self):
        resp = self.client.post(
            self.url,
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_verify_email_change_get_request_returns_405(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)