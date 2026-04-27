# CyberComply — Backend Testing Guide

> **Sprint 3 | Team Reference Document**
> This guide covers everything you need to set up, write, and run your assigned backend tests.
> Read this fully before writing a single line of test code.

---


## 1. Overview

We are writing two types of backend tests this sprint:

| Type | What it tests | Tool |
|---|---|---|
| **View / API Unit Tests** | Each Django view function in isolation — correct HTTP status codes, authentication enforcement, permission checks, error handling | `Django TestClient` + `pytest-django` |
| **Integration Tests** | Realistic multi-step user flows end-to-end (e.g. signup → login → upload → analyse → report) | `Django TestClient` + real DB, mocked external services |

The existing `tests.py` already covers **model-level unit tests** (database models, constraints, relationships). **Do not duplicate those.** Your job is the **view/API layer only.**

---

## 2. One-Time Setup

Run these commands once from the `DjangoManager/` directory with your virtual environment active.

### Activate the virtual environment (Windows)

```powershell
venv\Scripts\activate
```

### Install testing dependencies

```bash
pip install pytest==9.0.2 pytest-django==4.12.0 reportlab==4.4.10
```

These three packages are already added to `requirements.txt`. If you pulled the latest code, they may already be installed. Verify with:

```bash
pip show pytest pytest-django reportlab
```

---

## 3. Where to Create Your Test File

All test files live inside the `core` app folder, at the same level as the existing `tests.py`:

```
sd04_2025/
└── DjangoManager/
    ├── manage.py
    ├── generate_test_report.py       ← PDF report generator (already here)
    └── core/
        ├── models.py
        ├── views.py
        ├── urls.py
        ├── tests.py                  ← existing model tests (DO NOT MODIFY)
        ├── tests_views_auth.py       ← Member 1 (DONE — use as reference)
        ├── tests_views_profile.py    ← Member 2
        ├── tests_views_documents.py  ← Member 3
        ├── tests_views_analysis.py   ← Member 4
        ├── tests_views_reports.py    ← Member 5
        ├── tests_views_deletion.py   ← Member 6
        ├── tests_views_admin.py      ← Member 7
        └── tests_integration.py      ← Member 7
```

**File naming rule:** All test files must start with `tests_` so Django's test runner discovers them automatically. (Simply use the file name given above for clarity)

---

## 4. Team Assignment Table

| Member | Test File | Endpoints Covered | Description |
|---|---|---|---|
| **Member 1** *(Vivek)* | `tests_views_auth.py` | `POST /api/signup/` `POST /api/login/` `POST /api/verify-otp/` `POST /api/session-token/` `POST /api/logout/` | Signup validation, login lockout, OTP flows, session token issuance, logout cleanup |
| **Member 2** *(Suwarnadaran)* | `tests_views_profile.py` | `GET /api/profile/` `PATCH /api/profile/update/` `POST /api/profile/twofa/` `POST /api/request-email-change/` `POST /api/verify-email-change/` | Profile fetch, name update, enable/disable 2FA, email change OTP flow |
| **Member 3** *(Bimsara)* | `tests_views_documents.py` | `POST /upload/` `POST /analyze/` `POST /analyze-batch/` `POST /upload-from-drive/` `POST /upload-from-onedrive/` `POST /api/delete-file/` | File upload (valid/invalid types), malware scan mock, S3 mock, analysis trigger |
| **Member 4** *(Ammaar)* | `tests_views_analysis.py` | `POST /api/analysis/save/` `GET /api/analysis/latest/` `GET /api/analysis/history/` `GET /api/analysis/<id>/` `GET /api/analysis/<id>/findings/` `POST /api/recommendations/save/` `GET /api/recommendations/` | Save/retrieve analysis results, findings per result, cross-user access (403), recommendations |
| **Member 5** *(Ibrahim)* | `tests_views_reports.py` | `POST /api/reports/generate/` `GET /api/reports/` `GET /api/reports/<id>/` `DELETE /api/reports/<id>/delete/` `POST /api/download-report/` `POST /api/share-report/` `GET /api/reports/resolve-token/` | Generate report, list (user vs admin scope), get/delete access control, share presigned URL |
| **Member 6** *(Erandathi)* | `tests_views_deletion.py` | `POST /api/request-delete-account/` `POST /api/verify-delete-account-otp/` `POST /api/delete-account/` `GET /api/deletion-request/status/` | Full deletion flow, DeletionRequest row persists post-delete, sub-table cleanup, S3 cleanup mock |
| **Member 7** *(Sehansa)* | `tests_views_admin.py` + `tests_integration.py` | `POST /api/admin-access/request/` `POST /api/admin-access/verify/` `GET /api/admin-access/status/` `GET /api/notifications/unread/` `POST /api/notifications/mark-read/` + full end-to-end flows | Admin upgrade OTP flow, role enforcement, notifications; integration: signup→login→upload→analyse→report |

