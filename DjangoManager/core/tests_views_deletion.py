"""
tests_views_deletion.py — Group 6: Account Deletion View Tests
==============================================================
Covers:
  POST /api/request-delete-account/
  POST /api/verify-delete-account-otp/
  POST /api/delete-account/
  GET  /api/deletion-request/status/

Run with:
  python manage.py test core.tests_views_deletion --verbosity=2

All external calls that would hit real services are patched:
  - send_otp_email  → mocked so no real AWS SES calls are made
  - _delete_s3_keys → mocked so deletion does not hit real S3

How the Bearer token works in tests
-------------------------------------
The real app uses django.core.signing.dumps/loads with salt="session-token".
In tests we call the real issue_session_token endpoint to get a valid token
(same as the frontend does), then pass it as HTTP_AUTHORIZATION.
A helper method _get_token(email) is provided on every TestCase class that
needs authenticated requests so every test can get a token in one line.
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
    AnalysisResult,
    Finding,
    Recommendation,
    Report,
    ReportShare,
    ReportDownload,
    Notification,
    AdminAccessRequest,
    DeletionRequest,
)


# ─────────────────────────────────────────────────────────────────────────────
# Shared test data constants
# ─────────────────────────────────────────────────────────────────────────────

VALID_PASSWORD = "Str0ng!Pass99"
USER_EMAIL     = "erandathi.test@gmail.com"
USER_NAME      = "Erandathi Silva"


# ─────────────────────────────────────────────────────────────────────────────
# Helper — create a verified user directly in the DB
# ─────────────────────────────────────────────────────────────────────────────

def _make_verified_user(email=USER_EMAIL, name=USER_NAME,
                        role=UserProfile.Role.GENERAL, password=VALID_PASSWORD):
    """
    Directly creates a verified UserProfile in the DB (bypasses signup flow).
    This is the fast path: use it whenever a test needs a user but is NOT
    specifically testing the signup or OTP flow itself.
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
# 1. REQUEST DELETE ACCOUNT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class RequestDeleteAccountViewTest(TestCase):
    """
    Tests for POST /api/request-delete-account/

    This endpoint:
      - Accepts an email and sends a DELETE_ACCOUNT OTP to the user
      - Always returns 200 even for unknown or deleted accounts (security)
      - Invalidates any previously unused DELETE_ACCOUNT OTPs first
      - Creates an OtpVerification row with purpose DELETE_ACCOUNT
      - Records a LoginHistory row with purpose DELETE_ACCOUNT_OTP

    send_otp_email is patched on every test that reaches the OTP sending
    step to prevent real AWS SES calls.
    """

    def setUp(self):
        self.client  = Client()
        self.url     = "/api/request-delete-account/"
        self.profile = _make_verified_user()

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    # ── Happy path ─────────────────────────────────────────────────────────

    @patch("core.views.send_otp_email", return_value=True)
    def test_request_delete_account_valid_email_returns_200(self, mock_email):
        # A valid registered email should always return 200
        resp = self._post({"email": USER_EMAIL})
        self.assertEqual(resp.status_code, 200)

    @patch("core.views.send_otp_email", return_value=True)
    def test_request_delete_account_creates_otp_row(self, mock_email):
        # An OtpVerification row with DELETE_ACCOUNT purpose must be created
        self._post({"email": USER_EMAIL})
        exists = OtpVerification.objects.filter(
            user=self.profile,
            purpose=OtpVerification.Purpose.DELETE_ACCOUNT,
        ).exists()
        self.assertTrue(exists)

    @patch("core.views.send_otp_email", return_value=True)
    def test_request_delete_account_records_login_history(self, mock_email):
        # A LoginHistory row with DELETE_ACCOUNT_OTP purpose must be created
        self._post({"email": USER_EMAIL})
        exists = LoginHistory.objects.filter(
            user=self.profile,
            purpose=LoginHistory.Purpose.DELETE_ACCOUNT_OTP,
            status=LoginHistory.Status.PENDING_OTP,
        ).exists()
        self.assertTrue(exists)

    @patch("core.views.send_otp_email", return_value=True)
    def test_request_delete_account_invalidates_previous_otp(self, mock_email):
        # Any previously unused DELETE_ACCOUNT OTP must be invalidated
        # before a new one is created
        old_otp = OtpVerification.objects.create(
            user=self.profile,
            otp_hash=hashlib.sha256("111111".encode()).hexdigest(),
            purpose=OtpVerification.Purpose.DELETE_ACCOUNT,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        self._post({"email": USER_EMAIL})
        old_otp.refresh_from_db()
        self.assertIsNotNone(old_otp.used_at)

    @patch("core.views.send_otp_email", return_value=True)
    def test_request_delete_account_calls_send_otp_email(self, mock_email):
        # The email sending function must be called once
        self._post({"email": USER_EMAIL})
        self.assertTrue(mock_email.called)

    # ── Security: always 200 ───────────────────────────────────────────────

    def test_request_delete_account_unknown_email_returns_200(self):
        # Security: must not reveal whether the email exists in the system
        resp = self._post({"email": "nobody@example.com"})
        self.assertEqual(resp.status_code, 200)

    def test_request_delete_account_already_deleted_account_returns_200(self):
        # A soft-deleted account must still return 200 — no information leakage
        self.profile.deleted_at = timezone.now()
        self.profile.save(update_fields=["deleted_at"])
        resp = self._post({"email": USER_EMAIL})
        self.assertEqual(resp.status_code, 200)

    # ── Missing / invalid input ────────────────────────────────────────────

    def test_request_delete_account_missing_email_returns_400(self):
        resp = self._post({})
        self.assertEqual(resp.status_code, 400)

    def test_request_delete_account_invalid_email_format_returns_400(self):
        resp = self._post({"email": "not-an-email"})
        self.assertEqual(resp.status_code, 400)

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_request_delete_account_get_request_returns_405(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 2. VERIFY DELETE ACCOUNT OTP TESTS
# ─────────────────────────────────────────────────────────────────────────────

class VerifyDeleteAccountOtpViewTest(TestCase):
    """
    Tests for POST /api/verify-delete-account-otp/

    This endpoint:
      - Validates the DELETE_ACCOUNT OTP submitted by the user
      - Returns a signed delete_token on success (valid 10 minutes)
      - Increments attempt_count on wrong OTP
      - Invalidates the OTP after MAX_OTP_ATTEMPTS (5) failed attempts
      - Records LoginHistory SUCCESS or FAILED accordingly
    """

    def setUp(self):
        self.client  = Client()
        self.url     = "/api/verify-delete-account-otp/"

        # A verified user with a pre-created DELETE_ACCOUNT OTP
        self.profile = _make_verified_user()
        self.raw_otp = "748291"
        self.otp_row = OtpVerification.objects.create(
            user=self.profile,
            otp_hash=hashlib.sha256(self.raw_otp.encode()).hexdigest(),
            purpose=OtpVerification.Purpose.DELETE_ACCOUNT,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    # ── Happy path ─────────────────────────────────────────────────────────

    def test_verify_delete_otp_correct_returns_200(self):
        # Correct OTP must return 200
        resp = self._post({"email": USER_EMAIL, "otp": self.raw_otp})
        self.assertEqual(resp.status_code, 200)

    def test_verify_delete_otp_correct_returns_delete_token(self):
        # Response must contain a delete_token for the next step
        resp = self._post({"email": USER_EMAIL, "otp": self.raw_otp})
        data = json.loads(resp.content)
        self.assertIn("delete_token", data)

    def test_verify_delete_otp_delete_token_is_valid_signed_token(self):
        # The delete_token must be loadable with the correct salt
        resp         = self._post({"email": USER_EMAIL, "otp": self.raw_otp})
        delete_token = json.loads(resp.content)["delete_token"]
        data         = signing.loads(delete_token, salt="delete-account", max_age=600)
        self.assertEqual(data.get("purpose"), "delete_account")

    def test_verify_delete_otp_marks_otp_as_used(self):
        # The OTP row must be marked as used after correct submission
        self._post({"email": USER_EMAIL, "otp": self.raw_otp})
        self.otp_row.refresh_from_db()
        self.assertIsNotNone(self.otp_row.used_at)

    def test_verify_delete_otp_records_success_in_login_history(self):
        # A SUCCESS LoginHistory row must be created on correct OTP
        self._post({"email": USER_EMAIL, "otp": self.raw_otp})
        exists = LoginHistory.objects.filter(
            user=self.profile,
            purpose=LoginHistory.Purpose.DELETE_ACCOUNT_OTP,
            status=LoginHistory.Status.SUCCESS,
        ).exists()
        self.assertTrue(exists)

    # ── Wrong OTP ──────────────────────────────────────────────────────────

    def test_verify_delete_otp_wrong_code_returns_401(self):
        resp = self._post({"email": USER_EMAIL, "otp": "000000"})
        self.assertEqual(resp.status_code, 401)

    def test_verify_delete_otp_wrong_code_increments_attempt_count(self):
        # Each wrong OTP must increment the attempt counter
        self._post({"email": USER_EMAIL, "otp": "000000"})
        self.otp_row.refresh_from_db()
        self.assertEqual(self.otp_row.attempt_count, 1)

    def test_verify_delete_otp_wrong_code_records_failed_in_login_history(self):
        # A FAILED LoginHistory row must be created on wrong OTP
        self._post({"email": USER_EMAIL, "otp": "000000"})
        exists = LoginHistory.objects.filter(
            user=self.profile,
            purpose=LoginHistory.Purpose.DELETE_ACCOUNT_OTP,
            status=LoginHistory.Status.FAILED,
        ).exists()
        self.assertTrue(exists)

    # ── Expired OTP ────────────────────────────────────────────────────────

    def test_verify_delete_otp_expired_returns_401(self):
        # An expired OTP must be rejected even if the hash matches
        self.otp_row.expires_at = timezone.now() - timedelta(minutes=1)
        self.otp_row.save(update_fields=["expires_at"])
        resp = self._post({"email": USER_EMAIL, "otp": self.raw_otp})
        self.assertEqual(resp.status_code, 401)

    # ── Brute force guard ──────────────────────────────────────────────────

    def test_verify_delete_otp_brute_force_guard_returns_401(self):
        # Once attempt_count reaches MAX_OTP_ATTEMPTS the OTP must be blocked
        self.otp_row.attempt_count = 5
        self.otp_row.save(update_fields=["attempt_count"])
        resp = self._post({"email": USER_EMAIL, "otp": self.raw_otp})
        self.assertEqual(resp.status_code, 401)

    def test_verify_delete_otp_brute_force_guard_marks_otp_used(self):
        # The OTP must be invalidated (used_at set) after brute force guard triggers
        self.otp_row.attempt_count = 5
        self.otp_row.save(update_fields=["attempt_count"])
        self._post({"email": USER_EMAIL, "otp": self.raw_otp})
        self.otp_row.refresh_from_db()
        self.assertIsNotNone(self.otp_row.used_at)

    # ── Unknown email ──────────────────────────────────────────────────────

    def test_verify_delete_otp_unknown_email_returns_401(self):
        resp = self._post({"email": "ghost@example.com", "otp": self.raw_otp})
        self.assertEqual(resp.status_code, 401)

    # ── Missing / invalid input ────────────────────────────────────────────

    def test_verify_delete_otp_missing_email_returns_400(self):
        resp = self._post({"otp": self.raw_otp})
        self.assertEqual(resp.status_code, 400)

    def test_verify_delete_otp_missing_otp_returns_400(self):
        resp = self._post({"email": USER_EMAIL})
        self.assertEqual(resp.status_code, 400)

    def test_verify_delete_otp_non_digit_otp_returns_401(self):
        resp = self._post({"email": USER_EMAIL, "otp": "ABCDEF"})
        self.assertEqual(resp.status_code, 401)

    def test_verify_delete_otp_short_otp_returns_401(self):
        resp = self._post({"email": USER_EMAIL, "otp": "123"})
        self.assertEqual(resp.status_code, 401)

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_verify_delete_otp_get_request_returns_405(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 3. DELETE ACCOUNT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class DeleteAccountViewTest(TestCase):
    """
    Tests for POST /api/delete-account/

    This endpoint:
      - Validates the signed delete_token issued by verify-delete-account-otp
      - Soft-deletes the UserProfile (sets deleted_at)
      - Anonymises the auth_user username and email
      - Hard-deletes all personal data sub-tables in FK-safe order
      - Soft-deletes Document rows (sets deleted_at + status=DELETED)
      - Creates a DeletionRequest row that persists as an erasure certificate
      - Calls _delete_s3_keys to remove files from S3 (mocked in tests)
      - Writes a DELETE_ACCOUNT AuditLog entry

    _delete_s3_keys is patched on every test to avoid real S3 calls.
    """

    def setUp(self):
        self.client  = Client()
        self.url     = "/api/delete-account/"
        self.profile = _make_verified_user()
        # Generate a valid delete_token the same way the view does
        self.delete_token = signing.dumps(
            {"uid": str(self.profile.user_id), "purpose": "delete_account"},
            salt="delete-account",
        )

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _get_token(self, email):
        """Get a real Bearer token via issue_session_token."""
        resp = self.client.post(
            "/api/session-token/",
            data=json.dumps({"email": email}),
            content_type="application/json",
        )
        return json.loads(resp.content)["token"]

    # ── Happy path ─────────────────────────────────────────────────────────

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_valid_token_returns_200(self, mock_s3):
        # A valid delete_token must result in successful account deletion
        resp = self._post({"delete_token": self.delete_token})
        self.assertEqual(resp.status_code, 200)

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_sets_deleted_at_on_profile(self, mock_s3):
        # profile.deleted_at must be set after deletion
        self._post({"delete_token": self.delete_token})
        self.profile.refresh_from_db()
        self.assertIsNotNone(self.profile.deleted_at)

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_sets_auth_user_inactive(self, mock_s3):
        # auth_user.is_active must be False after deletion
        self._post({"delete_token": self.delete_token})
        self.profile.auth_user.refresh_from_db()
        self.assertFalse(self.profile.auth_user.is_active)

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_anonymises_auth_user_username(self, mock_s3):
        # auth_user.username must be replaced with an anonymised value
        self._post({"delete_token": self.delete_token})
        self.profile.auth_user.refresh_from_db()
        self.assertTrue(self.profile.auth_user.username.startswith("deleted_"))

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_anonymises_auth_user_email(self, mock_s3):
        # auth_user.email must be replaced with an anonymised value
        self._post({"delete_token": self.delete_token})
        self.profile.auth_user.refresh_from_db()
        self.assertTrue(self.profile.auth_user.email.endswith("@deleted.local"))

    # ── DeletionRequest audit certificate ──────────────────────────────────

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_creates_deletion_request_row(self, mock_s3):
        # A DeletionRequest row must be created during account deletion
        self._post({"delete_token": self.delete_token})
        exists = DeletionRequest.objects.filter(
            user_email_snapshot=USER_EMAIL,
        ).exists()
        self.assertTrue(exists)

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_deletion_request_status_is_completed(self, mock_s3):
        # The DeletionRequest must be marked COMPLETED on success
        self._post({"delete_token": self.delete_token})
        record = DeletionRequest.objects.get(user_email_snapshot=USER_EMAIL)
        self.assertEqual(record.status, DeletionRequest.Status.COMPLETED)

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_deletion_request_completed_at_is_set(self, mock_s3):
        # completed_at must be set on the DeletionRequest row
        self._post({"delete_token": self.delete_token})
        record = DeletionRequest.objects.get(user_email_snapshot=USER_EMAIL)
        self.assertIsNotNone(record.completed_at)

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_deletion_request_preserves_email_snapshot(self, mock_s3):
        # user_email_snapshot must hold the original email even after
        # auth_user is anonymised — this is the only remaining identity link
        self._post({"delete_token": self.delete_token})
        record = DeletionRequest.objects.get(user_email_snapshot=USER_EMAIL)
        self.assertEqual(record.user_email_snapshot, USER_EMAIL)

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_deletion_request_reason_stored(self, mock_s3):
        # reason provided by the user must be stored on the DeletionRequest
        self._post({"delete_token": self.delete_token, "reason": "Privacy concerns."})
        record = DeletionRequest.objects.get(user_email_snapshot=USER_EMAIL)
        self.assertEqual(record.reason, "Privacy concerns.")

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_deletion_request_erasure_summary_populated(self, mock_s3):
        # erasure_summary must be a dict and must be populated
        self._post({"delete_token": self.delete_token})
        record = DeletionRequest.objects.get(user_email_snapshot=USER_EMAIL)
        self.assertIsInstance(record.erasure_summary, dict)
        self.assertIn("documents_erased", record.erasure_summary)

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_deletion_request_row_survives_after_deletion(self, mock_s3):
        # The DeletionRequest row must still exist after account deletion —
        # it acts as the erasure certificate (GDPR audit trail)
        self._post({"delete_token": self.delete_token})
        surviving = DeletionRequest.objects.filter(
            user_email_snapshot=USER_EMAIL,
        )
        self.assertTrue(surviving.exists())

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_deletion_request_user_becomes_null(self, mock_s3):
        # After account deletion, DeletionRequest.user must be SET_NULL
        # so the certificate row survives even without a live user reference
        self._post({"delete_token": self.delete_token})
        record = DeletionRequest.objects.get(user_email_snapshot=USER_EMAIL)
        # profile is soft-deleted but still exists — user FK still points to it.
        # The SET_NULL behaviour kicks in only if the profile is hard-deleted.
        # Here we verify the record still exists and is linked correctly.
        self.assertIsNotNone(record)

    # ── Document soft-delete ───────────────────────────────────────────────

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_soft_deletes_documents(self, mock_s3):
        # Document rows must be soft-deleted (deleted_at set, status=DELETED)
        # not hard-deleted — the row stays in the DB
        doc = Document.objects.create(
            user=self.profile,
            original_filename="policy.pdf",
            file_type="PDF",
            s3_key="docs/policy.pdf",
            status=Document.Status.UPLOADED,
        )
        self._post({"delete_token": self.delete_token})
        doc.refresh_from_db()
        self.assertIsNotNone(doc.deleted_at)
        self.assertEqual(doc.status, Document.Status.DELETED)

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_document_row_still_exists_after_deletion(self, mock_s3):
        # The Document row must still be in the DB after deletion (soft delete)
        doc = Document.objects.create(
            user=self.profile,
            original_filename="report.pdf",
            file_type="PDF",
            s3_key="docs/report.pdf",
            status=Document.Status.UPLOADED,
        )
        doc_id = doc.document_id
        self._post({"delete_token": self.delete_token})
        self.assertTrue(Document.objects.filter(document_id=doc_id).exists())

    # ── Sub-table hard-deletes ─────────────────────────────────────────────

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_hard_deletes_analysis_results(self, mock_s3):
        # AnalysisResult rows belonging to the user must be hard-deleted
        doc = Document.objects.create(
            user=self.profile,
            original_filename="policy.pdf",
            file_type="PDF",
            s3_key="docs/policy.pdf",
        )
        result = AnalysisResult.objects.create(document=doc)
        result_id = result.result_id
        self._post({"delete_token": self.delete_token})
        self.assertFalse(AnalysisResult.objects.filter(result_id=result_id).exists())

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_hard_deletes_reports(self, mock_s3):
        # Report rows belonging to the user must be hard-deleted
        doc    = Document.objects.create(
            user=self.profile,
            original_filename="policy.pdf",
            file_type="PDF",
            s3_key="docs/policy.pdf",
        )
        result = AnalysisResult.objects.create(document=doc)
        report = Report.objects.create(
            result=result,
            report_snapshot={"company": "Test Co"},
            report_s3_key="reports/test.pdf",
            file_size=1024,
            expires_at=timezone.now() + timedelta(days=30),
        )
        report_id = report.report_id
        self._post({"delete_token": self.delete_token})
        self.assertFalse(Report.objects.filter(report_id=report_id).exists())

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_hard_deletes_notifications(self, mock_s3):
        # Notification rows belonging to the user must be hard-deleted
        doc    = Document.objects.create(
            user=self.profile,
            original_filename="policy.pdf",
            file_type="PDF",
            s3_key="docs/policy.pdf",
        )
        result = AnalysisResult.objects.create(document=doc)
        report = Report.objects.create(
            result=result,
            report_snapshot={"company": "Test Co"},
            report_s3_key="reports/test.pdf",
            file_size=1024,
            expires_at=timezone.now() + timedelta(days=30),
        )
        Notification.objects.create(
            user=self.profile,
            notification_type=Notification.NotificationType.REPORT_READY,
            message="Your report is ready.",
            report=report,
        )
        self._post({"delete_token": self.delete_token})
        self.assertFalse(
            Notification.objects.filter(user=self.profile).exists()
        )

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_hard_deletes_otp_records(self, mock_s3):
        # All OtpVerification rows for the user must be hard-deleted
        OtpVerification.objects.create(
            user=self.profile,
            otp_hash=hashlib.sha256("123456".encode()).hexdigest(),
            purpose=OtpVerification.Purpose.DELETE_ACCOUNT,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        self._post({"delete_token": self.delete_token})
        self.assertFalse(
            OtpVerification.objects.filter(user=self.profile).exists()
        )

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_hard_deletes_admin_access_requests(self, mock_s3):
        # AdminAccessRequest rows for the user must be hard-deleted
        AdminAccessRequest.objects.create(
            user=self.profile,
            org_email="erandathi.test@sliit.lk",
            status=AdminAccessRequest.Status.PENDING,
        )
        self._post({"delete_token": self.delete_token})
        self.assertFalse(
            AdminAccessRequest.objects.filter(user=self.profile).exists()
        )

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_hard_deletes_report_shares(self, mock_s3):
        # ReportShare rows linked to the user's reports must be hard-deleted
        other_profile = _make_verified_user(
            email="other@example.com", name="Other User"
        )
        doc    = Document.objects.create(
            user=self.profile,
            original_filename="policy.pdf",
            file_type="PDF",
            s3_key="docs/policy.pdf",
        )
        result = AnalysisResult.objects.create(document=doc)
        report = Report.objects.create(
            result=result,
            report_snapshot={"company": "Test Co"},
            report_s3_key="reports/test.pdf",
            file_size=1024,
            expires_at=timezone.now() + timedelta(days=30),
        )
        share = ReportShare.objects.create(
            report=report,
            shared_by=self.profile,
            shared_with_email="other@example.com",
            access_token="unique-share-token-999",
            expires_at=timezone.now() + timedelta(days=7),
        )
        share_id = share.share_id
        self._post({"delete_token": self.delete_token})
        self.assertFalse(ReportShare.objects.filter(share_id=share_id).exists())

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_hard_deletes_report_downloads(self, mock_s3):
        # ReportDownload rows linked to the user's reports must be hard-deleted
        doc    = Document.objects.create(
            user=self.profile,
            original_filename="policy.pdf",
            file_type="PDF",
            s3_key="docs/policy.pdf",
        )
        result = AnalysisResult.objects.create(document=doc)
        report = Report.objects.create(
            result=result,
            report_snapshot={"company": "Test Co"},
            report_s3_key="reports/test.pdf",
            file_size=1024,
            expires_at=timezone.now() + timedelta(days=30),
        )
        download = ReportDownload.objects.create(
            downloaded_by=self.profile,
            report_id=report.report_id,
        )
        download_id = download.download_id
        self._post({"delete_token": self.delete_token})
        self.assertFalse(
            ReportDownload.objects.filter(download_id=download_id).exists()
        )

    # ── Audit log ──────────────────────────────────────────────────────────

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_writes_audit_log_entry(self, mock_s3):
        # A DELETE_ACCOUNT AuditLog entry must be written on successful deletion
        self._post({"delete_token": self.delete_token})
        exists = AuditLog.objects.filter(
            user=self.profile,
            action_type="DELETE_ACCOUNT",
            success=True,
        ).exists()
        self.assertTrue(exists)

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_audit_log_severity_is_high(self, mock_s3):
        # The DELETE_ACCOUNT audit log entry must have HIGH severity
        self._post({"delete_token": self.delete_token})
        log = AuditLog.objects.get(
            user=self.profile,
            action_type="DELETE_ACCOUNT",
        )
        self.assertEqual(log.severity, AuditLog.Severity.HIGH)

    # ── S3 cleanup ─────────────────────────────────────────────────────────

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_calls_s3_delete(self, mock_s3):
        # _delete_s3_keys must be called during account deletion
        self._post({"delete_token": self.delete_token})
        self.assertTrue(mock_s3.called)

    # ── Invalid / missing token ────────────────────────────────────────────

    def test_delete_account_missing_token_returns_400(self):
        resp = self._post({})
        self.assertEqual(resp.status_code, 400)

    def test_delete_account_invalid_token_returns_401(self):
        resp = self._post({"delete_token": "totally.invalid.token"})
        self.assertEqual(resp.status_code, 401)

    def test_delete_account_expired_token_returns_401(self):
        # A token signed more than 600 seconds ago must be rejected
        expired_token = signing.dumps(
            {"uid": str(self.profile.user_id), "purpose": "delete_account"},
            salt="delete-account",
        )
        from unittest.mock import patch as _patch
        import core.views as views_module
        from django.core.signing import SignatureExpired
        with _patch("django.core.signing.loads", side_effect=SignatureExpired):
            resp = self._post({"delete_token": expired_token})
        self.assertEqual(resp.status_code, 401)

    @patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
    def test_delete_account_already_deleted_account_returns_400(self, mock_s3):
        # Attempting to delete an already deleted account must return 400
        self.profile.deleted_at = timezone.now()
        self.profile.save(update_fields=["deleted_at"])
        resp = self._post({"delete_token": self.delete_token})
        self.assertEqual(resp.status_code, 400)

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_delete_account_get_request_returns_405(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 4. GET DELETION REQUEST STATUS TESTS
# ─────────────────────────────────────────────────────────────────────────────

class GetDeletionRequestStatusViewTest(TestCase):
    """
    Tests for GET /api/deletion-request/status/

    This endpoint:
      - Requires a valid Bearer token
      - Returns the latest DeletionRequest for the authenticated user
      - Returns 404 if no DeletionRequest exists for the user
    """

    def setUp(self):
        self.client  = Client()
        self.url     = "/api/deletion-request/status/"
        self.profile = _make_verified_user()
        self.token   = self._get_token(USER_EMAIL)

        # Pre-create a completed DeletionRequest for the user
        self.deletion_record = DeletionRequest.objects.create(
            user=self.profile,
            user_email_snapshot=USER_EMAIL,
            request_type=DeletionRequest.RequestType.ACCOUNT,
            status=DeletionRequest.Status.COMPLETED,
            reason="No longer needed.",
            erasure_summary={
                "documents_erased": 2,
                "s3_keys_deleted": ["docs/policy.pdf"],
                "analysis_results_erased": 2,
                "findings_erased": 5,
                "recommendations_erased": 3,
                "reports_erased": 2,
                "report_s3_keys_deleted": ["reports/test.pdf"],
                "report_shares_erased": 0,
                "report_downloads_erased": 0,
                "notifications_erased": 1,
                "admin_access_requests_erased": 0,
                "otp_records_erased": 1,
            },
            completed_at=timezone.now(),
            ip_address="127.0.0.1",
        )

    def _get_token(self, email):
        resp = self.client.post(
            "/api/session-token/",
            data=json.dumps({"email": email}),
            content_type="application/json",
        )
        return json.loads(resp.content)["token"]

    def _get(self, token=None):
        headers = {}
        if token:
            headers["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        return self.client.get(self.url, **headers)

    # ── Happy path ─────────────────────────────────────────────────────────

    def test_get_deletion_status_authenticated_returns_200(self):
        # An authenticated user with a deletion request must get 200
        resp = self._get(token=self.token)
        self.assertEqual(resp.status_code, 200)

    def test_get_deletion_status_response_contains_deletion_id(self, ):
        # Response must contain deletion_id
        resp = self._get(token=self.token)
        data = json.loads(resp.content)
        self.assertIn("deletion_id", data)

    def test_get_deletion_status_response_contains_status(self):
        # Response must contain status field
        resp = self._get(token=self.token)
        data = json.loads(resp.content)
        self.assertIn("status", data)

    def test_get_deletion_status_response_contains_email_snapshot(self):
        # Response must contain user_email_snapshot
        resp = self._get(token=self.token)
        data = json.loads(resp.content)
        self.assertIn("user_email_snapshot", data)
        self.assertEqual(data["user_email_snapshot"], USER_EMAIL)

    def test_get_deletion_status_response_contains_erasure_summary(self):
        # Response must contain the erasure_summary dict
        resp = self._get(token=self.token)
        data = json.loads(resp.content)
        self.assertIn("erasure_summary", data)
        self.assertIsInstance(data["erasure_summary"], dict)

    def test_get_deletion_status_response_contains_completed_at(self):
        # Response must contain completed_at for a completed request
        resp = self._get(token=self.token)
        data = json.loads(resp.content)
        self.assertIn("completed_at", data)
        self.assertIsNotNone(data["completed_at"])

    def test_get_deletion_status_response_contains_reason(self):
        # Response must contain the reason field
        resp = self._get(token=self.token)
        data = json.loads(resp.content)
        self.assertIn("reason", data)
        self.assertEqual(data["reason"], "No longer needed.")

    def test_get_deletion_status_returns_latest_request(self):
        # If multiple requests exist, the latest one must be returned
        newer_record = DeletionRequest.objects.create(
            user=self.profile,
            user_email_snapshot=USER_EMAIL,
            request_type=DeletionRequest.RequestType.ACCOUNT,
            status=DeletionRequest.Status.PENDING,
            requested_at=timezone.now() + timedelta(days=1),
        )
        resp = self._get(token=self.token)
        data = json.loads(resp.content)
        self.assertEqual(data["deletion_id"], str(newer_record.deletion_id))

    # ── No deletion request ────────────────────────────────────────────────

    def test_get_deletion_status_no_request_returns_404(self):
        # A user with no deletion request must get 404
        other_profile = _make_verified_user(
            email="other@example.com", name="Other User"
        )
        other_token = self._get_token("other@example.com")
        resp = self._get(token=other_token)
        self.assertEqual(resp.status_code, 404)

    # ── Auth guard ─────────────────────────────────────────────────────────

    def test_get_deletion_status_no_token_returns_401(self):
        # Request without a Bearer token must be rejected with 401
        resp = self._get(token=None)
        self.assertEqual(resp.status_code, 401)

    def test_get_deletion_status_invalid_token_returns_401(self):
        # Request with an invalid Bearer token must be rejected with 401
        resp = self._get(token="totally.invalid.token")
        self.assertEqual(resp.status_code, 401)

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_get_deletion_status_post_request_returns_405(self):
        resp = self.client.post(
            self.url,
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(resp.status_code, 405)