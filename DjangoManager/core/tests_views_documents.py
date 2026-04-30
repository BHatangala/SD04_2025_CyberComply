"""
tests_views_documents.py — Group 3: Document View Tests
========================================================
Covers:
  POST /upload/
  POST /analyze/
  POST /analyze-batch/
  POST /upload-from-drive/
  POST /upload-from-onedrive/
  POST /api/delete-file/

Run with:
  python manage.py test core.tests_views_documents --verbosity=2

Key facts from reading the actual views.py:
  - upload_file:          file field is 'document' (not 'file')
                          also calls is_password_protected and push_upload_metric
  - analyze_compliance:   uses POST form field 'file_name', not JSON document_id
                          fetches bytes from Django cache; returns SSE stream
  - analyze_batch:        uses JSON body with 'files' list (each has 'file_name')
                          not document_ids; auth checked first
  - upload_from_drive:    requires file_id + access_token + file_name (3 required)
                          uses requests.get to download from Drive
  - upload_from_onedrive: same 3 required fields; additionally calls save_oauth_token
  - delete_file:          calls boto3.client('s3').delete_objects directly (not _delete_s3_keys)
                          filters docs by user=profile for non-admins; no 403 is raised —
                          other user's docs are silently excluded and 200 is returned
"""

import json
import uuid
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import UserProfile, Document


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

PASSWORD    = "Str0ng!Pass99"
EMAIL       = "docuser@test.com"
OTHER_EMAIL = "other@test.com"
NAME        = "Doc User"
OTHER_NAME  = "Other User"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_verified_user(email=EMAIL, name=NAME,
                        role=UserProfile.Role.GENERAL, password=PASSWORD):
    """
    Creates a verified UserProfile directly in the DB.
    Bypasses signup/OTP flow — use for any test that just needs an auth'd user.
    """
    auth_user = User.objects.create_user(
        username=email, email=email, password=password
    )
    return UserProfile.objects.create(
        auth_user=auth_user,
        full_name=name,
        role=role,
        is_verified=True,
        otp_is_enabled=False,
    )


def _get_token(client, email=EMAIL):
    """Obtains a real signed Bearer token via the session-token endpoint."""
    resp = client.post(
        "/api/session-token/",
        data=json.dumps({"email": email}),
        content_type="application/json",
    )
    return json.loads(resp.content)["token"]


def _pdf(name="test.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 fake", content_type="application/pdf")


