"""
tests_views_admin.py — Group 7: Admin Access + Notification View Tests
=====================================================================
Covers:
  POST /api/admin-access/request/
  POST /api/admin-access/verify/
  GET  /api/admin-access/status/
  GET  /api/notifications/unread/
  POST /api/notifications/mark-read/

Run with:
  python manage.py test core.tests_views_admin --verbosity=2
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
    AdminAccessRequest,
    Notification,
)


VALID_PASSWORD = "Str0ng!Pass99"
GENERAL_EMAIL = "sehansa.test@gmail.com"
GENERAL_NAME = "Sehansa Samarakoon"
ORG_EMAIL = "sehansa@sliit.lk"


def _make_verified_user(email=GENERAL_EMAIL, name=GENERAL_NAME,
                        role=UserProfile.Role.GENERAL, password=VALID_PASSWORD):
    auth_user = User.objects.create_user(
        username=email,
        email=email,
        password=password,
    )
    return UserProfile.objects.create(
        auth_user=auth_user,
        full_name=name,
        role=role,
        is_verified=True,
        otp_is_enabled=False,
    )


def _get_token(client, email):
    resp = client.post(
        "/api/session-token/",
        data=json.dumps({"email": email}),
        content_type="application/json",
    )
    return json.loads(resp.content)["token"]


class AdminAccessViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.profile = _make_verified_user()
        self.token = _get_token(self.client, GENERAL_EMAIL)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def _post_request(self, payload, token=None):
        headers = self._auth() if token is None else {
            "HTTP_AUTHORIZATION": f"Bearer {token}"
        }
        return self.client.post(
            "/api/admin-access/request/",
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def _post_verify(self, payload, token=None):
        headers = self._auth() if token is None else {
            "HTTP_AUTHORIZATION": f"Bearer {token}"
        }
        return self.client.post(
            "/api/admin-access/verify/",
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    # ── Admin access request ──────────────────────────────────────────────

    @patch("core.views.random.randint", return_value=123456)
    @patch("core.views.send_otp_email", return_value=True)
    def test_admin_access_request_valid_org_email_returns_201(self, mock_email, mock_rand):
        resp = self._post_request({"org_email": ORG_EMAIL})
        self.assertEqual(resp.status_code, 201)

        data = json.loads(resp.content)
        self.assertIn("request_id", data)

    @patch("core.views.random.randint", return_value=123456)
    @patch("core.views.send_otp_email", return_value=True)
    def test_admin_access_request_creates_pending_request(self, mock_email, mock_rand):
        self._post_request({"org_email": ORG_EMAIL})

        exists = AdminAccessRequest.objects.filter(
            user=self.profile,
            org_email=ORG_EMAIL,
            status=AdminAccessRequest.Status.PENDING,
        ).exists()
        self.assertTrue(exists)

    @patch("core.views.random.randint", return_value=123456)
    @patch("core.views.send_otp_email", return_value=True)
    def test_admin_access_request_creates_admin_otp(self, mock_email, mock_rand):
        self._post_request({"org_email": ORG_EMAIL})

        otp = OtpVerification.objects.filter(
            user=self.profile,
            purpose=OtpVerification.Purpose.ADMIN_REQUEST_VERIFY,
            used_at__isnull=True,
        ).first()

        self.assertIsNotNone(otp)
        assert otp is not None
        self.assertEqual(
            otp.otp_hash,
            hashlib.sha256("123456".encode()).hexdigest(),
        )

    def test_admin_access_request_no_token_returns_401(self):
        resp = self.client.post(
            "/api/admin-access/request/",
            data=json.dumps({"org_email": ORG_EMAIL}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_admin_access_request_invalid_token_returns_401(self):
        resp = self.client.post(
            "/api/admin-access/request/",
            data=json.dumps({"org_email": ORG_EMAIL}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer bad.token.value",
        )
        self.assertEqual(resp.status_code, 401)

    def test_admin_access_request_missing_org_email_returns_400(self):
        resp = self._post_request({})
        self.assertEqual(resp.status_code, 400)

    def test_admin_access_request_invalid_email_returns_400(self):
        resp = self._post_request({"org_email": "not-an-email"})
        self.assertEqual(resp.status_code, 400)

    def test_admin_access_request_personal_email_returns_400(self):
        resp = self._post_request({"org_email": "sehansa@gmail.com"})
        self.assertEqual(resp.status_code, 400)

    @patch("core.views.random.randint", return_value=123456)
    @patch("core.views.send_otp_email", return_value=True)
    def test_admin_access_request_duplicate_pending_returns_409(self, mock_email, mock_rand):
        self._post_request({"org_email": ORG_EMAIL})
        resp = self._post_request({"org_email": ORG_EMAIL})
        self.assertEqual(resp.status_code, 409)

    def test_admin_access_request_existing_admin_returns_400(self):
        admin = _make_verified_user(
            email="admin@sliit.lk",
            name="Admin User",
            role=UserProfile.Role.ADMIN,
        )
        admin_token = _get_token(self.client, "admin@sliit.lk")

        resp = self._post_request(
            {"org_email": "admin@sliit.lk"},
            token=admin_token,
        )
        self.assertEqual(resp.status_code, 400)

    def test_admin_access_request_get_returns_405(self):
        resp = self.client.get("/api/admin-access/request/", **self._auth())
        self.assertEqual(resp.status_code, 405)

    # ── Admin access verify ───────────────────────────────────────────────

    def _create_pending_admin_request(self, raw_otp="123456"):
        otp = OtpVerification.objects.create(
            user=self.profile,
            otp_hash=hashlib.sha256(raw_otp.encode()).hexdigest(),
            purpose=OtpVerification.Purpose.ADMIN_REQUEST_VERIFY,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        return AdminAccessRequest.objects.create(
            user=self.profile,
            verification_otp=otp,
            org_email=ORG_EMAIL,
            original_email=GENERAL_EMAIL,
            status=AdminAccessRequest.Status.PENDING,
        )

    def test_verify_admin_access_correct_otp_returns_200(self):
        req = self._create_pending_admin_request()

        resp = self._post_verify({
            "request_id": str(req.request_id),
            "otp": "123456",
        })

        self.assertEqual(resp.status_code, 200)

    def test_verify_admin_access_correct_otp_upgrades_role_to_admin(self):
        req = self._create_pending_admin_request()

        self._post_verify({
            "request_id": str(req.request_id),
            "otp": "123456",
        })

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.role, UserProfile.Role.ADMIN)

    def test_verify_admin_access_correct_otp_changes_user_email(self):
        req = self._create_pending_admin_request()

        self._post_verify({
            "request_id": str(req.request_id),
            "otp": "123456",
        })

        self.profile.auth_user.refresh_from_db()
        self.assertEqual(self.profile.auth_user.email, ORG_EMAIL)
        self.assertEqual(self.profile.auth_user.username, ORG_EMAIL)

    def test_verify_admin_access_correct_otp_marks_request_approved(self):
        req = self._create_pending_admin_request()

        self._post_verify({
            "request_id": str(req.request_id),
            "otp": "123456",
        })

        req.refresh_from_db()
        self.assertEqual(req.status, AdminAccessRequest.Status.APPROVED)
        self.assertIsNotNone(req.verified_at)

    def test_verify_admin_access_wrong_otp_returns_401(self):
        req = self._create_pending_admin_request()

        resp = self._post_verify({
            "request_id": str(req.request_id),
            "otp": "000000",
        })

        self.assertEqual(resp.status_code, 401)

    def test_verify_admin_access_wrong_otp_increments_attempt_count(self):
        req = self._create_pending_admin_request()

        self._post_verify({
            "request_id": str(req.request_id),
            "otp": "000000",
        })

        req.verification_otp.refresh_from_db()
        self.assertEqual(req.verification_otp.attempt_count, 1)

    def test_verify_admin_access_missing_fields_returns_400(self):
        resp = self._post_verify({})
        self.assertEqual(resp.status_code, 400)

    def test_verify_admin_access_invalid_otp_format_returns_401(self):
        req = self._create_pending_admin_request()

        resp = self._post_verify({
            "request_id": str(req.request_id),
            "otp": "abc123",
        })

        self.assertEqual(resp.status_code, 401)

    def test_verify_admin_access_unknown_request_returns_404(self):
        resp = self._post_verify({
            "request_id": "00000000-0000-0000-0000-000000000000",
            "otp": "123456",
        })

        self.assertEqual(resp.status_code, 404)

    def test_verify_admin_access_expired_otp_returns_401(self):
        req = self._create_pending_admin_request()
        otp = req.verification_otp
        otp.expires_at = timezone.now() - timedelta(minutes=1)
        otp.save(update_fields=["expires_at"])

        resp = self._post_verify({
            "request_id": str(req.request_id),
            "otp": "123456",
        })

        self.assertEqual(resp.status_code, 401)

    def test_verify_admin_access_too_many_attempts_rejects_request(self):
        req = self._create_pending_admin_request()
        otp = req.verification_otp
        otp.attempt_count = 5
        otp.save(update_fields=["attempt_count"])

        resp = self._post_verify({
            "request_id": str(req.request_id),
            "otp": "123456",
        })

        req.refresh_from_db()
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(req.status, AdminAccessRequest.Status.REJECTED)

    def test_verify_admin_access_no_token_returns_401(self):
        req = self._create_pending_admin_request()

        resp = self.client.post(
            "/api/admin-access/verify/",
            data=json.dumps({
                "request_id": str(req.request_id),
                "otp": "123456",
            }),
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 401)

    def test_verify_admin_access_get_returns_405(self):
        resp = self.client.get("/api/admin-access/verify/", **self._auth())
        self.assertEqual(resp.status_code, 405)

    # ── Admin access status ───────────────────────────────────────────────

    def test_admin_access_status_existing_request_returns_200(self):
        req = self._create_pending_admin_request()

        resp = self.client.get("/api/admin-access/status/", **self._auth())

        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data["request_id"], str(req.request_id))
        self.assertEqual(data["status"], AdminAccessRequest.Status.PENDING)

    def test_admin_access_status_no_request_returns_404(self):
        resp = self.client.get("/api/admin-access/status/", **self._auth())
        self.assertEqual(resp.status_code, 404)

    def test_admin_access_status_no_token_returns_401(self):
        resp = self.client.get("/api/admin-access/status/")
        self.assertEqual(resp.status_code, 401)

    def test_admin_access_status_post_returns_405(self):
        resp = self.client.post("/api/admin-access/status/", **self._auth())
        self.assertEqual(resp.status_code, 405)


class NotificationViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.profile = _make_verified_user()
        self.token = _get_token(self.client, GENERAL_EMAIL)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def _create_notification(self, message="Test notification", is_read=False):
        return Notification.objects.create(
            user=self.profile,
            notification_type=Notification.NotificationType.REPORT_READY,
            message=message,
            is_read=is_read,
        )

    # ── Unread notifications ──────────────────────────────────────────────

    def test_get_unread_notifications_returns_200(self):
        self._create_notification()

        resp = self.client.get("/api/notifications/unread/", **self._auth())

        self.assertEqual(resp.status_code, 200)

    def test_get_unread_notifications_returns_count_and_list(self):
        self._create_notification("One")
        self._create_notification("Two")

        resp = self.client.get("/api/notifications/unread/", **self._auth())
        data = json.loads(resp.content)

        self.assertEqual(data["unread_count"], 2)
        self.assertEqual(len(data["notifications"]), 2)

    def test_get_unread_notifications_excludes_read_notifications(self):
        self._create_notification("Unread", is_read=False)
        self._create_notification("Read", is_read=True)

        resp = self.client.get("/api/notifications/unread/", **self._auth())
        data = json.loads(resp.content)

        self.assertEqual(data["unread_count"], 1)

    def test_get_unread_notifications_no_token_returns_401(self):
        resp = self.client.get("/api/notifications/unread/")
        self.assertEqual(resp.status_code, 401)

    def test_get_unread_notifications_invalid_token_returns_401(self):
        resp = self.client.get(
            "/api/notifications/unread/",
            HTTP_AUTHORIZATION="Bearer invalid.token",
        )
        self.assertEqual(resp.status_code, 401)

    def test_get_unread_notifications_post_returns_405(self):
        resp = self.client.post("/api/notifications/unread/", **self._auth())
        self.assertEqual(resp.status_code, 405)

    # ── Mark notifications read ───────────────────────────────────────────

    def test_mark_notifications_read_without_ids_marks_all_unread(self):
        n1 = self._create_notification("One")
        n2 = self._create_notification("Two")

        resp = self.client.post(
            "/api/notifications/mark-read/",
            data=json.dumps({}),
            content_type="application/json",
            **self._auth(),
        )

        self.assertEqual(resp.status_code, 200)

        n1.refresh_from_db()
        n2.refresh_from_db()
        self.assertTrue(n1.is_read)
        self.assertTrue(n2.is_read)

    def test_mark_notifications_read_with_ids_marks_only_selected(self):
        n1 = self._create_notification("One")
        n2 = self._create_notification("Two")

        resp = self.client.post(
            "/api/notifications/mark-read/",
            data=json.dumps({"notification_ids": [str(n1.notification_id)]}),
            content_type="application/json",
            **self._auth(),
        )

        self.assertEqual(resp.status_code, 200)

        n1.refresh_from_db()
        n2.refresh_from_db()
        self.assertTrue(n1.is_read)
        self.assertFalse(n2.is_read)

    def test_mark_notifications_read_does_not_mark_other_users_notifications(self):
        other = _make_verified_user(
            email="other@example.com",
            name="Other User",
        )
        other_notification = Notification.objects.create(
            user=other,
            notification_type=Notification.NotificationType.REPORT_READY,
            message="Other user's notification",
            is_read=False,
        )

        self.client.post(
            "/api/notifications/mark-read/",
            data=json.dumps({}),
            content_type="application/json",
            **self._auth(),
        )

        other_notification.refresh_from_db()
        self.assertFalse(other_notification.is_read)

    def test_mark_notifications_read_invalid_json_returns_400(self):
        resp = self.client.post(
            "/api/notifications/mark-read/",
            data="{bad json",
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 400)

    def test_mark_notifications_read_no_token_returns_401(self):
        resp = self.client.post(
            "/api/notifications/mark-read/",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_mark_notifications_read_get_returns_405(self):
        resp = self.client.get("/api/notifications/mark-read/", **self._auth())
        self.assertEqual(resp.status_code, 405)