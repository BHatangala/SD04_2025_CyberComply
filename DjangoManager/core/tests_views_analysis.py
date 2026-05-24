"""
tests_views_analysis.py - Group 4: Analysis + Recommendation View Tests
=======================================================================
Covers:
  POST /api/analysis/save/
  GET /api/analysis/latest/
  GET /api/analysis/history/
  GET /api/analysis/<id>/
  GET /api/analysis/<id>/findings/
  POST /api/recommendations/save/
  GET /api/recommendations/

Run with:
  python manage.py test core.tests_views_analysis --verbosity=2
"""

import json
import uuid
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import signing
from django.test import Client, TestCase
from django.utils import timezone

from core.models import (
    AnalysisResult,
    Document,
    Finding,
    Organization,
    Recommendation,
    UserProfile,
)


VALID_PASSWORD = "Str0ng!Pass99"


AI_RESULT = {
    "summary": "Strengthen retention controls and close policy gaps.",
    "compliance": {
        "compliance_score": 62.4,
        "details": [
            {
                "clause": "Section 4",
                "status": "non_compliant",
                "reasoning": "Retention requirements are missing.",
            },
            {
                "clause": "Section 8",
                "status": "partial",
                "reasoning": "Incident logging exists but is incomplete.",
            },
            {
                "clause": "Section 10",
                "status": "compliant",
                "reasoning": "Encryption controls are present.",
            },
        ],
    },
    "risk_assessment": [
        {
            "title": "Weak data retention controls",
            "description": "Sensitive records may be retained longer than allowed.",
        },
        "Insufficient evidence of monitoring reviews",
    ],
    "recommendations": {
        "top_action": "Formalise retention and review procedures.",
    },
}


def _make_user(email, name, role=UserProfile.Role.GENERAL, org=None, password=VALID_PASSWORD):
    auth_user = User.objects.create_user(username=email, email=email, password=password)
    return UserProfile.objects.create(
        auth_user=auth_user,
        org=org,
        full_name=name,
        role=role,
        is_verified=True,
        otp_is_enabled=False,
    )


def _get_token(profile):
    return signing.dumps({"uid": str(profile.user_id)}, salt="session-token")