def _docx(name="test.docx"):
    return SimpleUploadedFile(
        name, b"PK fake docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def _txt(name="test.txt"):
    return SimpleUploadedFile(name, b"plain text content", content_type="text/plain")


def _exe(name="bad.exe"):
    return SimpleUploadedFile(name, b"MZ fake", content_type="application/octet-stream")


# ─────────────────────────────────────────────────────────────────────────────
# 1. UPLOAD VIEW TESTS  —  POST /upload/
# ─────────────────────────────────────────────────────────────────────────────

class UploadViewTest(TestCase):
    """
    Tests for POST /upload/

    Critical implementation details:
      - File must be sent as request.FILES['document'] (NOT 'file')
      - Auth checked first: missing/invalid token → 401
      - is_password_protected() called before scan_file()
      - scan_file() → non-None means threat → 400
      - upload_to_s3() called for clean files
      - Document record created on success; response contains 'document_id'
    """

    def setUp(self):
        self.client  = Client()
        self.url     = "/upload/"
        self.profile = _make_verified_user()
        self.token   = _get_token(self.client)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    # ── Happy path ─────────────────────────────────────────────────────────

    @patch("core.views.upload_to_s3", return_value=("docs/test.pdf", "https://s3.example.com/test.pdf"))
    @patch("core.views.scan_file", return_value=None)
    @patch("core.views.push_upload_metric")
    @patch("core.views.is_password_protected", return_value=False)
    def test_upload_valid_pdf_returns_200(self, _pp, _metric, _scan, _s3):
        resp = self.client.post(self.url, {"document": _pdf()}, **self._auth())
        self.assertEqual(resp.status_code, 200)

    @patch("core.views.upload_to_s3", return_value=("docs/test.docx", "https://s3.example.com/test.docx"))
    @patch("core.views.scan_file", return_value=None)
    @patch("core.views.push_upload_metric")
    @patch("core.views.is_password_protected", return_value=False)
    def test_upload_valid_docx_returns_200(self, _pp, _metric, _scan, _s3):
        resp = self.client.post(self.url, {"document": _docx()}, **self._auth())
        self.assertEqual(resp.status_code, 200)

    @patch("core.views.upload_to_s3", return_value=("docs/test.txt", "https://s3.example.com/test.txt"))
    @patch("core.views.scan_file", return_value=None)
    @patch("core.views.push_upload_metric")
    @patch("core.views.is_password_protected", return_value=False)
    def test_upload_valid_txt_returns_200(self, _pp, _metric, _scan, _s3):
        resp = self.client.post(self.url, {"document": _txt()}, **self._auth())
        self.assertEqual(resp.status_code, 200)

    @patch("core.views.upload_to_s3", return_value=("docs/test.pdf", "https://s3.example.com/test.pdf"))
    @patch("core.views.scan_file", return_value=None)
    @patch("core.views.push_upload_metric")
    @patch("core.views.is_password_protected", return_value=False)
    def test_upload_creates_document_record(self, _pp, _metric, _scan, _s3):
        self.client.post(self.url, {"document": _pdf()}, **self._auth())
        self.assertTrue(Document.objects.filter(user=self.profile).exists())

    @patch("core.views.upload_to_s3", return_value=("docs/test.pdf", "https://s3.example.com/test.pdf"))
    @patch("core.views.scan_file", return_value=None)
    @patch("core.views.push_upload_metric")
    @patch("core.views.is_password_protected", return_value=False)
    def test_upload_document_status_is_uploaded(self, _pp, _metric, _scan, _s3):
        self.client.post(self.url, {"document": _pdf()}, **self._auth())
        doc = Document.objects.filter(user=self.profile).first()
        self.assertIsNotNone(doc)
        self.assertEqual(doc.status, Document.Status.UPLOADED)

    @patch("core.views.upload_to_s3", return_value=("docs/test.pdf", "https://s3.example.com/test.pdf"))
    @patch("core.views.scan_file", return_value=None)
    @patch("core.views.push_upload_metric")
    @patch("core.views.is_password_protected", return_value=False)
    def test_upload_response_contains_document_id(self, _pp, _metric, _scan, _s3):
        resp = self.client.post(self.url, {"document": _pdf()}, **self._auth())
        data = json.loads(resp.content)
        self.assertIn("document_id", data)

    @patch("core.views.upload_to_s3", return_value=("docs/test.pdf", "https://s3.example.com/test.pdf"))
    @patch("core.views.scan_file", return_value=None)
    @patch("core.views.push_upload_metric")
    @patch("core.views.is_password_protected", return_value=False)
    def test_upload_calls_scan_file(self, _pp, _metric, mock_scan, _s3):
        self.client.post(self.url, {"document": _pdf()}, **self._auth())
        mock_scan.assert_called_once()

    @patch("core.views.upload_to_s3", return_value=("docs/test.pdf", "https://s3.example.com/test.pdf"))
    @patch("core.views.scan_file", return_value=None)
    @patch("core.views.push_upload_metric")
    @patch("core.views.is_password_protected", return_value=False)
    def test_upload_calls_upload_to_s3(self, _pp, _metric, _scan, mock_s3):
        self.client.post(self.url, {"document": _pdf()}, **self._auth())
        mock_s3.assert_called_once()

    # ── Malware detection ──────────────────────────────────────────────────

    @patch("core.views.scan_file", return_value="Eicar-Test-Signature")
    @patch("core.views.is_password_protected", return_value=False)
    def test_upload_infected_file_returns_400(self, _pp, _scan):
        resp = self.client.post(self.url, {"document": _pdf()}, **self._auth())
        self.assertEqual(resp.status_code, 400)

    @patch("core.views.scan_file", return_value="Eicar-Test-Signature")
    @patch("core.views.is_password_protected", return_value=False)
    def test_upload_infected_file_does_not_create_document(self, _pp, _scan):
        self.client.post(self.url, {"document": _pdf()}, **self._auth())
        self.assertFalse(Document.objects.filter(user=self.profile).exists())

    # ── Password-protected file ────────────────────────────────────────────

    @patch("core.views.is_password_protected", return_value=True)
    def test_upload_password_protected_file_returns_400(self, _pp):
        resp = self.client.post(self.url, {"document": _pdf()}, **self._auth())
        self.assertEqual(resp.status_code, 400)

    # ── Invalid / missing input ────────────────────────────────────────────

    def test_upload_unsupported_file_type_returns_400(self):
        resp = self.client.post(self.url, {"document": _exe()}, **self._auth())
        self.assertEqual(resp.status_code, 400)

    def test_upload_missing_file_returns_400(self):
        resp = self.client.post(self.url, {}, **self._auth())
        self.assertEqual(resp.status_code, 400)

    # ── Auth guard ─────────────────────────────────────────────────────────

    def test_upload_no_token_returns_401(self):
        resp = self.client.post(self.url, {"document": _pdf()})
        self.assertEqual(resp.status_code, 401)

    def test_upload_invalid_token_returns_401(self):
        resp = self.client.post(
            self.url, {"document": _pdf()},
            HTTP_AUTHORIZATION="Bearer totally.invalid.token",
        )
        self.assertEqual(resp.status_code, 401)

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_upload_get_request_returns_405(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 2. ANALYZE VIEW TESTS  —  POST /analyze/
# ─────────────────────────────────────────────────────────────────────────────

class AnalyzeViewTest(TestCase):
    """
    Tests for POST /analyze/

    IMPORTANT — this view does NOT use JSON with document_id.
    It reads POST form fields: file_name (required), company_name, department.
    It fetches file bytes from Django cache (key = 'file_bytes_<file_name>').
    Missing file_name → 400. File not in cache → 400.
    On success it returns a StreamingHttpResponse (SSE) with status 200.
    Auth is checked as best-effort; profile may be None (just skips notification).
    """

    def setUp(self):
        self.client  = Client()
        self.url     = "/analyze/"
        self.profile = _make_verified_user()
        self.token   = _get_token(self.client)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    # ── Missing / invalid input (checked before any AI call) ───────────────

    def test_analyze_missing_file_name_returns_400(self):
        resp = self.client.post(self.url, data={}, **self._auth())
        self.assertEqual(resp.status_code, 400)

    def test_analyze_file_not_in_cache_returns_400(self):
        # file_name provided but no bytes are in cache → 400
        resp = self.client.post(
            self.url,
            data={"file_name": "not_cached.pdf"},
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 400)

    # ── Auth guard ─────────────────────────────────────────────────────────
    # analyze_compliance checks auth as best-effort (profile can be None —
    # notification is simply skipped). The view checks file_name BEFORE auth,
    # so a missing file_name always → 400 regardless of token validity.
    # These tests document the actual observable behaviour.

    def test_analyze_no_token_missing_file_name_returns_400(self):
        # No token, no file_name — 400 fires before auth is ever checked
        resp = self.client.post(self.url, data={})
        self.assertEqual(resp.status_code, 400)

    def test_analyze_invalid_token_missing_file_name_returns_400(self):
        # Invalid token, no file_name — same: 400 before auth
        resp = self.client.post(
            self.url, data={},
            HTTP_AUTHORIZATION="Bearer bad.token",
        )
        self.assertEqual(resp.status_code, 400)

    def test_analyze_no_token_file_not_in_cache_returns_400(self):
        # No token but file_name is present — still 400 because bytes not in cache
        resp = self.client.post(self.url, data={"file_name": "ghost.pdf"})
        self.assertEqual(resp.status_code, 400)

    # ── Happy path — bytes seeded in cache → SSE response ─────────────────

    @patch("core.views.cache")
    def test_analyze_cached_file_returns_200_sse(self, mock_cache):
        mock_cache.get.return_value = b"%PDF-1.4 fake bytes"
        resp = self.client.post(
            self.url,
            data={"file_name": "policy.pdf"},
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp.get("Content-Type", ""))

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_analyze_get_request_returns_405(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 3. ANALYZE BATCH VIEW TESTS  —  POST /analyze-batch/
# ─────────────────────────────────────────────────────────────────────────────

class AnalyzeBatchViewTest(TestCase):
    """
    Tests for POST /analyze-batch/

    IMPORTANT — this view does NOT use document_ids.
    It reads a JSON body with a 'files' list; each entry needs 'file_name'.
    Auth is checked FIRST → 401. Then body is parsed → 400 for bad structure.
    Each file_name is looked up in Django cache → 400 if missing.
    On success it returns SSE stream (status 200).
    """

    def setUp(self):
        self.client  = Client()
        self.url     = "/analyze-batch/"
        self.profile = _make_verified_user()
        self.token   = _get_token(self.client)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def _post(self, payload, **extra):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            **extra,
        )

    # ── Auth guard ─────────────────────────────────────────────────────────

    def test_analyze_batch_no_token_returns_401(self):
        resp = self._post({"files": [{"file_name": "a.pdf"}]})
        self.assertEqual(resp.status_code, 401)

    def test_analyze_batch_invalid_token_returns_401(self):
        resp = self.client.post(
            self.url,
            data=json.dumps({"files": [{"file_name": "a.pdf"}]}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer bad.token.here",
        )
        self.assertEqual(resp.status_code, 401)

    # ── Missing / invalid input ────────────────────────────────────────────

    def test_analyze_batch_missing_files_key_returns_400(self):
        resp = self._post({}, **self._auth())
        self.assertEqual(resp.status_code, 400)

    def test_analyze_batch_empty_files_list_returns_400(self):
        resp = self._post({"files": []}, **self._auth())
        self.assertEqual(resp.status_code, 400)

    def test_analyze_batch_entry_missing_file_name_returns_400(self):
        resp = self._post({"files": [{"department": "IT"}]}, **self._auth())
        self.assertEqual(resp.status_code, 400)

    def test_analyze_batch_file_not_in_cache_returns_400(self):
        resp = self._post({"files": [{"file_name": "ghost.pdf"}]}, **self._auth())
        self.assertEqual(resp.status_code, 400)

    # ── Happy path — bytes seeded in cache → SSE response ─────────────────

    @patch("core.views.cache")
    def test_analyze_batch_cached_files_returns_200_sse(self, mock_cache):
        mock_cache.get.return_value = b"%PDF-1.4 fake"
        resp = self._post(
            {"files": [{"file_name": "doc1.pdf"}, {"file_name": "doc2.pdf"}]},
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp.get("Content-Type", ""))

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_analyze_batch_get_request_returns_405(self):
        resp = self.client.get(self.url, **self._auth())
        self.assertEqual(resp.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 4. UPLOAD FROM GOOGLE DRIVE TESTS  —  POST /upload-from-drive/
# ─────────────────────────────────────────────────────────────────────────────

class UploadFromDriveViewTest(TestCase):
    """
    Tests for POST /upload-from-drive/

    Three required JSON fields: file_id, access_token, file_name.
    Auth is checked first → 401. Extension validated before Drive download.
    Drive download uses requests.get (patched at core.views.requests.get).
    Returns SSE StreamingHttpResponse on success.
    """

    def setUp(self):
        self.client  = Client()
        self.url     = "/upload-from-drive/"
        self.profile = _make_verified_user()
        self.token   = _get_token(self.client)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def _post(self, payload, **extra):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            **extra,
        )

    def _valid_payload(self, file_name="policy.pdf"):
        return {
            "file_id":      "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
            "access_token": "ya29.fake-oauth-token",
            "file_name":    file_name,
        }

    # ── Auth guard ─────────────────────────────────────────────────────────

    def test_drive_upload_no_token_returns_401(self):
        resp = self._post(self._valid_payload())
        self.assertEqual(resp.status_code, 401)

    def test_drive_upload_invalid_token_returns_401(self):
        resp = self.client.post(
            self.url,
            data=json.dumps(self._valid_payload()),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer garbage.token",
        )
        self.assertEqual(resp.status_code, 401)

    # ── Missing / invalid input ────────────────────────────────────────────

    def test_drive_upload_missing_file_id_returns_400(self):
        payload = self._valid_payload()
        del payload["file_id"]
        resp = self._post(payload, **self._auth())
        self.assertEqual(resp.status_code, 400)

    def test_drive_upload_missing_access_token_returns_400(self):
        payload = self._valid_payload()
        del payload["access_token"]
        resp = self._post(payload, **self._auth())
        self.assertEqual(resp.status_code, 400)

    def test_drive_upload_missing_file_name_returns_400(self):
        payload = self._valid_payload()
        del payload["file_name"]
        resp = self._post(payload, **self._auth())
        self.assertEqual(resp.status_code, 400)

    def test_drive_upload_empty_body_returns_400(self):
        resp = self._post({}, **self._auth())
        self.assertEqual(resp.status_code, 400)

    def test_drive_upload_unsupported_extension_returns_400(self):
        # .xlsx is not in (.pdf, .docx, .txt) — rejected before hitting Drive
        resp = self._post(self._valid_payload(file_name="data.xlsx"), **self._auth())
        self.assertEqual(resp.status_code, 400)

    def test_drive_upload_exe_extension_returns_400(self):
        resp = self._post(self._valid_payload(file_name="bad.exe"), **self._auth())
        self.assertEqual(resp.status_code, 400)

    # ── Happy path ─────────────────────────────────────────────────────────

    @patch("core.views.upload_to_s3", return_value=("docs/policy.pdf", "https://s3.example.com/policy.pdf"))
    @patch("core.views.scan_file", return_value=None)
    @patch("core.views.push_upload_metric")
    @patch("core.views.is_password_protected", return_value=False)
    @patch("core.views.requests.get")
    def test_drive_upload_valid_pdf_returns_200_sse(self, mock_get, _pp, _metric, _scan, _s3):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.iter_content.return_value = [b"%PDF-1.4 fake drive content"]
        mock_get.return_value = mock_resp

        resp = self._post(self._valid_payload(), **self._auth())
        self.assertEqual(resp.status_code, 200)

    @patch("core.views.upload_to_s3", return_value=("docs/policy.pdf", "https://s3.example.com/policy.pdf"))
    @patch("core.views.scan_file", return_value=None)
    @patch("core.views.push_upload_metric")
    @patch("core.views.is_password_protected", return_value=False)
    @patch("core.views.requests.get")
    def test_drive_upload_creates_document_record(self, mock_get, _pp, _metric, _scan, _s3):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.iter_content.return_value = [b"%PDF-1.4 fake drive content"]
        mock_get.return_value = mock_resp

        self._post(self._valid_payload(), **self._auth())
        self.assertTrue(Document.objects.filter(user=self.profile).exists())

    # ── Drive API error responses ──────────────────────────────────────────

    @patch("core.views.requests.get")
    def test_drive_upload_invalid_google_token_returns_401(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.ok = False
        mock_get.return_value = mock_resp
        resp = self._post(self._valid_payload(), **self._auth())
        self.assertEqual(resp.status_code, 401)

    @patch("core.views.requests.get")
    def test_drive_upload_google_forbidden_returns_403(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.ok = False
        mock_get.return_value = mock_resp
        resp = self._post(self._valid_payload(), **self._auth())
        self.assertEqual(resp.status_code, 403)

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_drive_upload_get_request_returns_405(self):
        resp = self.client.get(self.url, **self._auth())
        self.assertEqual(resp.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 5. UPLOAD FROM ONEDRIVE TESTS  —  POST /upload-from-onedrive/
# ─────────────────────────────────────────────────────────────────────────────

class UploadFromOneDriveViewTest(TestCase):
    """
    Tests for POST /upload-from-onedrive/

    Same structure as Drive: requires file_id, access_token, file_name.
    Additionally calls save_oauth_token() → must be patched at core.views.save_oauth_token.
    Extension validated before OneDrive download.
    """

    def setUp(self):
        self.client  = Client()
        self.url     = "/upload-from-onedrive/"
        self.profile = _make_verified_user()
        self.token   = _get_token(self.client)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def _post(self, payload, **extra):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            **extra,
        )

    def _valid_payload(self, file_name="report.pdf"):
        return {
            "file_id":      "01ABC123ONEDRIVEFAKE",
            "access_token": "EwAoA8l6BAAUFake-ms-token",
            "file_name":    file_name,
        }

    # ── Auth guard ─────────────────────────────────────────────────────────

    def test_onedrive_upload_no_token_returns_401(self):
        resp = self._post(self._valid_payload())
        self.assertEqual(resp.status_code, 401)

    def test_onedrive_upload_invalid_token_returns_401(self):
        resp = self.client.post(
            self.url,
            data=json.dumps(self._valid_payload()),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer wrong.token",
        )
        self.assertEqual(resp.status_code, 401)

    # ── Missing / invalid input ────────────────────────────────────────────

    def test_onedrive_upload_missing_file_id_returns_400(self):
        payload = self._valid_payload()
        del payload["file_id"]
        resp = self._post(payload, **self._auth())
        self.assertEqual(resp.status_code, 400)

    def test_onedrive_upload_missing_access_token_returns_400(self):
        payload = self._valid_payload()
        del payload["access_token"]
        resp = self._post(payload, **self._auth())
        self.assertEqual(resp.status_code, 400)

    def test_onedrive_upload_missing_file_name_returns_400(self):
        payload = self._valid_payload()
        del payload["file_name"]
        resp = self._post(payload, **self._auth())
        self.assertEqual(resp.status_code, 400)

    def test_onedrive_upload_empty_body_returns_400(self):
        resp = self._post({}, **self._auth())
        self.assertEqual(resp.status_code, 400)

    @patch("core.views.save_oauth_token")
    def test_onedrive_upload_unsupported_extension_returns_400(self, _tok):
        resp = self._post(self._valid_payload(file_name="image.png"), **self._auth())
        self.assertEqual(resp.status_code, 400)

    # ── Happy path ─────────────────────────────────────────────────────────

    @patch("core.views.upload_to_s3", return_value=("docs/report.pdf", "https://s3.example.com/report.pdf"))
    @patch("core.views.scan_file", return_value=None)
    @patch("core.views.push_upload_metric")
    @patch("core.views.is_password_protected", return_value=False)
    @patch("core.views.save_oauth_token")
    @patch("core.views.requests.get")
    def test_onedrive_upload_valid_pdf_returns_200(
        self, mock_get, _tok, _pp, _metric, _scan, _s3
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.iter_content.return_value = [b"%PDF-1.4 fake od content"]
        mock_get.return_value = mock_resp

        resp = self._post(self._valid_payload(), **self._auth())
        self.assertEqual(resp.status_code, 200)

    @patch("core.views.upload_to_s3", return_value=("docs/report.pdf", "https://s3.example.com/report.pdf"))
    @patch("core.views.scan_file", return_value=None)
    @patch("core.views.push_upload_metric")
    @patch("core.views.is_password_protected", return_value=False)
    @patch("core.views.save_oauth_token")
    @patch("core.views.requests.get")
    def test_onedrive_upload_creates_document_record(
        self, mock_get, _tok, _pp, _metric, _scan, _s3
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.iter_content.return_value = [b"%PDF-1.4 fake od content"]
        mock_get.return_value = mock_resp

        self._post(self._valid_payload(), **self._auth())
        self.assertTrue(Document.objects.filter(user=self.profile).exists())

    # ── OneDrive API error responses ───────────────────────────────────────

    @patch("core.views.save_oauth_token")
    @patch("core.views.requests.get")
    def test_onedrive_upload_invalid_ms_token_returns_401(self, mock_get, _tok):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.ok = False
        mock_get.return_value = mock_resp
        resp = self._post(self._valid_payload(), **self._auth())
        self.assertEqual(resp.status_code, 401)

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_onedrive_upload_get_request_returns_405(self):
        resp = self.client.get(self.url, **self._auth())
        self.assertEqual(resp.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# 6. DELETE FILE TESTS  —  POST /api/delete-file/
# ─────────────────────────────────────────────────────────────────────────────

class DeleteFileViewTest(TestCase):
    """
    Tests for POST /api/delete-file/

    Key behaviours from views.py lines 948–1016:
      - Auth checked first → 401
      - Accepts 'document_id' (single) or 'document_ids' (list) in JSON body
      - For GENERAL users: queryset filtered by user=profile (line 984)
        → another user's doc is silently excluded — no 403 raised, 200 returned
      - Matching docs are soft-deleted (status=DELETED, deleted_at=now)
      - Then calls boto3.client('s3').delete_objects directly (NOT _delete_s3_keys)
      - If no S3 keys to delete (e.g. non-existent UUID), returns 200 with a note
      - Returns 400 if neither document_id/document_ids nor file_name is provided
    """

    def setUp(self):
        self.client  = Client()
        self.url     = "/api/delete-file/"
        self.profile = _make_verified_user()
        self.token   = _get_token(self.client)

        self.doc = Document.objects.create(
            user=self.profile,
            original_filename="to_delete.pdf",
            file_type="PDF",
            s3_key="docs/to_delete.pdf",
            status=Document.Status.UPLOADED,
        )

        self.other_profile = _make_verified_user(email=OTHER_EMAIL, name=OTHER_NAME)
        self.other_token   = _get_token(self.client, OTHER_EMAIL)
        self.other_doc = Document.objects.create(
            user=self.other_profile,
            original_filename="other.pdf",
            file_type="PDF",
            s3_key="docs/other.pdf",
            status=Document.Status.UPLOADED,
        )

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def _post(self, payload, **extra):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            **extra,
        )

    # ── Happy path ─────────────────────────────────────────────────────────

    @patch("core.views.boto3.client")
    def test_delete_valid_document_returns_200(self, mock_boto):
        mock_boto.return_value.delete_objects.return_value = {}
        resp = self._post({"document_id": str(self.doc.document_id)}, **self._auth())
        self.assertEqual(resp.status_code, 200)

    @patch("core.views.boto3.client")
    def test_delete_soft_deletes_document(self, mock_boto):
        mock_boto.return_value.delete_objects.return_value = {}
        self._post({"document_id": str(self.doc.document_id)}, **self._auth())
        self.doc.refresh_from_db()
        self.assertIsNotNone(self.doc.deleted_at)

    @patch("core.views.boto3.client")
    def test_delete_sets_status_to_deleted(self, mock_boto):
        mock_boto.return_value.delete_objects.return_value = {}
        self._post({"document_id": str(self.doc.document_id)}, **self._auth())
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, Document.Status.DELETED)

    @patch("core.views.boto3.client")
    def test_delete_calls_s3_delete_objects(self, mock_boto):
        mock_s3 = mock_boto.return_value
        mock_s3.delete_objects.return_value = {}
        self._post({"document_id": str(self.doc.document_id)}, **self._auth())
        mock_s3.delete_objects.assert_called_once()

    # ── Permission: GENERAL user cannot delete another user's doc ──────────

    @patch("core.views.boto3.client")
    def test_delete_other_user_document_leaves_it_intact(self, mock_boto):
        """
        The view filters by user=profile for non-admins. Attempting to delete
        another user's document silently excludes it — no 403, returns 200,
        but the document must remain untouched in the DB.
        """
        mock_boto.return_value.delete_objects.return_value = {}
        self._post(
            {"document_id": str(self.other_doc.document_id)},
            **self._auth(),
        )
        self.other_doc.refresh_from_db()
        self.assertIsNone(self.other_doc.deleted_at)

    # ── Non-existent UUID — no match; view returns 200 with note ──────────

    def test_delete_nonexistent_uuid_returns_200(self):
        # A well-formed UUID that doesn't exist; view skips S3 and returns 200
        resp = self._post({"document_id": str(uuid.uuid4())}, **self._auth())
        self.assertEqual(resp.status_code, 200)

    # ── Missing input ──────────────────────────────────────────────────────

    def test_delete_missing_document_id_returns_400(self):
        resp = self._post({}, **self._auth())
        self.assertEqual(resp.status_code, 400)

    # ── Auth guard ─────────────────────────────────────────────────────────

    def test_delete_no_token_returns_401(self):
        resp = self._post({"document_id": str(self.doc.document_id)})
        self.assertEqual(resp.status_code, 401)

    def test_delete_invalid_token_returns_401(self):
        resp = self.client.post(
            self.url,
            data=json.dumps({"document_id": str(self.doc.document_id)}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer bogus.token.value",
        )
        self.assertEqual(resp.status_code, 401)

    # ── HTTP method guard ──────────────────────────────────────────────────

    def test_delete_get_request_returns_405(self):
        resp = self.client.get(self.url, **self._auth())
        self.assertEqual(resp.status_code, 405)