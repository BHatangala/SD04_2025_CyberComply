"""
tests_integration.py — Group 7: End-to-End Backend Integration Tests
===================================================================
Covers:
  1. signup → login → OTP verify → session token → upload → analyse → generate report
  2. general user → request admin access → verify admin OTP → role becomes ADMIN

Run with:
  python manage.py test core.tests_integration --verbosity=2
"""

import json
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import (
    UserProfile,
    Document,
    AnalysisResult,
    Report,
)


VALID_PASSWORD = "Str0ng!Pass99"
USER_EMAIL = "integration.user@gmail.com"
USER_NAME = "Integration User"
ORG_EMAIL = "integration.user@sliit.lk"


AI_RESULT = {
    "summary": "The uploaded policy document was analysed successfully.",
    "metadata": {
        "file_analyzed": "policy.txt",
        "company": "CyberComply",
    },
    "compliance": {
        "compliance_score": 82,
        "details": [
            {
                "clause": "Consent Management",
                "status": "compliant",
                "reasoning": "Consent handling is clearly defined.",
                "risk_level": "low",
            },
            {
                "clause": "Retention Policy",
                "status": "partial",
                "reasoning": "Retention period requires more detail.",
                "risk_level": "medium",
            },
        ],
    },
    "risk_assessment": [
        {
            "title": "Retention ambiguity",
            "description": "The policy should define retention timelines more clearly.",
        }
    ],
    "recommendations": {
        "top_action": "Clarify retention timelines.",
    },
}


