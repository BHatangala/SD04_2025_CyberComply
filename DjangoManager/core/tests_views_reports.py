import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone

from core.models import (
    UserProfile,
    Organization,
    Document,
    AnalysisResult,
    Report,
    ReportDownload,
    Notification,
)


# ─────────────────────────────────────────────────────────────────────────────
# Shared constants
# ─────────────────────────────────────────────────────────────────────────────

VALID_PASSWORD = "Str0ng!Pass99"
GENERAL_EMAIL  = "general.report@gmail.com"
ADMIN_EMAIL    = "admin.report@sliit.lk"
OTHER_EMAIL    = "other.user@gmail.com"

SNAPSHOT = {
    "metadata":   {"company": "TestCorp", "file_analyzed": "policy.pdf"},
    "compliance": {"compliance_score": 80, "details": []},
    "risks":      {"status": "low", "factors": []},
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(email, name, role, password=VALID_PASSWORD):
    auth_user = User.objects.create_user(username=email, email=email, password=password)
    profile = UserProfile.objects.create(
        auth_user=auth_user,
        full_name=name,
        role=role,
        is_verified=True,
        otp_is_enabled=False,
    )
    return profile


def _make_org():
    return Organization.objects.create(org_name="TestOrg")


def _make_document(profile, org=None):
    return Document.objects.create(
        user=profile,
        org=org,
        original_filename="policy.pdf",
        s3_key=f"docs/{uuid.uuid4()}.pdf",
        size_bytes=1024,
        file_type="PDF",
    )


def _make_analysis(document):
    return AnalysisResult.objects.create(
        document=document,
        compliance_score=80,
        risk_level=AnalysisResult.RiskLevel.LOW,
        raw_output=SNAPSHOT,
    )


def _make_report(analysis):
    return Report.objects.create(
        result=analysis,
        report_snapshot=SNAPSHOT,
        report_s3_key="reports/policy.pdf",
        file_size=2048,
        expires_at=timezone.now() + timedelta(days=30),
        view_token=str(uuid.uuid4()).replace("-", ""),
    )


def _get_token(client, email, password=VALID_PASSWORD):
    res = client.post(
        "/api/session-token/",
        data=json.dumps({"email": email, "password": password}),
        content_type="application/json",
    )
    return res.json().get("token", "")


def _auth(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# 1. GENERATE REPORT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class GenerateReportViewTest(TestCase):
    """Tests for POST /api/reports/generate/"""

    def setUp(self):
        self.client  = Client()
        self.url     = "/api/reports/generate/"
        self.profile = _make_user(GENERAL_EMAIL, "General User", UserProfile.Role.GENERAL)
        self.doc     = _make_document(self.profile)
        self.analysis = _make_analysis(self.doc)
        self.token   = _get_token(self.client, GENERAL_EMAIL)

    def _post(self, payload, token=None):
        tok = token or self.token
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            **_auth(tok),
        )

    @patch("core.views._send_report_notification")
    def test_generate_report_returns_201(self, mock_notify):
        res = self._post({
            "result_id":       str(self.analysis.result_id),
            "report_snapshot": SNAPSHOT,
            "report_s3_key":   "reports/policy.pdf",
            "file_size":       2048,
        })
        self.assertEqual(res.status_code, 201)

    @patch("core.views._send_report_notification")
    def test_generate_report_returns_report_id(self, mock_notify):
        res = self._post({
            "result_id":       str(self.analysis.result_id),
            "report_snapshot": SNAPSHOT,
            "report_s3_key":   "reports/policy.pdf",
            "file_size":       2048,
        })
        self.assertIn("report_id", res.json())

    @patch("core.views._send_report_notification")
    def test_generate_report_creates_db_row(self, mock_notify):
        self._post({
            "result_id":       str(self.analysis.result_id),
            "report_snapshot": SNAPSHOT,
            "report_s3_key":   "reports/policy.pdf",
            "file_size":       2048,
        })
        self.assertEqual(Report.objects.count(), 1)

    def test_generate_report_missing_result_id_returns_400(self):
        res = self._post({
            "report_snapshot": SNAPSHOT,
            "report_s3_key":   "reports/policy.pdf",
            "file_size":       2048,
        })
        self.assertEqual(res.status_code, 400)

    def test_generate_report_missing_snapshot_returns_400(self):
        res = self._post({
            "result_id":     str(self.analysis.result_id),
            "report_s3_key": "reports/policy.pdf",
            "file_size":     2048,
        })
        self.assertEqual(res.status_code, 400)

    def test_generate_report_missing_file_size_returns_400(self):
        res = self._post({
            "result_id":       str(self.analysis.result_id),
            "report_snapshot": SNAPSHOT,
            "report_s3_key":   "reports/policy.pdf",
        })
        self.assertEqual(res.status_code, 400)

    def test_generate_report_invalid_result_id_returns_404(self):
        res = self._post({
            "result_id":       str(uuid.uuid4()),
            "report_snapshot": SNAPSHOT,
            "report_s3_key":   "reports/policy.pdf",
            "file_size":       2048,
        })
        self.assertEqual(res.status_code, 404)

    def test_generate_report_no_token_returns_401(self):
        res = self.client.post(
            self.url,
            data=json.dumps({
                "result_id":       str(self.analysis.result_id),
                "report_snapshot": SNAPSHOT,
                "report_s3_key":   "reports/policy.pdf",
                "file_size":       2048,
            }),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 401)

    def test_generate_report_get_method_returns_405(self):
        res = self.client.get(self.url, **_auth(self.token))
        self.assertEqual(res.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 2. GET REPORT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class GetReportViewTest(TestCase):
    """Tests for GET /api/reports/<report_id>/"""

    def setUp(self):
        self.client   = Client()
        self.profile  = _make_user(GENERAL_EMAIL, "General User", UserProfile.Role.GENERAL)
        self.doc      = _make_document(self.profile)
        self.analysis = _make_analysis(self.doc)
        self.report   = _make_report(self.analysis)
        self.token    = _get_token(self.client, GENERAL_EMAIL)

    def _get(self, report_id, token=None):
        tok = token or self.token
        return self.client.get(
            f"/api/reports/{report_id}/",
            **_auth(tok),
        )

    def test_get_report_owner_returns_200(self):
        res = self._get(self.report.report_id)
        self.assertEqual(res.status_code, 200)

    def test_get_report_returns_snapshot(self):
        res = self._get(self.report.report_id)
        self.assertIn("report_snapshot", res.json())

    def test_get_report_returns_result_id(self):
        res = self._get(self.report.report_id)
        self.assertEqual(res.json()["result_id"], str(self.analysis.result_id))

    def test_get_report_not_found_returns_404(self):
        res = self._get(uuid.uuid4())
        self.assertEqual(res.status_code, 404)

    def test_get_report_no_token_returns_401(self):
        res = self.client.get(f"/api/reports/{self.report.report_id}/")
        self.assertEqual(res.status_code, 401)

    def test_get_report_other_user_returns_403(self):
        other = _make_user(OTHER_EMAIL, "Other User", UserProfile.Role.GENERAL)
        other_token = _get_token(self.client, OTHER_EMAIL)
        res = self._get(self.report.report_id, token=other_token)
        self.assertEqual(res.status_code, 403)

    def test_get_report_post_method_returns_405(self):
        res = self.client.post(
            f"/api/reports/{self.report.report_id}/",
            **_auth(self.token),
        )
        self.assertEqual(res.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 3. DOWNLOAD REPORT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class DownloadReportViewTest(TestCase):
    """Tests for POST /api/download-report/"""

    def setUp(self):
        self.client      = Client()
        self.url         = "/api/download-report/"
        self.org         = _make_org()
        self.admin       = _make_user(ADMIN_EMAIL, "Admin User", UserProfile.Role.ADMIN)
        self.admin.org   = self.org
        self.admin.save()
        self.doc         = _make_document(self.admin, org=self.org)
        self.analysis    = _make_analysis(self.doc)
        self.report      = _make_report(self.analysis)
        self.admin_token = _get_token(self.client, ADMIN_EMAIL)

        self.general      = _make_user(GENERAL_EMAIL, "General User", UserProfile.Role.GENERAL)
        self.general_token = _get_token(self.client, GENERAL_EMAIL)

    def _post(self, payload, token=None):
        tok = token or self.admin_token
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            **_auth(tok),
        )

    def test_admin_download_returns_200(self):
        res = self._post({"report_id": str(self.report.report_id)})
        self.assertEqual(res.status_code, 200)

    def test_admin_download_creates_download_record(self):
        self._post({"report_id": str(self.report.report_id)})
        self.assertEqual(ReportDownload.objects.count(), 1)

    def test_general_user_download_returns_403(self):
        res = self._post({"report_id": str(self.report.report_id)}, token=self.general_token)
        self.assertEqual(res.status_code, 403)

    def test_download_missing_report_id_returns_400(self):
        res = self._post({})
        self.assertEqual(res.status_code, 400)

    def test_download_nonexistent_report_returns_404(self):
        res = self._post({"report_id": str(uuid.uuid4())})
        self.assertEqual(res.status_code, 404)

    def test_download_no_token_returns_401(self):
        res = self.client.post(
            self.url,
            data=json.dumps({"report_id": str(self.report.report_id)}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 401)

    def test_download_get_method_returns_405(self):
        res = self.client.get(self.url, **_auth(self.admin_token))
        self.assertEqual(res.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 4. NOTIFICATIONS TESTS
# ─────────────────────────────────────────────────────────────────────────────

class GetUnreadNotificationsTest(TestCase):
    """Tests for GET /api/notifications/unread/"""

    def setUp(self):
        self.client  = Client()
        self.url     = "/api/notifications/unread/"
        self.profile = _make_user(GENERAL_EMAIL, "General User", UserProfile.Role.GENERAL)
        self.token   = _get_token(self.client, GENERAL_EMAIL)

        self.doc      = _make_document(self.profile)
        self.analysis = _make_analysis(self.doc)
        self.report   = _make_report(self.analysis)

    def _get(self, token=None):
        tok = token or self.token
        return self.client.get(self.url, **_auth(tok))

    def test_no_notifications_returns_empty_list(self):
        res = self._get()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["unread_count"], 0)
        self.assertEqual(res.json()["notifications"], [])

    def test_unread_notification_appears_in_response(self):
        Notification.objects.create(
            user=self.profile,
            notification_type=Notification.NotificationType.REPORT_READY,
            message="Your report is ready.",
            report=self.report,
        )
        res = self._get()
        self.assertEqual(res.json()["unread_count"], 1)
        self.assertEqual(len(res.json()["notifications"]), 1)

    def test_read_notification_not_returned(self):
        Notification.objects.create(
            user=self.profile,
            notification_type=Notification.NotificationType.REPORT_READY,
            message="Your report is ready.",
            report=self.report,
            is_read=True,
        )
        res = self._get()
        self.assertEqual(res.json()["unread_count"], 0)

    def test_notification_contains_expected_fields(self):
        Notification.objects.create(
            user=self.profile,
            notification_type=Notification.NotificationType.REPORT_READY,
            message="Your report is ready.",
            report=self.report,
        )
        res = self._get()
        notif = res.json()["notifications"][0]
        self.assertIn("notification_id", notif)
        self.assertIn("type", notif)
        self.assertIn("message", notif)
        self.assertIn("created_at", notif)

    def test_no_token_returns_401(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 401)

    def test_other_users_notifications_not_returned(self):
        other_profile  = _make_user(OTHER_EMAIL, "Other User", UserProfile.Role.GENERAL)
        other_doc      = _make_document(other_profile)
        other_analysis = _make_analysis(other_doc)
        other_report   = _make_report(other_analysis)
        Notification.objects.create(
            user=other_profile,
            notification_type=Notification.NotificationType.REPORT_READY,
            message="Other user's report is ready.",
            report=other_report,
        )
        res = self._get()
        self.assertEqual(res.json()["unread_count"], 0)


class MarkNotificationsReadTest(TestCase):
    """Tests for POST /api/notifications/mark-read/"""

    def setUp(self):
        self.client  = Client()
        self.url     = "/api/notifications/mark-read/"
        self.profile = _make_user(GENERAL_EMAIL, "General User", UserProfile.Role.GENERAL)
        self.token   = _get_token(self.client, GENERAL_EMAIL)

        self.doc      = _make_document(self.profile)
        self.analysis = _make_analysis(self.doc)
        self.report   = _make_report(self.analysis)

    def _make_notification(self):
        return Notification.objects.create(
            user=self.profile,
            notification_type=Notification.NotificationType.REPORT_READY,
            message="Your report is ready.",
            report=self.report,
        )

    def _post(self, payload=None, token=None):
        tok = token or self.token
        return self.client.post(
            self.url,
            data=json.dumps(payload or {}),
            content_type="application/json",
            **_auth(tok),
        )

    def test_mark_all_read_returns_200(self):
        self._make_notification()
        res = self._post()
        self.assertEqual(res.status_code, 200)

    def test_mark_all_read_updates_all_notifications(self):
        self._make_notification()
        self._make_notification()
        self._post()
        unread = Notification.objects.filter(user=self.profile, is_read=False).count()
        self.assertEqual(unread, 0)

    def test_mark_specific_notification_read(self):
        n1 = self._make_notification()
        n2 = self._make_notification()
        self._post({"notification_ids": [str(n1.notification_id)]})
        self.assertTrue(Notification.objects.get(notification_id=n1.notification_id).is_read)
        self.assertFalse(Notification.objects.get(notification_id=n2.notification_id).is_read)

    def test_mark_read_response_contains_count(self):
        self._make_notification()
        self._make_notification()
        res = self._post()
        self.assertIn("2 notification(s) marked as read", res.json()["detail"])

    def test_mark_read_no_token_returns_401(self):
        res = self.client.post(self.url, data=json.dumps({}), content_type="application/json")
        self.assertEqual(res.status_code, 401)

    def test_mark_read_empty_body_marks_all(self):
        self._make_notification()
        res = self._post({})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Notification.objects.filter(is_read=False).count(), 0)