def _auth(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _make_document(profile, filename="policy.pdf", org=None, status=Document.Status.UPLOADED):
    return Document.objects.create(
        user=profile,
        org=org or profile.org,
        original_filename=filename,
        file_type="PDF",
        size_bytes=1024,
        s3_key=f"docs/{uuid.uuid4()}.pdf",
        status=status,
    )


def _make_analysis(document, score=80, risk_level=AnalysisResult.RiskLevel.LOW, created_at=None):
    analysis = AnalysisResult.objects.create(
        document=document,
        compliance_score=score,
        risk_level=risk_level,
        summary="Stored summary",
        raw_output=AI_RESULT,
    )
    if created_at is not None:
        AnalysisResult.objects.filter(pk=analysis.pk).update(created_at=created_at)
        analysis.refresh_from_db()
    return analysis


class SaveAnalysisResultViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(org_name="CyberComply Test Org")
        self.owner = _make_user("owner.analysis@gmail.com", "Owner User", org=self.org)
        self.admin = _make_user(
            "admin.analysis@sliit.lk",
            "Org Admin",
            role=UserProfile.Role.ADMIN,
            org=self.org,
        )
        self.other = _make_user("other.analysis@gmail.com", "Other User")
        self.token = _get_token(self.owner)
        self.admin_token = _get_token(self.admin)
        self.other_token = _get_token(self.other)
        self.url = "/api/analysis/save/"
        self.document = _make_document(self.owner, org=self.org)

    def _post(self, payload, token=None):
        tok = token or self.token
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            **_auth(tok),
        )

    def test_save_analysis_valid_payload_returns_201_and_saves_findings(self):
        res = self._post({"document_id": str(self.document.document_id), "result": AI_RESULT})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["compliance_score"], 62)
        self.assertEqual(res.json()["risk_level"], AnalysisResult.RiskLevel.MEDIUM)
        self.assertEqual(res.json()["findings_saved"], 4)

        analysis = AnalysisResult.objects.get(document=self.document)
        self.assertEqual(analysis.summary, AI_RESULT["summary"])
        self.assertEqual(Finding.objects.filter(result=analysis, finding_type=Finding.FindingType.GAP).count(), 2)
        self.assertEqual(Finding.objects.filter(result=analysis, finding_type=Finding.FindingType.RISK).count(), 2)

        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.COMPLETED)

    def test_save_analysis_replaces_existing_analysis_for_document(self):
        old_analysis = _make_analysis(self.document, score=35, risk_level=AnalysisResult.RiskLevel.HIGH)
        Finding.objects.create(
            result=old_analysis,
            finding_type=Finding.FindingType.GAP,
            title="Old gap",
            description="Old description",
        )

        res = self._post({"document_id": str(self.document.document_id), "result": AI_RESULT})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(AnalysisResult.objects.filter(document=self.document).count(), 1)
        self.assertFalse(AnalysisResult.objects.filter(result_id=old_analysis.result_id).exists())

    def test_save_analysis_missing_result_returns_400(self):
        res = self._post({"document_id": str(self.document.document_id)})
        self.assertEqual(res.status_code, 400)

    def test_save_analysis_missing_document_id_returns_400(self):
        res = self._post({"result": AI_RESULT})
        self.assertEqual(res.status_code, 400)

    def test_save_analysis_unknown_document_returns_404(self):
        res = self._post({"document_id": str(uuid.uuid4()), "result": AI_RESULT})
        self.assertEqual(res.status_code, 404)

    def test_save_analysis_other_user_document_returns_403(self):
        res = self._post(
            {"document_id": str(self.document.document_id), "result": AI_RESULT},
            token=self.other_token,
        )
        self.assertEqual(res.status_code, 403)

    def test_save_analysis_same_org_admin_can_save(self):
        res = self._post(
            {"document_id": str(self.document.document_id), "result": AI_RESULT},
            token=self.admin_token,
        )
        self.assertEqual(res.status_code, 201)

    def test_save_analysis_no_token_returns_401(self):
        res = self.client.post(
            self.url,
            data=json.dumps({"document_id": str(self.document.document_id), "result": AI_RESULT}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 401)

    def test_save_analysis_invalid_token_returns_401(self):
        res = self.client.post(
            self.url,
            data=json.dumps({"document_id": str(self.document.document_id), "result": AI_RESULT}),
            content_type="application/json",
            **_auth("not-a-real-token"),
        )
        self.assertEqual(res.status_code, 401)

    def test_save_analysis_get_method_returns_405(self):
        res = self.client.get(self.url, **_auth(self.token))
        self.assertEqual(res.status_code, 405)


class LatestAndHistoryAnalysisViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(org_name="History Org")
        self.owner = _make_user("history.owner@gmail.com", "History Owner", org=self.org)
        self.teammate = _make_user("history.team@gmail.com", "Team Member", org=self.org)
        self.admin = _make_user(
            "history.admin@sliit.lk",
            "History Admin",
            role=UserProfile.Role.ADMIN,
            org=self.org,
        )
        self.outsider = _make_user("history.outsider@gmail.com", "Outside User")
        self.token = _get_token(self.owner)
        self.admin_token = _get_token(self.admin)

        now = timezone.now()
        self.owner_recent = _make_analysis(
            _make_document(self.owner, "owner-recent.pdf", org=self.org),
            score=88,
            risk_level=AnalysisResult.RiskLevel.LOW,
            created_at=now - timedelta(days=2),
        )
        self.owner_older = _make_analysis(
            _make_document(self.owner, "owner-older.pdf", org=self.org),
            score=48,
            risk_level=AnalysisResult.RiskLevel.MEDIUM,
            created_at=now - timedelta(days=10),
        )
        self.team_recent = _make_analysis(
            _make_document(self.teammate, "team-recent.pdf", org=self.org),
            score=30,
            risk_level=AnalysisResult.RiskLevel.HIGH,
            created_at=now - timedelta(days=3),
        )
        self.outside_recent = _make_analysis(
            _make_document(self.outsider, "outside.pdf"),
            score=75,
            risk_level=AnalysisResult.RiskLevel.LOW,
            created_at=now - timedelta(days=1),
        )

    def test_get_latest_analysis_returns_most_recent_owner_result(self):
        res = self.client.get("/api/analysis/latest/", **_auth(self.token))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["result_id"], str(self.owner_recent.result_id))
        self.assertEqual(res.json()["original_filename"], "owner-recent.pdf")

    def test_get_latest_analysis_without_results_returns_404(self):
        fresh = _make_user("fresh.analysis@gmail.com", "Fresh User")
        fresh_token = _get_token(fresh)
        res = self.client.get("/api/analysis/latest/", **_auth(fresh_token))
        self.assertEqual(res.status_code, 404)

    def test_get_latest_analysis_no_token_returns_401(self):
        res = self.client.get("/api/analysis/latest/")
        self.assertEqual(res.status_code, 401)

    def test_get_latest_analysis_post_method_returns_405(self):
        res = self.client.post("/api/analysis/latest/", **_auth(self.token))
        self.assertEqual(res.status_code, 405)

    def test_get_analysis_history_general_user_only_sees_own_results(self):
        res = self.client.get("/api/analysis/history/", **_auth(self.token))
        self.assertEqual(res.status_code, 200)

        data = res.json()
        self.assertEqual(len(data["last_7_days"]), 1)
        self.assertEqual(data["last_7_days"][0]["result_id"], str(self.owner_recent.result_id))
        self.assertEqual(len(data["last_30_days"]), 1)
        self.assertEqual(data["last_30_days"][0]["result_id"], str(self.owner_older.result_id))

    def test_get_analysis_history_admin_sees_same_org_results(self):
        res = self.client.get("/api/analysis/history/", **_auth(self.admin_token))
        self.assertEqual(res.status_code, 200)

        ids_last_7 = {item["result_id"] for item in res.json()["last_7_days"]}
        self.assertIn(str(self.owner_recent.result_id), ids_last_7)
        self.assertIn(str(self.team_recent.result_id), ids_last_7)
        self.assertNotIn(str(self.outside_recent.result_id), ids_last_7)

    def test_get_analysis_history_invalid_token_returns_401(self):
        res = self.client.get("/api/analysis/history/", **_auth("broken-token"))
        self.assertEqual(res.status_code, 401)

    def test_get_analysis_history_post_method_returns_405(self):
        res = self.client.post("/api/analysis/history/", **_auth(self.token))
        self.assertEqual(res.status_code, 405)


class AnalysisDetailAndFindingsViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(org_name="Detail Org")
        self.owner = _make_user("detail.owner@gmail.com", "Detail Owner", org=self.org)
        self.admin = _make_user(
            "detail.admin@sliit.lk",
            "Detail Admin",
            role=UserProfile.Role.ADMIN,
            org=self.org,
        )
        self.other = _make_user("detail.other@gmail.com", "Detail Other")
        self.token = _get_token(self.owner)
        self.admin_token = _get_token(self.admin)
        self.other_token = _get_token(self.other)

        self.analysis = _make_analysis(_make_document(self.owner, "detail.pdf", org=self.org))
        Finding.objects.create(
            result=self.analysis,
            finding_type=Finding.FindingType.GAP,
            title="Gap one",
            description="Missing procedure",
        )
        Finding.objects.create(
            result=self.analysis,
            finding_type=Finding.FindingType.RISK,
            title="Risk one",
            description="Possible data exposure",
        )

    def test_get_analysis_by_id_owner_returns_200(self):
        res = self.client.get(f"/api/analysis/{self.analysis.result_id}/", **_auth(self.token))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["result_id"], str(self.analysis.result_id))

    def test_get_analysis_by_id_other_user_returns_403(self):
        res = self.client.get(f"/api/analysis/{self.analysis.result_id}/", **_auth(self.other_token))
        self.assertEqual(res.status_code, 403)

    def test_get_analysis_by_id_same_org_admin_returns_200(self):
        res = self.client.get(f"/api/analysis/{self.analysis.result_id}/", **_auth(self.admin_token))
        self.assertEqual(res.status_code, 200)

    def test_get_analysis_by_id_unknown_result_returns_404(self):
        res = self.client.get(f"/api/analysis/{uuid.uuid4()}/", **_auth(self.token))
        self.assertEqual(res.status_code, 404)

    def test_get_findings_for_result_returns_counts_and_items(self):
        res = self.client.get(
            f"/api/analysis/{self.analysis.result_id}/findings/",
            **_auth(self.token),
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["gap_count"], 1)
        self.assertEqual(data["risk_count"], 1)

    def test_get_findings_for_result_other_user_returns_403(self):
        res = self.client.get(
            f"/api/analysis/{self.analysis.result_id}/findings/",
            **_auth(self.other_token),
        )
        self.assertEqual(res.status_code, 403)

    def test_get_findings_for_result_unknown_result_returns_404(self):
        res = self.client.get(f"/api/analysis/{uuid.uuid4()}/findings/", **_auth(self.token))
        self.assertEqual(res.status_code, 404)


class RecommendationViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.org = Organization.objects.create(org_name="Recommendation Org")
        self.owner = _make_user("rec.owner@gmail.com", "Rec Owner", org=self.org)
        self.admin = _make_user(
            "rec.admin@sliit.lk",
            "Rec Admin",
            role=UserProfile.Role.ADMIN,
            org=self.org,
        )
        self.other = _make_user("rec.other@gmail.com", "Rec Other")
        self.token = _get_token(self.owner)
        self.admin_token = _get_token(self.admin)
        self.other_token = _get_token(self.other)
        self.analysis = _make_analysis(_make_document(self.owner, "recommendations.pdf", org=self.org))
        self.save_url = "/api/recommendations/save/"
        self.list_url = f"/api/recommendations/?result_id={self.analysis.result_id}"

    def _save_payload(self):
        return {
            "result_id": str(self.analysis.result_id),
            "recommendations": [
                {
                    "recommendation_text": "Create a retention register.",
                    "status": Recommendation.Status.HIGH,
                    "act_name": "Data Protection Act",
                    "steps_to_achieve": ["Identify retention owners", "Publish register"],
                    "section": "Section 4",
                },
                {
                    "recommendation_text": "Review monitoring exceptions.",
                    "status": "NOT_A_REAL_STATUS",
                    "act_name": "Cybersecurity Act",
                    "steps_to_achieve": "not-a-list",
                    "section": "Section 8",
                },
            ],
        }

    def test_save_recommendations_valid_payload_returns_201(self):
        res = self.client.post(
            self.save_url,
            data=json.dumps(self._save_payload()),
            content_type="application/json",
            **_auth(self.token),
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Recommendation.objects.filter(result=self.analysis).count(), 2)

        fallback_rec = Recommendation.objects.get(act_name="Cybersecurity Act")
        self.assertEqual(fallback_rec.status, Recommendation.Status.MEDIUM)
        self.assertEqual(fallback_rec.steps_to_achieve, [])

    def test_save_recommendations_missing_result_id_returns_400(self):
        payload = self._save_payload()
        payload.pop("result_id")
        res = self.client.post(
            self.save_url,
            data=json.dumps(payload),
            content_type="application/json",
            **_auth(self.token),
        )
        self.assertEqual(res.status_code, 400)

    def test_save_recommendations_empty_list_returns_400(self):
        res = self.client.post(
            self.save_url,
            data=json.dumps({"result_id": str(self.analysis.result_id), "recommendations": []}),
            content_type="application/json",
            **_auth(self.token),
        )
        self.assertEqual(res.status_code, 400)

    def test_save_recommendations_invalid_result_id_returns_400(self):
        res = self.client.post(
            self.save_url,
            data=json.dumps({"result_id": "bad-uuid", "recommendations": [{}]}),
            content_type="application/json",
            **_auth(self.token),
        )
        self.assertEqual(res.status_code, 400)

    def test_save_recommendations_unknown_analysis_returns_404(self):
        payload = self._save_payload()
        payload["result_id"] = str(uuid.uuid4())
        res = self.client.post(
            self.save_url,
            data=json.dumps(payload),
            content_type="application/json",
            **_auth(self.token),
        )
        self.assertEqual(res.status_code, 404)

    def test_save_recommendations_no_token_returns_401(self):
        res = self.client.post(
            self.save_url,
            data=json.dumps(self._save_payload()),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 401)

    def test_save_recommendations_get_method_returns_405(self):
        res = self.client.get(self.save_url, **_auth(self.token))
        self.assertEqual(res.status_code, 405)

    def test_get_recommendations_owner_returns_200(self):
        Recommendation.objects.create(
            result=self.analysis,
            recommendation_text="Create a retention register.",
            status=Recommendation.Status.HIGH,
            act_name="Data Protection Act",
            steps_to_achieve=["Step one"],
            section="Section 4",
        )

        res = self.client.get(self.list_url, **_auth(self.token))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["recommendations"]), 1)

    def test_get_recommendations_same_org_admin_returns_200(self):
        Recommendation.objects.create(
            result=self.analysis,
            recommendation_text="Create a retention register.",
            status=Recommendation.Status.HIGH,
            act_name="Data Protection Act",
            steps_to_achieve=["Step one"],
            section="Section 4",
        )

        res = self.client.get(self.list_url, **_auth(self.admin_token))
        self.assertEqual(res.status_code, 200)

    def test_get_recommendations_other_user_returns_403(self):
        res = self.client.get(self.list_url, **_auth(self.other_token))
        self.assertEqual(res.status_code, 403)

    def test_get_recommendations_missing_result_id_returns_400(self):
        res = self.client.get("/api/recommendations/", **_auth(self.token))
        self.assertEqual(res.status_code, 400)

    def test_get_recommendations_unknown_result_returns_404(self):
        res = self.client.get(f"/api/recommendations/?result_id={uuid.uuid4()}", **_auth(self.token))
        self.assertEqual(res.status_code, 404)

    def test_get_recommendations_invalid_token_returns_401(self):
        res = self.client.get(self.list_url, **_auth("broken-token"))
        self.assertEqual(res.status_code, 401)

    def test_get_recommendations_post_method_returns_405(self):
        res = self.client.post(self.list_url, **_auth(self.token))
        self.assertEqual(res.status_code, 405)