class CyberComplyIntegrationTest(TestCase):
    def setUp(self):
        self.client = Client()

    def _post_json(self, url, payload, token=None):
        headers = {}
        if token:
            headers["HTTP_AUTHORIZATION"] = f"Bearer {token}"

        return self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def _get_json(self, url, token=None):
        headers = {}
        if token:
            headers["HTTP_AUTHORIZATION"] = f"Bearer {token}"

        return self.client.get(url, **headers)

    def _get_token(self, email):
        resp = self._post_json("/api/session-token/", {"email": email})
        self.assertEqual(resp.status_code, 200)
        return json.loads(resp.content)["token"]

    def _signup_and_verify_user(self, email=USER_EMAIL):
        signup_resp = self._post_json("/api/signup/", {
            "name": USER_NAME,
            "email": email,
            "password": VALID_PASSWORD,
            "role": "General user",
        })
        self.assertEqual(signup_resp.status_code, 201)

        with patch("core.views.random.randint", return_value=654321), \
             patch("core.views.send_otp_email", return_value=True):
            login_resp = self._post_json("/api/login/", {
                "email": email,
                "password": VALID_PASSWORD,
            })

        self.assertEqual(login_resp.status_code, 200)
        self.assertTrue(json.loads(login_resp.content).get("requires_otp"))

        otp_resp = self._post_json("/api/verify-otp/", {
            "email": email,
            "otp": "654321",
        })
        self.assertEqual(otp_resp.status_code, 200)

        profile = UserProfile.objects.get(auth_user__username=email)
        self.assertTrue(profile.is_verified)

        token = self._get_token(email)
        return profile, token

    # ─────────────────────────────────────────────────────────────────────
    # 1. Full compliance flow
    # signup → login → OTP verify → token → upload → analyse → report
    # ─────────────────────────────────────────────────────────────────────

    def test_full_signup_login_upload_analyse_generate_report_flow(self):
        profile, token = self._signup_and_verify_user()

        uploaded_file = SimpleUploadedFile(
            "policy.txt",
            b"This is a sample compliance policy document.",
            content_type="text/plain",
        )

        with patch("core.views.is_password_protected", return_value=False), \
             patch("core.views.scan_file", return_value=None), \
             patch("core.views.upload_to_s3", return_value=("policy.txt", "https://s3.example.com/policy.txt")), \
             patch("core.views.push_upload_metric"):
            upload_resp = self.client.post(
                "/upload/",
                data={"document": uploaded_file},
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )

        self.assertEqual(upload_resp.status_code, 200)

        upload_data = json.loads(upload_resp.content)
        self.assertEqual(upload_data["status"], "uploaded")
        self.assertIn("document_id", upload_data)

        document = Document.objects.get(document_id=upload_data["document_id"])
        self.assertEqual(document.user, profile)
        self.assertEqual(document.status, Document.Status.UPLOADED)

        mock_submit_response = MagicMock()
        mock_submit_response.status_code = 200
        mock_submit_response.json.return_value = {"job_id": "job-123"}
        mock_submit_response.raise_for_status.return_value = None

        mock_status_response = MagicMock()
        mock_status_response.json.return_value = {
            "status": "success",
            "result": AI_RESULT,
        }

        with patch("core.views.requests.post", return_value=mock_submit_response), \
             patch("core.views.requests.get", return_value=mock_status_response), \
             patch("core.views._time.sleep", return_value=None), \
             patch("core.views.push_ai_metric"):
            analyse_resp = self.client.post(
                "/analyze/",
                data={
                    "file_name": "policy.txt",
                    "company_name": "CyberComply",
                    "department": "Compliance",
                },
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )

            self.assertEqual(analyse_resp.status_code, 200)
            stream_output = b"".join(analyse_resp.streaming_content).decode("utf-8")

        self.assertIn('"status": "analysed"', stream_output)

        analysis = AnalysisResult.objects.get(document=document)
        self.assertEqual(analysis.compliance_score, 82)
        self.assertEqual(analysis.risk_level, AnalysisResult.RiskLevel.LOW)

        with patch("core.views._send_report_notification"):
            report_resp = self._post_json(
                "/api/reports/generate/",
                {
                    "result_id": str(analysis.result_id),
                    "report_snapshot": AI_RESULT,
                    "report_s3_key": "reports/policy-report.pdf",
                    "file_size": 2048,
                    "expires_in_days": 30,
                },
                token=token,
            )

        self.assertEqual(report_resp.status_code, 201)

        report_data = json.loads(report_resp.content)
        self.assertIn("report_id", report_data)
        self.assertIn("view_token", report_data)

        report = Report.objects.get(report_id=report_data["report_id"])
        self.assertEqual(report.result, analysis)

        get_report_resp = self._get_json(
            f"/api/reports/{report.report_id}/",
            token=token,
        )
        self.assertEqual(get_report_resp.status_code, 200)

    # ─────────────────────────────────────────────────────────────────────
    # 2. Admin upgrade flow
    # general user → request admin access → verify OTP → role becomes ADMIN
    # ─────────────────────────────────────────────────────────────────────

    def test_admin_upgrade_flow_grants_admin_role(self):
        profile, token = self._signup_and_verify_user(email="admin.flow@gmail.com")

        with patch("core.views.random.randint", return_value=123456), \
             patch("core.views.send_otp_email", return_value=True):
            request_resp = self._post_json(
                "/api/admin-access/request/",
                {"org_email": ORG_EMAIL},
                token=token,
            )

        self.assertEqual(request_resp.status_code, 201)

        request_data = json.loads(request_resp.content)
        self.assertIn("request_id", request_data)

        verify_resp = self._post_json(
            "/api/admin-access/verify/",
            {
                "request_id": request_data["request_id"],
                "otp": "123456",
            },
            token=token,
        )

        self.assertEqual(verify_resp.status_code, 200)

        profile.refresh_from_db()
        profile.auth_user.refresh_from_db()

        self.assertEqual(profile.role, UserProfile.Role.ADMIN)
        self.assertEqual(profile.auth_user.email, ORG_EMAIL)
        self.assertEqual(profile.auth_user.username, ORG_EMAIL)

        status_resp = self._get_json(
            "/api/admin-access/status/",
            token=token,
        )

        self.assertEqual(status_resp.status_code, 200)

        status_data = json.loads(status_resp.content)
        self.assertEqual(status_data["status"], "APPROVED")