---

## 5. What to Include in Your Test File

### Minimum structure every file must have

```python
"""
tests_views_<group>.py — Group N: <Group Name> View Tests
==========================================================
Covers:
  LIST THE ENDPOINTS YOU ARE TESTING HERE

Run with:
  python manage.py test core.tests_views_<group> --verbosity=2
"""

import json
from unittest.mock import patch
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from core.models import UserProfile  # import whatever models you need


# ── Helper: create a verified user directly (bypasses signup/OTP) ──────────
def _make_verified_user(email="test@example.com", name="Test User",
                        role=UserProfile.Role.GENERAL, password="Str0ng!Pass99"):
    auth = User.objects.create_user(username=email, email=email, password=password)
    return UserProfile.objects.create(
        auth_user=auth, full_name=name, role=role,
        is_verified=True, otp_is_enabled=False,
    )


# ── Helper: get a real Bearer token for a verified user ────────────────────
def _get_token(client, email):
    resp = client.post(
        "/api/session-token/",
        data=json.dumps({"email": email}),
        content_type="application/json",
    )
    return json.loads(resp.content)["token"]


class YourGroupViewTest(TestCase):
    def setUp(self):
        self.client  = Client()
        self.profile = _make_verified_user()
        self.token   = _get_token(self.client, "test@example.com")

    def _auth(self):
        """Return the Authorization header dict for use in requests."""
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    # ── Happy path ──────────────────────────────────────────────────────────

    def test_<endpoint>_<expected_outcome>(self):
        resp = self.client.get("/api/your-endpoint/", **self._auth())
        self.assertEqual(resp.status_code, 200)

    # ── Auth guard ─────────────────────────────────────────────────────────

    def test_<endpoint>_no_token_returns_401(self):
        resp = self.client.get("/api/your-endpoint/")
        self.assertEqual(resp.status_code, 401)
```

### Test naming convention

Follow this pattern — it makes the PDF report and terminal output readable for everyone:

```
test_<endpoint_or_action>_<expected_outcome>

Examples:
  test_generate_report_valid_result_returns_200
  test_get_report_other_user_returns_403
  test_delete_report_owner_removes_record
  test_list_reports_admin_sees_org_reports
  test_upload_invalid_file_type_returns_400
```

### Required test categories per endpoint

For **every endpoint you cover**, include at minimum:

| Category | What to test |
|---|---|
| **Happy path** | Valid request with authenticated user → correct status + response shape |
| **Auth guard** | No token → 401, invalid token → 401 |
| **Permission check** | If the endpoint is admin-only, verify a general user gets 403. If it's owner-only, verify another user gets 403 |
| **Missing / invalid input** | Missing required fields → 400, wrong types → 400 |
| **HTTP method guard** | Wrong method (GET on a POST endpoint) → 405 |
| **Not found** | Non-existent resource ID → 404 |

---

## 6. Key Patterns Every Member Must Follow

### Pattern 1 — Getting a Bearer token in tests

Every protected endpoint requires `Authorization: Bearer <token>`. Get it via `issue_session_token`:

```python
def _get_token(client, email):
    resp = client.post(
        "/api/session-token/",
        data=json.dumps({"email": email}),
        content_type="application/json",
    )
    return json.loads(resp.content)["token"]
```

Then pass it in requests:

```python
resp = self.client.get(
    "/api/analysis/history/",
    HTTP_AUTHORIZATION=f"Bearer {self.token}",
)
```

### Pattern 2 — Mocking AWS S3

Any test that triggers a real S3 call (upload, delete, share) will fail without real credentials. Mock it:

```python
from unittest.mock import patch

@patch("core.views._delete_s3_keys", return_value={"deleted": [], "failed": []})
def test_logout_cleans_up_files(self, mock_s3):
    resp = self.client.post("/api/logout/", HTTP_AUTHORIZATION=f"Bearer {self.token}")
    self.assertEqual(resp.status_code, 200)
    mock_s3.assert_called_once()
```

For S3 upload in the upload view:

```python
@patch("core.views.upload_to_s3", return_value=("docs/test.pdf", "https://s3.example.com/test.pdf"))
@patch("core.views.scan_file",    return_value=None)   # None = clean file
def test_upload_valid_pdf(self, mock_scan, mock_s3):
    ...
```

### Pattern 3 — Mocking email (SES)

Any test that triggers OTP sending will call AWS SES. Mock it:

```python
@patch("core.views.send_otp_email", return_value=True)
def test_request_email_change_sends_otp(self, mock_email):
    resp = self.client.post(...)
    self.assertTrue(mock_email.called)
```

### Pattern 4 — Creating test data directly (not through the API)

Use Django ORM directly in `setUp` for speed. Do NOT call the signup API to create users you need for unrelated tests — that creates unnecessary coupling.

```python
# GOOD — fast, isolated
profile = _make_verified_user(email="admin@sliit.lk", role=UserProfile.Role.ADMIN)

# AVOID — slow, depends on signup logic working correctly
self.client.post("/api/signup/", data=json.dumps({...}), content_type="application/json")
```

### Pattern 5 — Testing 403 (permission denied)

Create a second user and verify they cannot access the first user's resources:

```python
def test_get_report_other_user_returns_403(self):
    # Create another user and get their token
    other = _make_verified_user(email="other@example.com", name="Other User")
    other_token = _get_token(self.client, "other@example.com")

    # Try to access first user's report with other user's token
    resp = self.client.get(
        f"/api/reports/{self.report_id}/",
        HTTP_AUTHORIZATION=f"Bearer {other_token}",
    )
    self.assertEqual(resp.status_code, 403)
```

---

## 7. Running Your Tests

All commands are run from the `DjangoManager/` directory with your virtual environment active.

### Run your own test file only

```powershell
python manage.py test core.tests_views_<group> --verbosity=2
```

For example:

```powershell
python manage.py test core.tests_views_profile --verbosity=2
```

### Run a single test class

```powershell
python manage.py test core.tests_views_profile.ProfileViewTest --verbosity=2
```

### Run a single test method

```powershell
python manage.py test core.tests_views_profile.ProfileViewTest.test_get_profile_returns_200 --verbosity=2
```

### Run the entire backend test suite (all files)

```powershell
python manage.py test core --verbosity=2
```

### Run the existing model tests only (to make sure you haven't broken anything)

```powershell
python manage.py test core.tests --verbosity=2
```

### What a passing run looks like

```
Found 81 test(s).
Creating test database for alias 'default' ('test_cybercomply_db')...
...
test_signup_general_user_returns_201 (core.tests_views_auth.SignupViewTest) ... ok
test_login_valid_credentials_returns_200 (core.tests_views_auth.LoginViewTest) ... ok
...
Ran 81 tests in 37.785s

OK
```

---

## 8. Generating the PDF Report

A PDF report script is included at `DjangoManager/generate_test_report.py`. It runs the tests automatically and produces a formatted PDF with a summary table, per-class coverage, and full output.

### Run it

```powershell
# From DjangoManager/ with venv active:
python generate_test_report.py

# Or for a specific test module:
python generate_test_report.py core.tests_views_profile
```

### Output

A file named `test_report_YYYYMMDD_HHMMSS.pdf` is saved in `DjangoManager/`. Open it directly — it contains:

- Overall pass/fail verdict with stat boxes
- Full per-test results table (class, test name, PASS/FAIL)
- Coverage summary by test class
- Failure tracebacks if any tests failed
- Full raw terminal output (with JSON middleware logs filtered out)

> **Note:** Do not commit the PDF file, move it away from DjangoManager folder and add it to the subfolder in 'Sprint 4 Evidence for Agile'.



---

## Quick Reference Card

| Task | Command |
|---|---|
| Activate venv | `venv\Scripts\activate` |
| Install dependencies | `pip install pytest==9.0.2 pytest-django==4.12.0 reportlab==4.4.10` |
| Run my tests | `python manage.py test core.tests_views_<group> --verbosity=2` |
| Run all tests | `python manage.py test core --verbosity=2` |
| Generate PDF report | `python generate_test_report.py` |
| Check installed versions | `pip show pytest pytest-django reportlab` |

---

*Last updated: Sprint 4 (27th April 2026) — prepared by Vivek Edirisinghe*