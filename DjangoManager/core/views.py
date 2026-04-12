from django.shortcuts import render
import requests
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import transaction, IntegrityError
from django.core.validators import validate_email
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.contrib.auth import authenticate
from django.utils import timezone
from datetime import timedelta
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.conf import settings
from .email_service import send_otp_email
from django.core.cache import cache
import random
import hashlib
import json, time
import socket
import tempfile
import os
import boto3
import re
import uuid
from botocore.exceptions import BotoCoreError, ClientError
import logging
logger = logging.getLogger(__name__)

from .models import (
    UserProfile, LoginHistory, OtpVerification,
    Document, Organization, Department,
    AnalysisResult, Finding, Recommendation,
    Report, AuditLog, AdminAccessRequest,
    ReportDownload, DeletionRequest, ReportShare,
)
from .utils import validate_org_email
from django.db import models

# ──────────────────────────────────────────────
# Security Configuration
# ──────────────────────────────────────────────

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES    = 15
MAX_OTP_ATTEMPTS   = 5

AI_API_URL = "http://127.0.0.1:5000/api"


# ──────────────────────────────────────────────
# Home view
# ──────────────────────────────────────────────

def home(request):
    return render(request, 'home.html')


# ──────────────────────────────────────────────
# AWS / File helpers
# ──────────────────────────────────────────────

def is_password_protected(file_path, file_name):
    try:
        ext = file_name.lower().split('.')[-1]
        if ext == 'pdf':
            import PyPDF2
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                return reader.is_encrypted
        elif ext == 'docx':
            import docx
            try:
                docx.Document(file_path)
                return False
            except Exception:
                return True
        return False
    except Exception:
        return False


def scan_file(file_path):
    """
    Scans a file via ClamAV.
    Returns None if clean.
    Returns 'SCAN_ERROR:<msg>' if the scanner is unavailable.
    Returns the threat string if malware is detected.
    """
    try:
        cd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cd.connect((settings.CLAMAV_HOST, settings.CLAMAV_PORT))
        with open(file_path, 'rb') as f:
            file_data = f.read()
        cd.send(b'zINSTREAM\0')
        size = len(file_data)
        cd.send(size.to_bytes(4, byteorder='big'))
        cd.send(file_data)
        cd.send((0).to_bytes(4, byteorder='big'))
        result = cd.recv(1024).decode()
        cd.close()
        if 'OK' in result:
            return None  # Clean
        else:
            return result  # Threat detected
    except Exception as e:
        return f"SCAN_ERROR:{str(e)}"


def upload_to_s3(file_path, file_name):
    """
    Uploads a local file to S3.
    Returns (s3_key, s3_url) on success, or (None, None) on failure.
    Storing the key (not the URL) in the DB is preferred — the URL can always
    be reconstructed from the key, but the key cannot safely be parsed back
    from a URL if the bucket/region/domain ever changes.
    """
    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        s3.upload_file(file_path, bucket_name, file_name)
        s3_key = file_name
        s3_url = f"https://{bucket_name}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{file_name}"
        return s3_key, s3_url
    except (BotoCoreError, ClientError) as e:
        logger.error("S3 upload failed for %s: %s", file_name, str(e))
        return None, None


def _mime_type_for(file_name):
    """Return the correct MIME type based on file extension."""
    ext = file_name.lower().split('.')[-1]
    return {
        'pdf':  'application/pdf',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'txt':  'text/plain',
    }.get(ext, 'application/octet-stream')


# ──────────────────────────────────────────────
# OAuth Token helpers (SSM Parameter Store)
# ──────────────────────────────────────────────

def save_oauth_token(user_id: str, provider: str, token: str):
    """Save a user's OAuth token securely to AWS SSM Parameter Store."""
    try:
        ssm = boto3.client(
            'ssm',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        ssm.put_parameter(
            Name=f"/cybercomply/oauth/{user_id}/{provider}_token",
            Value=token,
            Type="SecureString",
            Overwrite=True,
        )
        return True
    except (BotoCoreError, ClientError) as e:
        logger.error("ERROR saving OAuth token for %s/%s: %s", user_id, provider, e)
        return False


def get_oauth_token(user_id: str, provider: str):
    """Retrieve a user's OAuth token from AWS SSM Parameter Store."""
    try:
        ssm = boto3.client(
            'ssm',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        response = ssm.get_parameter(
            Name=f"/cybercomply/oauth/{user_id}/{provider}_token",
            WithDecryption=True,
        )
        return response["Parameter"]["Value"]
    except (BotoCoreError, ClientError) as e:
        logger.error("ERROR retrieving OAuth token for %s/%s: %s", user_id, provider, e)
        return None


# ──────────────────────────────────────────────
# Auth helper — resolve UserProfile from
# Authorization: Bearer <token> header.
# Returns (profile, None) on success or
# (None, JsonResponse) on failure.
# ──────────────────────────────────────────────

def _get_profile_from_token(request):
    """
    Validates the signed session token from the Authorization: Bearer <token> header.
    Returns (UserProfile, None) on success.
    Returns (None, JsonResponse) when the token is missing, expired, or invalid.
    """
    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header.startswith("Bearer "):
        return None, JsonResponse({"detail": "Authentication required"}, status=401)
    token = auth_header[len("Bearer "):].strip()
    if not token:
        return None, JsonResponse({"detail": "Authentication required"}, status=401)

    try:
        data = signing.loads(token, salt="session-token", max_age=86400)  # 24-hour TTL
    except SignatureExpired:
        return None, JsonResponse({"detail": "Session expired. Please log in again."}, status=401)
    except BadSignature:
        return None, JsonResponse({"detail": "Invalid session token"}, status=401)

    user_id = data.get("uid")
    if not user_id:
        return None, JsonResponse({"detail": "Invalid session token"}, status=401)

    try:
        profile = (
            UserProfile.objects
            .select_related("auth_user", "org")
            .get(user_id=user_id)
        )
    except (ObjectDoesNotExist, Exception):
        return None, JsonResponse({"detail": "User not found"}, status=401)

    if profile.deleted_at is not None:
        return None, JsonResponse({"detail": "Account has been deleted"}, status=401)

    if not profile.is_verified:
        return None, JsonResponse({"detail": "Account not verified"}, status=403)

    return profile, None


# ──────────────────────────────────────────────
# Phase 1 — Device upload (validate → scan → S3)
# Does NOT call the AI service.
# ──────────────────────────────────────────────

@csrf_exempt
def upload_file(request):
    """
    Receives a single file from the frontend, runs security checks, and stores
    it in S3. Returns plain JSON so the frontend can update the file's status
    badge to UPLOADED.
    The AI analysis step is intentionally absent — it is triggered separately
    by the Analyse button via analyze_compliance or analyze_batch.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error
    assert profile is not None

    uploaded_file = request.FILES.get('document')
    company_name  = request.POST.get('company_name', '').strip()
    department    = request.POST.get('department', '').strip()

    if not uploaded_file:
        return JsonResponse({'error': 'No file provided'}, status=400)

    # Resolve Organisation & Department FIRST, before touching S3
    org  = None
    dept = None

    if profile.role == UserProfile.Role.ADMIN:
        if not company_name:
            _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request)
            return JsonResponse({'error': 'Organisation name is required.'}, status=400)
        if not department:
            _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request)
            return JsonResponse({'error': 'Department is required. Please select a department before uploading.'}, status=400)
        org, _  = Organization.objects.get_or_create(org_name=company_name)
        dept, _ = Department.objects.get_or_create(org=org, dept_name=department)
        if not profile.org_id:
            profile.org = org
            profile.save(update_fields=["org"])

    ext = uploaded_file.name.lower().rsplit('.', 1)[-1]
    file_type_map = {'pdf': 'PDF', 'docx': 'DOCX', 'txt': 'TXT'}
    file_type = file_type_map.get(ext)
    if not file_type:
        _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.LOW)
        return JsonResponse({'error': 'Unsupported file type. Only PDF, DOCX, and TXT are allowed.'}, status=400)

    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        for chunk in uploaded_file.chunks():
            temp_file.write(chunk)
        temp_path = temp_file.name

    try:
        if is_password_protected(temp_path, uploaded_file.name):
            _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.LOW)
            return JsonResponse({'error': 'File rejected — password protected files are not allowed'}, status=400)

        scan_result = scan_file(temp_path)
        if scan_result is not None:
            if scan_result.startswith('SCAN_ERROR:'):
                _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.MEDIUM)
                return JsonResponse({'error': 'File could not be scanned. The security scanner is temporarily unavailable. Please try again shortly.'}, status=503)
            _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.HIGH)
            return JsonResponse({'error': 'File rejected — malware detected'}, status=400)

        s3_key, s3_url = upload_to_s3(temp_path, uploaded_file.name)
        if s3_key is None:
            logger.error("S3 upload returned None for file %s, user %s", uploaded_file.name, profile.user_id)
            _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.HIGH)
            return JsonResponse({'error': 'Failed to upload file to S3. Please try again in a few minutes.'}, status=500)

        with open(temp_path, 'rb') as f:
            file_bytes = f.read()
        cache.set(f'file_bytes_{uploaded_file.name}', file_bytes, timeout=3600)

        document = Document.objects.create(
            user=profile,
            org=org,
            dept=dept,
            original_filename=uploaded_file.name,
            file_type=file_type,
            size_bytes=uploaded_file.size,
            s3_key=s3_key,
            status=Document.Status.UPLOADED,
        )

        _record_audit_log(profile, "UPLOAD", "document", document.document_id, True, request, AuditLog.Severity.LOW)
        return JsonResponse({
            'status':      'uploaded',
            's3_url':      s3_url,
            'file_name':   uploaded_file.name,
            'document_id': str(document.document_id),
        })

    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


# ──────────────────────────────────────────────
# Phase 2a — Analyse single file (SSE stream)
# Triggered by the Analyse button (single file).
# ──────────────────────────────────────────────

@csrf_exempt
def analyze_compliance(request):
    """
    Reads file bytes from cache, forwards to AI service, streams SSE events back,
    and persists the result + report to the database.

    SSE events emitted:
        data: {"status": "analysing"}
        data: {"status": "analysed", "result": {...}}
        data: {"status": "error",    "message": "..."}
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    file_name    = request.POST.get('file_name', '').strip()
    company_name = request.POST.get('company_name', '')
    department   = request.POST.get('department', '')

    if not file_name:
        return JsonResponse({'error': 'file_name is required'}, status=400)

    file_bytes = cache.get(f'file_bytes_{file_name}')
    if file_bytes is None:
        return JsonResponse(
            {'error': f'File bytes for "{file_name}" not found in cache. Please re-upload.'},
            status=400,
        )

    def event_stream():
        try:
            yield f"data: {json.dumps({'status': 'analysing'})}\n\n".encode('utf-8')

            files    = {'file': (file_name, file_bytes, _mime_type_for(file_name))}
            data     = {'company_name': company_name, 'department': department}
            response = requests.post(f"{AI_API_URL}/analyze", files=files, data=data, timeout=1200)
            result   = response.json()

            # Persist AnalysisResult + Report to database (non-critical — don't break SSE)
            try:
                import json as _json
                document = Document.objects.filter(
                    s3_key=file_name, deleted_at__isnull=True
                ).order_by('-uploaded_at').first()

                if document is not None:
                    AnalysisResult.objects.filter(document=document).delete()
                    analysis_result = AnalysisResult.objects.create(
                        document=document,
                        compliance_score=max(0, min(100, int(round(float(
                            result.get('compliance', {}).get('compliance_score', 0)
                        ))))),
                        risk_level=(
                            'LOW'    if float(result.get('compliance', {}).get('compliance_score', 0)) >= 75
                            else 'MEDIUM' if float(result.get('compliance', {}).get('compliance_score', 0)) >= 40
                            else 'HIGH'
                        ),
                        summary=result.get('summary') or result.get('recommendations', {}).get('top_action') or None,
                        raw_output=result,
                    )
                    snapshot     = {**result, 'metadata': {**result.get('metadata', {}), 'file_analyzed': file_name, 'company': company_name}}
                    snapshot_str = _json.dumps(snapshot)
                    Report.objects.create(
                        result=analysis_result,
                        dept=document.dept,
                        report_snapshot=snapshot,
                        report_s3_key=file_name,
                        file_size=len(snapshot_str),
                        expires_at=timezone.now() + timedelta(days=30),
                    )
            except Exception:
                pass

            yield f"data: {json.dumps({'status': 'analysed', 'result': result})}\n\n".encode('utf-8')
            cache.delete(f'file_bytes_{file_name}')

        except requests.exceptions.ConnectionError:
            yield f"data: {json.dumps({'status': 'error', 'message': 'AI Server is not running.'})}\n\n".encode('utf-8')
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n".encode('utf-8')

    return StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


# ──────────────────────────────────────────────
# Phase 2b — Analyse multiple files (batch)
# Triggered by the Analyse button (multiple files).
# ──────────────────────────────────────────────

@csrf_exempt
def analyze_batch(request):
    """
    Expected request body:
    {
        "company_name": "Acme Corp",
        "files": [
            {"file_name": "policy.pdf",  "department": "IT"},
            {"file_name": "report.docx", "department": "Finance"}
        ]
    }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    company_name = payload.get('company_name', '')
    files        = payload.get('files', [])

    if not files or not isinstance(files, list):
        return JsonResponse({'error': 'A non-empty "files" list is required'}, status=400)

    multipart_files = []
    for entry in files:
        file_name  = (entry.get('file_name') or '').strip()
        department = (entry.get('department') or '').strip()
        if not file_name:
            return JsonResponse({'error': 'Each file entry must include a file_name'}, status=400)
        file_bytes = cache.get(f'file_bytes_{file_name}')
        if file_bytes is None:
            return JsonResponse(
                {'error': f'File bytes for "{file_name}" not found in cache. Please re-upload.'},
                status=400,
            )
        multipart_files.append({'file_name': file_name, 'department': department, 'file_bytes': file_bytes})

    try:
        files_payload = [
            ('files', (f['file_name'], f['file_bytes'], _mime_type_for(f['file_name'])))
            for f in multipart_files
        ]
        data_payload = {
            'company_name': company_name,
            'departments':  ','.join(f['department'] for f in multipart_files),
        }
        response = requests.post(f"{AI_API_URL}/analyze-batch", files=files_payload, data=data_payload, timeout=1200)
        result   = response.json()

        for f in multipart_files:
            cache.delete(f'file_bytes_{f["file_name"]}')

        return JsonResponse({'status': 'analysed', 'result': result})

    except requests.exceptions.ConnectionError:
        return JsonResponse({'error': 'AI Server is not running.'}, status=503)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ──────────────────────────────────────────────
# S3 File Deletion
# ──────────────────────────────────────────────

@csrf_exempt
def delete_file(request):
    """
    Soft-deletes Document record(s) and hard-deletes from S3.
    Requires a valid Bearer token. Users may only delete their own documents.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error
    assert profile is not None

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    file_name    = data.get('file_name', '').strip()
    file_names   = data.get('file_names', [])
    document_id  = data.get('document_id', '').strip()
    document_ids = data.get('document_ids', [])

    if file_name:
        file_names.append(file_name)
    if document_id:
        document_ids.append(document_id)

    if not file_names and not document_ids:
        return JsonResponse({'error': 'No file names or document IDs provided'}, status=400)

    now = timezone.now()

    if document_ids:
        docs_qs = Document.objects.filter(document_id__in=document_ids, deleted_at__isnull=True)
        if profile.role != UserProfile.Role.ADMIN:
            docs_qs = docs_qs.filter(user=profile)
        docs_qs.update(status=Document.Status.DELETED, deleted_at=now)
    elif file_names:
        docs_qs = Document.objects.filter(s3_key__in=file_names, deleted_at__isnull=True)
        if profile.role != UserProfile.Role.ADMIN:
            docs_qs = docs_qs.filter(user=profile)
        docs_qs.update(status=Document.Status.DELETED, deleted_at=now)

    keys_to_delete = list(file_names)
    if document_ids and not file_names:
        keys_to_delete = list(
            Document.objects.filter(document_id__in=document_ids).values_list('s3_key', flat=True)
        )

    if not keys_to_delete:
        return JsonResponse({'status': 'Document record(s) soft-deleted (no S3 keys to remove)'})

    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        s3.delete_objects(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Delete={'Objects': [{'Key': k} for k in keys_to_delete]},
        )
        _record_audit_log(profile, "DELETE", "document", None, True, request)
        return JsonResponse({'status': f'{len(keys_to_delete)} file(s) deleted'})

    except (BotoCoreError, ClientError) as e:
        return JsonResponse({'error': f'DB record soft-deleted but S3 deletion failed: {str(e)}'}, status=500)


# ──────────────────────────────────────────────
# Google Drive Upload — Phase 1 only
# ──────────────────────────────────────────────

@csrf_exempt
def upload_from_drive(request):
    """
    Frontend sends file_id + OAuth token; Django downloads from Drive,
    scans, stores in S3, creates a Document record. No AI call.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error
    assert profile is not None

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    file_id      = (payload.get('file_id')      or '').strip()
    access_token = (payload.get('access_token') or '').strip()
    file_name    = (payload.get('file_name')    or '').strip()
    company_name = (payload.get('company_name') or '').strip()
    department   = (payload.get('department')   or '').strip()

    if not file_id or not access_token or not file_name:
        return JsonResponse({'error': 'file_id, access_token and file_name are required'}, status=400)

    valid_exts = ('.pdf', '.docx', '.txt')
    if not file_name.lower().endswith(valid_exts):
        _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.LOW)
        return JsonResponse({'error': f'"{file_name}" is not supported. Only PDF, DOCX and TXT files are allowed.'}, status=400)

    # Resolve Organisation & Department
    org  = None
    dept = None
    if profile.role == UserProfile.Role.ADMIN:
        if not company_name:
            _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request)
            return JsonResponse({'error': 'Organisation name is required.'}, status=400)
        if not department:
            _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request)
            return JsonResponse({'error': 'Department is required for each file.'}, status=400)
        org, _  = Organization.objects.get_or_create(org_name=company_name)
        dept, _ = Department.objects.get_or_create(org=org, dept_name=department)
    else:
        org  = profile.org
        dept = None

    ext = file_name.lower().rsplit('.', 1)[-1]
    file_type_map = {'pdf': 'PDF', 'docx': 'DOCX', 'txt': 'TXT'}
    file_type = file_type_map.get(ext)
    if not file_type:
        _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.LOW)
        return JsonResponse({'error': 'Unsupported file type. Only PDF, DOCX, and TXT are allowed.'}, status=400)

    # Download from Google Drive
    download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    try:
        drive_response = requests.get(
            download_url,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=60,
            stream=True,
        )
    except requests.exceptions.RequestException as e:
        logger.error("Google Drive download failed for file %s, user %s: %s", file_name, profile.user_id, str(e))
        _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.MEDIUM)
        return JsonResponse({'error': 'Could not reach Google Drive. Please check your connection and try again.'}, status=502)

    if drive_response.status_code == 401:
        _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.LOW)
        return JsonResponse({'error': 'Google access token is invalid or expired'}, status=401)
    if drive_response.status_code == 403:
        _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.LOW)
        return JsonResponse({'error': 'Permission denied — cannot access this Google Drive file'}, status=403)
    if not drive_response.ok:
        logger.error("Google Drive returned HTTP %s for file %s, user %s", drive_response.status_code, file_name, profile.user_id)
        _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.MEDIUM)
        return JsonResponse({'error': 'Google Drive is temporarily unavailable. Please try again in a few minutes.'}, status=502)

    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as tmp:
        for chunk in drive_response.iter_content(chunk_size=8192):
            tmp.write(chunk)
        temp_path = tmp.name

    # streaming_started tracks whether we handed off to StreamingHttpResponse.
    # If True, event_stream()'s finally block owns cleanup.
    streaming_started = False

    try:
        file_size = os.path.getsize(temp_path)
        if file_size > 50 * 1024 * 1024:
            _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.LOW)
            return JsonResponse({'error': f'"{file_name}" exceeds the 50 MB limit.'}, status=400)

        if is_password_protected(temp_path, file_name):
            _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.LOW)
            return JsonResponse({'error': 'File rejected — password protected files are not allowed'}, status=400)

        scan_result = scan_file(temp_path)
        if scan_result is not None:
            if scan_result.startswith('SCAN_ERROR:'):
                logger.error("ClamAV scanner unavailable for file %s, user %s: %s", file_name, profile.user_id, scan_result)
                _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.MEDIUM)
                return JsonResponse({'error': 'File could not be scanned. The security scanner is temporarily unavailable. Please try again shortly.'}, status=503)
            _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.HIGH)
            return JsonResponse({'error': 'File rejected — malware detected'}, status=400)

        s3_key, s3_url = upload_to_s3(temp_path, file_name)
        if s3_key is None:
            logger.error("S3 upload returned None for file %s, user %s", file_name, profile.user_id)
            _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.HIGH)
            return JsonResponse({'error': 'Failed to upload file to S3. Please try again in a few minutes.'}, status=500)

        with open(temp_path, 'rb') as f:
            file_bytes = f.read()
        cache.set(f'file_bytes_{file_name}', file_bytes, timeout=3600)

        document = Document.objects.create(
            user=profile,
            org=org,
            dept=dept,
            original_filename=file_name,
            file_type=file_type,
            size_bytes=file_size,
            s3_key=s3_key,
            status=Document.Status.UPLOADED,
        )

        _record_audit_log(profile, "UPLOAD", "document", document.document_id, True, request, AuditLog.Severity.LOW)

        def event_stream():
            try:
                yield f"data: {json.dumps({'status': 'uploaded', 's3_url': s3_url, 'document_id': str(document.document_id)})}\n\n".encode('utf-8')
            except Exception as e:
                yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n".encode('utf-8')
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        streaming_started = True
        return StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
        )

    except Exception as e:
        logger.error("Unexpected error in upload_from_drive for file %s, user %s: %s", file_name, profile.user_id, str(e))
        return JsonResponse({'error': str(e)}, status=500)

    finally:
        if not streaming_started and os.path.exists(temp_path):
            os.unlink(temp_path)


# ──────────────────────────────────────────────
# OneDrive Upload — Phase 1 only
# ──────────────────────────────────────────────

@csrf_exempt
def upload_from_onedrive(request):
    """
    Frontend sends file_id + OAuth token; Django downloads via Microsoft Graph,
    scans, stores in S3, creates a Document record. No AI call.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    # ── Auth ──────────────────────────────────────────────────────────────────
    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error
    assert profile is not None

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    file_id      = (payload.get('file_id')      or '').strip()
    access_token = (payload.get('access_token') or '').strip()
    file_name    = (payload.get('file_name')    or '').strip()
    company_name = (payload.get('company_name') or '').strip()
    department   = (payload.get('department')   or '').strip()

    if not file_id or not access_token or not file_name:
        return JsonResponse({'error': 'Missing required fields'}, status=400)

    # Save the access token securely to AWS SSM
    user_id = request.user.id if request.user.is_authenticated else 'anonymous'
    save_oauth_token(user_id, 'onedrive', access_token)

    valid_exts = ('.pdf', '.docx', '.txt')
    if not file_name.lower().endswith(valid_exts):
        _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.LOW)
        return JsonResponse({'error': 'Unsupported file type'}, status=400)

    # ── Resolve Organisation & Department ─────────────────────────────────────
    org  = None
    dept = None
    if profile.role == UserProfile.Role.ADMIN:
        if not company_name:
            _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request)
            return JsonResponse({'error': 'Organisation name is required.'}, status=400)
        if not department:
            _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request)
            return JsonResponse({'error': 'Department is required for each file.'}, status=400)
        org, _  = Organization.objects.get_or_create(org_name=company_name)
        dept, _ = Department.objects.get_or_create(org=org, dept_name=department)
    else:
        org  = profile.org  # may be None for general users
        dept = None

    # ── Detect file type ──────────────────────────────────────────────────────
    ext = file_name.lower().rsplit('.', 1)[-1]
    file_type_map = {'pdf': 'PDF', 'docx': 'DOCX', 'txt': 'TXT'}
    file_type = file_type_map.get(ext)
    if not file_type:
        _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.LOW)
        return JsonResponse({'error': 'Unsupported file type. Only PDF, DOCX, and TXT are allowed.'}, status=400)

    # ── Download from Microsoft Graph ─────────────────────────────────────────
    download_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}/content"

    try:
        response = requests.get(
            download_url,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=60,
            stream=True,
        )
    except requests.exceptions.RequestException as e:
        _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.MEDIUM)
        return JsonResponse({'error': str(e)}, status=502)

    if response.status_code == 401:
        _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.LOW)
        return JsonResponse({'error': 'Invalid or expired token'}, status=401)
    if not response.ok:
        _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.MEDIUM)
        return JsonResponse({'error': f'Microsoft API error {response.status_code}'}, status=502)

    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as tmp:
        for chunk in response.iter_content(chunk_size=8192):
            tmp.write(chunk)
        temp_path = tmp.name

    try:
        # ── Size check ────────────────────────────────────────────────────────
        file_size = os.path.getsize(temp_path)
        if file_size > 50 * 1024 * 1024:
            _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.LOW)
            return JsonResponse({'error': 'File too large. Maximum size is 50 MB.'}, status=400)

        # ── Password protection check ─────────────────────────────────────────
        if is_password_protected(temp_path, file_name):
            _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.LOW)
            return JsonResponse({'error': 'File rejected — password protected files are not allowed'}, status=400)

        # ── Malware scan ──────────────────────────────────────────────────────
        scan_result = scan_file(temp_path)
        if scan_result is not None:
            if scan_result.startswith('SCAN_ERROR:'):
                _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.MEDIUM)
                return JsonResponse({'error': 'File could not be scanned. The security scanner is temporarily unavailable. Please try again shortly.'}, status=503)
            _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.HIGH)
            return JsonResponse({'error': 'File rejected — malware detected'}, status=400)

        # ── Upload to S3 ──────────────────────────────────────────────────────
        s3_key, s3_url = upload_to_s3(temp_path, file_name)
        if s3_key is None:
            logger.error("S3 upload returned None for file %s, user %s", file_name, profile.user_id)
            _record_audit_log(profile, "UPLOAD_REJECTED", "document", None, False, request, AuditLog.Severity.HIGH)
            return JsonResponse({'error': 'S3 upload failed. Please try again in a few minutes.'}, status=500)

        # ── Cache file bytes for analysis ─────────────────────────────────────
        with open(temp_path, 'rb') as f:
            cache.set(f'file_bytes_{file_name}', f.read(), timeout=3600)

        # ── Create Document record ────────────────────────────────────────────
        document = Document.objects.create(
            user=profile,
            org=org,
            dept=dept,
            original_filename=file_name,
            file_type=file_type,
            size_bytes=file_size,
            s3_key=s3_key,
            status=Document.Status.UPLOADED,
        )

        _record_audit_log(profile, "UPLOAD", "document", document.document_id, True, request, AuditLog.Severity.LOW)

        return JsonResponse({
            'status':      'uploaded',
            's3_url':      s3_url,
            'file_name':   file_name,
            'document_id': str(document.document_id),
        })

    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


# ──────────────────────────────────────────────
# Auth — Signup
# ──────────────────────────────────────────────

@csrf_exempt
def signup(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    full_name = (payload.get("name")     or "").strip()
    email     = (payload.get("email")    or "").strip().lower()
    password  = payload.get("password") or ""
    role_ui   = (payload.get("role")     or "").strip()

    if not full_name or not email or not password or not role_ui:
        return JsonResponse({"detail": "All fields are required"}, status=400)

    full_name = " ".join(full_name.split())

    if len(full_name) < 3:
        return JsonResponse({"detail": "Please enter your full name (first and last name)"}, status=400)
    
    if len(full_name) > 150:
        return JsonResponse({"detail": "Full name is too long."}, status=400)

    if any(ord(char) < 32 for char in full_name):
        return JsonResponse({"detail": "Invalid name format"}, status=400)

    if not re.match(r"^[A-Za-z'-]+(?:\s[A-Za-z'-]+)+$", full_name):
        return JsonResponse({"detail": "Please enter your full name (first and last name)"}, status=400)

    if any(len(part) < 2 for part in full_name.split()):
        return JsonResponse({"detail": "Please enter your full name (first and last name)"}, status=400)

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Please enter a valid email address."}, status=400)

    try:
        validate_password(password)
    except ValidationError as e:
        return JsonResponse({"detail": e.messages[0]}, status=400)

    role_map = {
        "General user":        UserProfile.Role.GENERAL,
        "Administrative user": UserProfile.Role.ADMIN,
    }
    role_db = role_map.get(role_ui)
    if not role_db:
        return JsonResponse({"detail": "Invalid role selected"}, status=400)

    if role_db == UserProfile.Role.ADMIN:
        is_valid_org, org_error = validate_org_email(email)
        if not is_valid_org:
            return JsonResponse({"detail": org_error}, status=400)

    if User.objects.filter(username=email).exists():
        return JsonResponse({"detail": "Email already registered"}, status=409)

    try:
        with transaction.atomic():
            auth_user = User.objects.create_user(username=email, email=email, password=password)
            UserProfile.objects.create(auth_user=auth_user, full_name=full_name, role=role_db)
    except IntegrityError:
        return JsonResponse({"detail": "Email already registered"}, status=409)
    except Exception:
        return JsonResponse({"detail": "Account creation failed. Please try again."}, status=500)

    return JsonResponse({"detail": "Account created successfully"}, status=201)


# ──────────────────────────────────────────────
# Auth — Login
# ──────────────────────────────────────────────

@csrf_exempt
def login(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    email    = (payload.get("email")    or "").strip().lower()
    password = payload.get("password") or ""

    if not email or not password:
        return JsonResponse({"detail": "Email and password are required"}, status=400)

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Please enter a valid email address."}, status=400)

    profile = None
    try:
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=email)
    except ObjectDoesNotExist:
        profile = None

    # Auto-unlock if lock period expired
    if profile and profile.locked_until and profile.locked_until <= timezone.now():
        profile.locked_until       = None
        profile.failed_login_count = 0
        profile.save(update_fields=["locked_until", "failed_login_count"])

    if profile and profile.deleted_at is not None:
        _record_login_attempt(profile, request, LoginHistory.Status.LOCKED, LoginHistory.Purpose.LOGIN)
        return JsonResponse({"detail": "Invalid email or password"}, status=401)

    if profile and profile.locked_until and profile.locked_until > timezone.now():
        _record_login_attempt(profile, request, LoginHistory.Status.LOCKED, LoginHistory.Purpose.LOGIN)
        return JsonResponse({"detail": "Account is temporarily locked. Please try again in 15 minutes."}, status=423)

    try:
        user = authenticate(username=email, password=password)
    except Exception:
        return JsonResponse({"detail": "Login failed. Please try again."}, status=500)

    if user is None:
        if profile:
            profile.failed_login_count += 1
            just_locked = False
            if profile.failed_login_count >= MAX_LOGIN_ATTEMPTS:
                profile.locked_until = timezone.now() + timedelta(minutes=LOCKOUT_MINUTES)
                just_locked = True
            profile.save(update_fields=["failed_login_count", "locked_until"])
            if just_locked:
                _record_login_attempt(profile, request, LoginHistory.Status.LOCKED, LoginHistory.Purpose.LOGIN)
                return JsonResponse(
                    {"detail": f"Too many attempts. Account locked for {LOCKOUT_MINUTES} minutes."},
                    status=423,
                )
            _record_login_attempt(profile, request, LoginHistory.Status.FAILED, LoginHistory.Purpose.LOGIN)
        return JsonResponse({"detail": "Invalid email or password"}, status=401)

    profile = UserProfile.objects.get(auth_user=user)

    # First login — require email verification OTP
    if not profile.is_verified:
        raw_otp = _generate_and_store_otp(profile, OtpVerification.Purpose.FIRST_LOGIN)
        if not send_otp_email(profile.auth_user.email, raw_otp, purpose="verification"):
            return JsonResponse({"detail": "Failed to send verification code. Please try again."}, status=500)
        _record_login_attempt(profile, request, LoginHistory.Status.PENDING_OTP, LoginHistory.Purpose.FIRST_LOGIN_OTP)
        return JsonResponse({"requires_otp": True, "detail": "A verification code has been sent to your email."}, status=200)

    # 2FA enabled — require OTP
    if profile.otp_is_enabled:
        raw_otp = _generate_and_store_otp(profile, OtpVerification.Purpose.LOGIN_2FA)
        if not send_otp_email(profile.auth_user.email, raw_otp, purpose="login"):
            return JsonResponse({"detail": "Failed to send verification code. Please try again."}, status=500)
        _record_login_attempt(profile, request, LoginHistory.Status.PENDING_OTP, LoginHistory.Purpose.LOGIN_2FA_OTP)
        return JsonResponse({"requires_otp": True, "detail": "A verification code has been sent to your email."}, status=200)

    # No 2FA — complete login immediately
    profile.failed_login_count = 0
    profile.locked_until       = None
    profile.last_login_at      = timezone.now()
    profile.save(update_fields=["failed_login_count", "locked_until", "last_login_at"])

    _record_login_attempt(profile, request, LoginHistory.Status.SUCCESS, LoginHistory.Purpose.LOGIN)

    return JsonResponse(
        {"detail": "Login successful", "email": user.email, "role": profile.role, "full_name": profile.full_name},
        status=200,
    )


# ──────────────────────────────────────────────
# Auth — Issue Session Token
# ──────────────────────────────────────────────

@csrf_exempt
def issue_session_token(request):
    """
    POST { "email": "user@example.com" }
    Returns { "token": "<signed-token>", "role": "..." }
    Called by frontend after successful login/OTP. Valid 24 hours.
    """
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    email = (payload.get("email") or "").strip().lower()
    if not email:
        return JsonResponse({"detail": "Email is required"}, status=400)

    try:
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=email)
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "User not found"}, status=404)

    if profile.deleted_at is not None:
        return JsonResponse({"detail": "Account not found"}, status=404)

    if not profile.is_verified:
        return JsonResponse({"detail": "Account not verified"}, status=403)

    token = signing.dumps({"uid": str(profile.user_id)}, salt="session-token")
    return JsonResponse({"token": token, "role": profile.role}, status=200)


# ──────────────────────────────────────────────
# Auth — Verify OTP (login / first login)
# ──────────────────────────────────────────────

@csrf_exempt
def verify_otp(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    email = (payload.get("email") or "").strip().lower()
    otp   = (payload.get("otp")   or "").strip()

    if not email or not otp:
        return JsonResponse({"detail": "Email and OTP are required"}, status=400)

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Please enter a valid email address."}, status=400)

    if not otp.isdigit() or len(otp) != 6:
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    invalid_otp_response = JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    try:
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=email)
    except ObjectDoesNotExist:
        return invalid_otp_response

    if profile.deleted_at is not None:
        return invalid_otp_response

    if profile.is_verified and not profile.otp_is_enabled:
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, LoginHistory.Purpose.OTP_SUBMISSION)
        return JsonResponse({"detail": "OTP not required for this account."}, status=400)

    otp_row = (
        OtpVerification.objects
        .filter(user=profile, purpose__in=[OtpVerification.Purpose.LOGIN_2FA, OtpVerification.Purpose.FIRST_LOGIN], used_at__isnull=True)
        .order_by("-created_at")
        .first()
    )

    # Brute-force guard — invalidate OTP after too many attempts
    if otp_row and otp_row.attempt_count >= MAX_OTP_ATTEMPTS:
        otp_row.used_at = timezone.now()
        otp_row.save(update_fields=["used_at"])
        return JsonResponse(
            {"detail": "Too many verification attempts. Please login again to request a new verification code."},
            status=401,
        )

    if otp_row:
        otp_purpose = (
            LoginHistory.Purpose.FIRST_LOGIN_OTP
            if otp_row.purpose == OtpVerification.Purpose.FIRST_LOGIN
            else LoginHistory.Purpose.LOGIN_2FA_OTP
        )
    else:
        otp_purpose = LoginHistory.Purpose.OTP_SUBMISSION

    if profile.locked_until and profile.locked_until > timezone.now():
        _record_login_attempt(profile, request, LoginHistory.Status.LOCKED, otp_purpose)
        return JsonResponse({"detail": "Account is temporarily locked. Try again later."}, status=423)

    if not otp_row:
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, otp_purpose)
        return invalid_otp_response

    if otp_row.expires_at <= timezone.now():
        otp_row.used_at = timezone.now()
        otp_row.save(update_fields=["used_at"])
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, otp_purpose)
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    incoming_hash = hashlib.sha256(otp.encode()).hexdigest()
    if incoming_hash != otp_row.otp_hash:
        otp_row.attempt_count += 1
        otp_row.save(update_fields=["attempt_count"])
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, otp_purpose)
        return invalid_otp_response

    otp_row.used_at = timezone.now()
    otp_row.save(update_fields=["used_at"])

    profile.failed_login_count = 0
    profile.locked_until       = None
    profile.last_login_at      = timezone.now()
    if otp_row.purpose == OtpVerification.Purpose.FIRST_LOGIN:
        profile.is_verified = True
    profile.save(update_fields=["failed_login_count", "locked_until", "last_login_at", "is_verified"])

    _record_login_attempt(profile, request, LoginHistory.Status.SUCCESS, otp_purpose)

    return JsonResponse(
        {"detail": "Login successful", "email": profile.auth_user.email, "role": profile.role, "full_name": profile.full_name},
        status=200,
    )


# ──────────────────────────────────────────────
# Auth — Password Reset
# ──────────────────────────────────────────────

@csrf_exempt
def request_password_reset(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    email = (payload.get("email") or "").strip().lower()
    if not email:
        return JsonResponse({"detail": "Email is required"}, status=400)

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Please enter a valid email address."}, status=400)

    try:
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=email)
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "A verification code has been sent to your email."}, status=200)

    if profile.deleted_at is not None:
        return JsonResponse({"detail": "A verification code has been sent to your email."}, status=200)

    OtpVerification.objects.filter(
        user=profile, purpose=OtpVerification.Purpose.RESET_PASSWORD, used_at__isnull=True
    ).update(used_at=timezone.now())

    raw_otp = _generate_and_store_otp(profile, OtpVerification.Purpose.RESET_PASSWORD)
    _record_login_attempt(profile, request, LoginHistory.Status.PENDING_OTP, LoginHistory.Purpose.RESET_PASSWORD_OTP)

    if not send_otp_email(profile.auth_user.email, raw_otp, purpose="password_reset"):
        return JsonResponse({"detail": "Failed to send verification code. Please try again."}, status=500)

    return JsonResponse({"detail": "A verification code has been sent to your email."}, status=200)


@csrf_exempt
def verify_reset_otp(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    email = (payload.get("email") or "").strip().lower()
    otp   = (payload.get("otp")   or "").strip()

    if not email or not otp:
        return JsonResponse({"detail": "Email and OTP are required"}, status=400)

    if not otp.isdigit() or len(otp) != 6:
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Please enter a valid email address."}, status=400)

    try:
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=email)
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    if profile.deleted_at is not None:
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    otp_row = (
        OtpVerification.objects
        .filter(user=profile, purpose=OtpVerification.Purpose.RESET_PASSWORD, used_at__isnull=True)
        .order_by("-created_at")
        .first()
    )

    if otp_row and otp_row.attempt_count >= MAX_OTP_ATTEMPTS:
        otp_row.used_at = timezone.now()
        otp_row.save(update_fields=["used_at"])
        return JsonResponse({"detail": "Too many verification attempts. Please request a new code."}, status=401)

    if not otp_row:
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, LoginHistory.Purpose.RESET_PASSWORD_OTP)
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    if otp_row.expires_at <= timezone.now():
        otp_row.used_at = timezone.now()
        otp_row.save(update_fields=["used_at"])
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, LoginHistory.Purpose.RESET_PASSWORD_OTP)
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    incoming_hash = hashlib.sha256(otp.encode()).hexdigest()
    if incoming_hash != otp_row.otp_hash:
        otp_row.attempt_count += 1
        otp_row.save(update_fields=["attempt_count"])
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, LoginHistory.Purpose.RESET_PASSWORD_OTP)
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    otp_row.used_at = timezone.now()
    otp_row.save(update_fields=["used_at"])
    _record_login_attempt(profile, request, LoginHistory.Status.SUCCESS, LoginHistory.Purpose.RESET_PASSWORD_OTP)

    reset_token = signing.dumps({"uid": str(profile.user_id), "purpose": "password_reset"}, salt="pwd-reset")
    return JsonResponse({"detail": "OTP verified.", "reset_token": reset_token}, status=200)


@csrf_exempt
def reset_password(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    reset_token  = (payload.get("reset_token")  or "").strip()
    new_password = payload.get("new_password") or ""

    if not reset_token or not new_password:
        return JsonResponse({"detail": "Reset token and new password are required"}, status=400)

    try:
        validate_password(new_password)
    except ValidationError as e:
        return JsonResponse({"detail": e.messages[0]}, status=400)

    try:
        data = signing.loads(reset_token, salt="pwd-reset", max_age=600)
    except SignatureExpired:
        return JsonResponse({"detail": "Reset token expired. Please request OTP again."}, status=401)
    except BadSignature:
        return JsonResponse({"detail": "Invalid reset token"}, status=401)

    if data.get("purpose") != "password_reset":
        return JsonResponse({"detail": "Invalid reset token"}, status=401)

    user_id = data.get("uid")
    if not user_id:
        return JsonResponse({"detail": "Invalid reset token"}, status=401)

    try:
        profile = UserProfile.objects.select_related("auth_user").get(user_id=user_id)
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "Invalid reset token"}, status=401)

    if profile.deleted_at is not None:
        return JsonResponse({"detail": "Invalid reset token"}, status=401)

    auth_user = profile.auth_user

    if auth_user.check_password(new_password):
        return JsonResponse({"detail": "Your new password cannot be the same as your current password."}, status=400)

    auth_user.set_password(new_password)
    auth_user.save(update_fields=["password"])

    _record_login_attempt(profile, request, LoginHistory.Status.SUCCESS, LoginHistory.Purpose.RESET_PASSWORD)

    OtpVerification.objects.filter(
        user=profile, purpose=OtpVerification.Purpose.RESET_PASSWORD, used_at__isnull=True
    ).update(used_at=timezone.now())

    profile.failed_login_count = 0
    profile.locked_until       = None
    profile.save(update_fields=["failed_login_count", "locked_until"])

    return JsonResponse({"detail": "Password reset successful"}, status=200)


# ──────────────────────────────────────────────
# Auth helpers (internal)
# ──────────────────────────────────────────────

def _record_login_attempt(profile: UserProfile, request, status: str, purpose: str) -> None:
    ip         = request.META.get("REMOTE_ADDR")
    user_agent = request.META.get("HTTP_USER_AGENT")
    LoginHistory.objects.create(
        user=profile, status=status, purpose=purpose,
        ip_address=ip, user_agent=user_agent,
    )


def _generate_and_store_otp(profile: UserProfile, purpose: str) -> str:
    raw_otp  = f"{random.randint(100000, 999999)}"
    otp_hash = hashlib.sha256(raw_otp.encode()).hexdigest()
    OtpVerification.objects.create(
        user=profile, otp_hash=otp_hash, purpose=purpose,
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    return raw_otp


def _record_audit_log(profile, action_type: str, target_type: str, target_id, success: bool, request=None, severity: str = AuditLog.Severity.LOW) -> None:
    ip = request.META.get("REMOTE_ADDR") if request else None
    AuditLog.objects.create(
        user=profile, action_type=action_type, target_type=target_type,
        target_id=target_id, success=success, severity=severity, ip_address=ip
    )


# ──────────────────────────────────────────────
# Profile — Get / Update
# ──────────────────────────────────────────────

@csrf_exempt
def get_profile(request):
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    email = (request.GET.get("email") or "").strip().lower()
    if not email:
        return JsonResponse({"detail": "Email is required"}, status=400)

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Please enter a valid email address."}, status=400)

    try:
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=email)
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "User not found"}, status=404)

    if profile.deleted_at is not None:
        return JsonResponse({"detail": "User not found"}, status=404)

    return JsonResponse(
        {
            "full_name":      profile.full_name,
            "email":          profile.auth_user.email,
            "role":           UserProfile.Role(profile.role).label,
            "otp_is_enabled": profile.otp_is_enabled,
        },
        status=200,
    )


@csrf_exempt
@require_http_methods(["PATCH"])
def update_profile(request):
    """PATCH /api/profile/update/ — Body: { "email": "...", "full_name": "New Name" }"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    email     = data.get("email", "").strip().lower()
    full_name = data.get("full_name", "").strip()

    if not email:
        return JsonResponse({"detail": "Email is required"}, status=400)
    if not full_name:
        return JsonResponse({"detail": "full_name is required"}, status=400)
    if len(full_name) < 3:
        return JsonResponse({"detail": "Name must be at least 3 characters"}, status=400)

    try:
        profile = UserProfile.objects.get(auth_user__username=email)
    except UserProfile.DoesNotExist:
        return JsonResponse({"detail": "User not found"}, status=404)

    if profile.deleted_at:
        return JsonResponse({"detail": "User not found"}, status=404)

    profile.full_name  = full_name
    profile.updated_at = timezone.now()
    profile.save(update_fields=["full_name", "updated_at"])

    return JsonResponse({"detail": "Profile updated", "full_name": profile.full_name}, status=200)


# ──────────────────────────────────────────────
# Profile — 2FA Setting
# ──────────────────────────────────────────────

@csrf_exempt
def update_twofa(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    email          = (payload.get("email") or "").strip().lower()
    otp_is_enabled = payload.get("otp_is_enabled")

    if not email or otp_is_enabled is None:
        return JsonResponse({"detail": "Email and otp_is_enabled are required"}, status=400)

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Please enter a valid email address."}, status=400)

    try:
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=email)
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "User not found"}, status=404)

    if profile.deleted_at is not None:
        return JsonResponse({"detail": "User not found"}, status=404)

    profile.otp_is_enabled = bool(otp_is_enabled)
    profile.updated_at     = timezone.now()
    profile.save(update_fields=["otp_is_enabled", "updated_at"])

    _record_login_attempt(profile, request, LoginHistory.Status.SUCCESS, LoginHistory.Purpose.UPDATE_2FA)

    return JsonResponse(
        {"detail": "Two-factor authentication setting updated successfully.", "otp_is_enabled": profile.otp_is_enabled},
        status=200,
    )


# ──────────────────────────────────────────────
# Profile — Email Change
# ──────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def request_email_change(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    current_email = data.get("current_email", "").strip().lower()
    new_email     = data.get("new_email", "").strip().lower()

    if not current_email or not new_email:
        return JsonResponse({"detail": "Current and new email required"}, status=400)
    if current_email == new_email:
        return JsonResponse({"detail": "New email must be different"}, status=400)

    try:
        validate_email(current_email)
        validate_email(new_email)
    except ValidationError:
        return JsonResponse({"detail": "Invalid email address"}, status=400)

    if User.objects.filter(username=new_email).exclude(username=current_email).exists():
        return JsonResponse({"detail": "New email already in use"}, status=409)

    try:
        profile = UserProfile.objects.get(auth_user__username=current_email)
    except UserProfile.DoesNotExist:
        return JsonResponse({"detail": "User not found"}, status=404)

    if profile.deleted_at:
        return JsonResponse({"detail": "User not found"}, status=404)

    raw_otp  = f"{random.randint(100000, 999999)}"
    otp_hash = hashlib.sha256(raw_otp.encode()).hexdigest()

    OtpVerification.objects.filter(
        user=profile, purpose=OtpVerification.Purpose.EMAIL_CHANGE, used_at__isnull=True
    ).update(used_at=timezone.now())

    OtpVerification.objects.create(
        user=profile, otp_hash=otp_hash,
        purpose=OtpVerification.Purpose.EMAIL_CHANGE,
        expires_at=timezone.now() + timedelta(minutes=10),
    )

    if not send_otp_email(new_email, raw_otp, purpose="email_change"):
        return JsonResponse({"detail": "Failed to send code"}, status=500)

    return JsonResponse({"detail": "Verification code sent to your new email"}, status=200)


@csrf_exempt
@require_http_methods(["POST"])
def verify_email_change(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    otp           = data.get("otp", "").strip()
    new_email     = data.get("new_email", "").strip().lower()
    current_email = data.get("current_email", "").strip().lower()

    if not otp or not new_email or not current_email:
        return JsonResponse({"detail": "OTP, new email, and current email are required"}, status=400)
    if not otp.isdigit() or len(otp) != 6:
        return JsonResponse({"detail": "Invalid OTP format"}, status=400)
    if current_email == new_email:
        return JsonResponse({"detail": "New email must be different"}, status=400)

    try:
        validate_email(new_email)
    except ValidationError:
        return JsonResponse({"detail": "Invalid new email"}, status=400)

    try:
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=current_email)
    except UserProfile.DoesNotExist:
        return JsonResponse({"detail": "User not found"}, status=404)

    if profile.deleted_at:
        return JsonResponse({"detail": "User not found"}, status=404)

    otp_row = OtpVerification.objects.filter(
        user=profile, purpose=OtpVerification.Purpose.EMAIL_CHANGE,
        used_at__isnull=True, expires_at__gt=timezone.now(),
    ).order_by("-created_at").first()

    if not otp_row:
        return JsonResponse({"detail": "No active verification code found for this account"}, status=400)

    incoming_hash = hashlib.sha256(otp.encode()).hexdigest()
    if incoming_hash != otp_row.otp_hash:
        otp_row.attempt_count += 1
        otp_row.save(update_fields=["attempt_count"])
        if otp_row.attempt_count >= 5:
            otp_row.used_at = timezone.now()
            otp_row.save(update_fields=["used_at"])
        return JsonResponse({"detail": "Invalid or expired code"}, status=400)

    if User.objects.filter(username=new_email).exclude(username=current_email).exists():
        return JsonResponse({"detail": "Email already taken"}, status=409)

    profile.auth_user.username = new_email
    profile.auth_user.email    = new_email
    profile.auth_user.save(update_fields=["username", "email"])

    otp_row.used_at = timezone.now()
    otp_row.save(update_fields=["used_at"])

    _record_login_attempt(profile, request, LoginHistory.Status.SUCCESS, LoginHistory.Purpose.UPDATE_EMAIL)

    return JsonResponse({"detail": "Email updated successfully", "new_email": new_email}, status=200)


# ──────────────────────────────────────────────
# Profile — Account Deletion
# ──────────────────────────────────────────────

@csrf_exempt
def request_delete_account(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    email = (payload.get("email") or "").strip().lower()
    if not email:
        return JsonResponse({"detail": "Email is required"}, status=400)

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Please enter a valid email address."}, status=400)

    try:
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=email)
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "A verification code has been sent to your email."}, status=200)

    if profile.deleted_at is not None:
        return JsonResponse({"detail": "A verification code has been sent to your email."}, status=200)

    OtpVerification.objects.filter(
        user=profile, purpose=OtpVerification.Purpose.DELETE_ACCOUNT, used_at__isnull=True
    ).update(used_at=timezone.now())

    raw_otp = _generate_and_store_otp(profile, OtpVerification.Purpose.DELETE_ACCOUNT)
    _record_login_attempt(profile, request, LoginHistory.Status.PENDING_OTP, LoginHistory.Purpose.DELETE_ACCOUNT_OTP)

    if not send_otp_email(profile.auth_user.email, raw_otp, purpose="delete_account"):
        return JsonResponse({"detail": "Failed to send verification code. Please try again."}, status=500)

    return JsonResponse({"detail": "A verification code has been sent to your email."}, status=200)


@csrf_exempt
def verify_delete_account_otp(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    email = (payload.get("email") or "").strip().lower()
    otp   = (payload.get("otp")   or "").strip()

    if not email or not otp:
        return JsonResponse({"detail": "Email and OTP are required"}, status=400)
    if not otp.isdigit() or len(otp) != 6:
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Please enter a valid email address."}, status=400)

    try:
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=email)
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    if profile.deleted_at is not None:
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    otp_row = (
        OtpVerification.objects
        .filter(user=profile, purpose=OtpVerification.Purpose.DELETE_ACCOUNT, used_at__isnull=True)
        .order_by("-created_at")
        .first()
    )

    if not otp_row:
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, LoginHistory.Purpose.DELETE_ACCOUNT_OTP)
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    if otp_row.attempt_count >= MAX_OTP_ATTEMPTS:
        otp_row.used_at = timezone.now()
        otp_row.save(update_fields=["used_at"])
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, LoginHistory.Purpose.DELETE_ACCOUNT_OTP)
        return JsonResponse({"detail": "Too many verification attempts. Please request a new code."}, status=401)

    if otp_row.expires_at <= timezone.now():
        otp_row.used_at = timezone.now()
        otp_row.save(update_fields=["used_at"])
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, LoginHistory.Purpose.DELETE_ACCOUNT_OTP)
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    incoming_hash = hashlib.sha256(otp.encode()).hexdigest()
    if incoming_hash != otp_row.otp_hash:
        otp_row.attempt_count += 1
        otp_row.save(update_fields=["attempt_count"])
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, LoginHistory.Purpose.DELETE_ACCOUNT_OTP)
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    otp_row.used_at = timezone.now()
    otp_row.save(update_fields=["used_at"])
    _record_login_attempt(profile, request, LoginHistory.Status.SUCCESS, LoginHistory.Purpose.DELETE_ACCOUNT_OTP)

    delete_token = signing.dumps(
        {"uid": str(profile.user_id), "purpose": "delete_account"}, salt="delete-account"
    )
    return JsonResponse({"detail": "OTP verified.", "delete_token": delete_token}, status=200)


@csrf_exempt
def delete_account(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    delete_token = (payload.get("delete_token") or "").strip()
    reason       = (payload.get("reason") or "").strip() or None

    if not delete_token:
        return JsonResponse({"detail": "delete_token is required"}, status=400)

    try:
        data = signing.loads(delete_token, salt="delete-account", max_age=600)
    except SignatureExpired:
        return JsonResponse({"detail": "Delete token expired. Please request OTP again."}, status=401)
    except BadSignature:
        return JsonResponse({"detail": "Invalid delete token"}, status=401)

    if data.get("purpose") != "delete_account":
        return JsonResponse({"detail": "Invalid delete token"}, status=401)

    user_id = data.get("uid")
    if not user_id:
        return JsonResponse({"detail": "Invalid delete token"}, status=401)

    try:
        profile = UserProfile.objects.select_related("auth_user").get(user_id=user_id)
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "Invalid delete token"}, status=401)

    if profile.deleted_at is not None:
        return JsonResponse({"detail": "Account already deleted"}, status=400)

    ip             = request.META.get("REMOTE_ADDR")
    original_email = profile.auth_user.email

    docs_qs        = Document.objects.filter(user=profile)
    doc_ids        = list(docs_qs.values_list("document_id", flat=True))
    s3_keys        = list(docs_qs.values_list("s3_key", flat=True))
    result_ids     = list(AnalysisResult.objects.filter(document_id__in=doc_ids).values_list("result_id", flat=True))
    report_s3_keys = list(Report.objects.filter(result_id__in=result_ids).values_list("report_s3_key", flat=True))

    erasure_summary = {
        "documents_erased":        docs_qs.count(),
        "s3_keys_deleted":         s3_keys,
        "analysis_results_erased": len(result_ids),
        "findings_erased":         Finding.objects.filter(result_id__in=result_ids).count(),
        "recommendations_erased":  Recommendation.objects.filter(result_id__in=result_ids).count(),
        "reports_erased":          Report.objects.filter(result_id__in=result_ids).count(),
        "report_s3_keys_deleted":  report_s3_keys,
    }

    deletion_record = DeletionRequest.objects.create(
        user=profile, user_email_snapshot=original_email,
        request_type=DeletionRequest.RequestType.ACCOUNT,
        status=DeletionRequest.Status.PENDING,
        reason=reason, erasure_summary=erasure_summary, ip_address=ip,
    )

    try:
        with transaction.atomic():
            now = timezone.now()
            profile.deleted_at         = now
            profile.otp_is_enabled     = False
            profile.locked_until       = None
            profile.failed_login_count = 0
            profile.updated_at         = now
            profile.save(update_fields=["deleted_at", "otp_is_enabled", "locked_until", "failed_login_count", "updated_at"])

            deleted_suffix = now.strftime("%Y%m%d%H%M%S")
            profile.auth_user.username  = f"deleted_{profile.user_id}_{deleted_suffix}"
            profile.auth_user.email     = f"deleted_{profile.user_id}_{deleted_suffix}@deleted.local"
            profile.auth_user.is_active = False
            profile.auth_user.save(update_fields=["username", "email", "is_active"])

            OtpVerification.objects.filter(
                user=profile, purpose=OtpVerification.Purpose.DELETE_ACCOUNT, used_at__isnull=True
            ).update(used_at=now)

            deletion_record.status       = DeletionRequest.Status.COMPLETED
            deletion_record.completed_at = now
            deletion_record.save(update_fields=["status", "completed_at"])

    except Exception:
        deletion_record.status = DeletionRequest.Status.FAILED
        deletion_record.save(update_fields=["status"])
        return JsonResponse({"detail": "Account deletion failed. Please try again."}, status=500)

    _record_audit_log(profile, "DELETE_ACCOUNT", "user_profile", profile.user_id, True, request, AuditLog.Severity.HIGH )
    return JsonResponse({"detail": "Account deleted successfully"}, status=200)


@csrf_exempt
@require_http_methods(["GET"])
def get_deletion_request_status(request):
    """GET /api/deletion-request/status/"""
    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error
    assert profile is not None

    latest = DeletionRequest.objects.filter(user=profile).order_by("-requested_at").first()
    if not latest:
        return JsonResponse({"detail": "No deletion request found."}, status=404)

    return JsonResponse(
        {
            "deletion_id":         str(latest.deletion_id),
            "request_type":        latest.request_type,
            "status":              latest.status,
            "user_email_snapshot": latest.user_email_snapshot,
            "reason":              latest.reason,
            "erasure_summary":     latest.erasure_summary,
            "requested_at":        latest.requested_at.isoformat(),
            "completed_at":        latest.completed_at.isoformat() if latest.completed_at else None,
            "ip_address":          latest.ip_address,
        },
        status=200,
    )


# ──────────────────────────────────────────────
# Analysis Results
# ──────────────────────────────────────────────

def _score_to_risk_level(score: int) -> str:
    if score >= 75:
        return AnalysisResult.RiskLevel.LOW
    if score >= 40:
        return AnalysisResult.RiskLevel.MEDIUM
    return AnalysisResult.RiskLevel.HIGH


def _serialize_analysis(analysis: AnalysisResult) -> dict:
    return {
        "result_id":         str(analysis.result_id),
        "document_id":       str(analysis.document_id),
        "original_filename": analysis.document.original_filename,
        "company_name":      analysis.document.org.org_name if analysis.document.org else "", 
        "department":        analysis.document.dept.dept_name if analysis.document.dept else "", 
        "compliance_score":  analysis.compliance_score,
        "risk_level":        analysis.risk_level,
        "summary":           analysis.summary,
        "raw_output":        analysis.raw_output,
        "created_at":        analysis.created_at.isoformat(),
        "compliance":        (analysis.raw_output or {}).get("compliance", {}),
        "recommendations":   (analysis.raw_output or {}).get("recommendations", {}),
    }


@csrf_exempt
@require_http_methods(["POST"])
def save_analysis_result(request):
    """POST /api/analysis/save/ — Persist AI result + findings atomically."""
    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON body"}, status=400)

    ai_result = data.get("result", {})
    doc_id    = (data.get("document_id") or "").strip()

    if not ai_result:
        return JsonResponse({"detail": "'result' is required and must not be empty"}, status=400)
    if not doc_id:
        return JsonResponse({"detail": "'document_id' is required"}, status=400)

    try:
        document = Document.objects.get(document_id=doc_id)
    except Document.DoesNotExist:
        return JsonResponse({"detail": "Document not found"}, status=404)

    is_owner = str(document.user_id) == str(profile.user_id)
    is_org_admin = (
        profile.role == UserProfile.Role.ADMIN
        and document.org_id is not None
        and str(document.org_id) == str(profile.org_id)
    )
    if not is_owner and not is_org_admin:
        return JsonResponse({"detail": "You do not have access to this document"}, status=403)

    raw_score        = ai_result.get("compliance", {}).get("compliance_score", 0)
    compliance_score = max(0, min(100, int(round(float(raw_score)))))
    risk_level       = _score_to_risk_level(compliance_score)
    summary          = ai_result.get("summary") or ai_result.get("recommendations", {}).get("top_action") or None

    with transaction.atomic():
        AnalysisResult.objects.filter(document=document).delete()
        analysis = AnalysisResult.objects.create(
            document=document, compliance_score=compliance_score,
            risk_level=risk_level, summary=summary, raw_output=ai_result,
        )

        findings_to_create = []
        for d in ai_result.get("compliance", {}).get("details", []):
            raw_status = (d.get("status") or "").lower().replace("-", "_")
            if raw_status in ("non_compliant", "partial"):
                findings_to_create.append(Finding(
                    result=analysis,
                    finding_type=Finding.FindingType.GAP,
                    title=(d.get("clause") or "Unknown Clause")[:200],
                    description=d.get("reasoning") or "",
                ))

        for r in ai_result.get("risk_assessment", []):
            if isinstance(r, str):
                title_text, desc_text = r[:200], ""
            else:
                title_text = (r.get("title") or r.get("risk") or "Risk Item")[:200]
                desc_text  = r.get("description") or r.get("detail") or ""
            findings_to_create.append(Finding(
                result=analysis, finding_type=Finding.FindingType.RISK,
                title=title_text, description=desc_text,
            ))

        if findings_to_create:
            Finding.objects.bulk_create(findings_to_create)

    if document.status != Document.Status.COMPLETED:
        document.status = Document.Status.COMPLETED
        document.save(update_fields=["status"])

    _record_audit_log(profile, "ANALYSE", "analysis_result", analysis.result_id, True, request, AuditLog.Severity.LOW)
    return JsonResponse(
        {"result_id": str(analysis.result_id), "compliance_score": compliance_score,
         "risk_level": risk_level, "findings_saved": len(findings_to_create)},
        status=201,
    )


@csrf_exempt
@require_http_methods(["GET"])
def get_latest_analysis(request):
    """GET /api/analysis/latest/"""
    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error

    try:
        analysis = (
            AnalysisResult.objects.select_related("document")
            .filter(document__user=profile).latest("created_at")
        )
    except AnalysisResult.DoesNotExist:
        return JsonResponse({"detail": "No analysis results found for this user"}, status=404)

    return JsonResponse(_serialize_analysis(analysis), status=200)


@csrf_exempt
@require_http_methods(["GET"])
def get_analysis_by_id(request, result_id):
    """GET /api/analysis/<result_id>/"""
    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error

    try:
        analysis = AnalysisResult.objects.select_related("document").get(result_id=result_id)
    except AnalysisResult.DoesNotExist:
        return JsonResponse({"detail": "Analysis result not found"}, status=404)

    is_owner = str(analysis.document.user_id) == str(profile.user_id)
    is_org_admin = (
        profile.role == UserProfile.Role.ADMIN
        and analysis.document.org_id is not None
        and str(analysis.document.org_id) == str(profile.org_id)
    )
    if not is_owner and not is_org_admin:
        return JsonResponse({"detail": "You do not have access to this result"}, status=403)

    return JsonResponse(_serialize_analysis(analysis), status=200)


@csrf_exempt
@require_http_methods(["GET"])
def get_analysis_history(request):
    """GET /api/analysis/history/"""
    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error

    now       = timezone.now()
    cutoff_7  = now - timedelta(days=7)
    cutoff_30 = now - timedelta(days=30)

    if profile.role == UserProfile.Role.ADMIN and profile.org_id:
        qs = AnalysisResult.objects.filter(document__user__org=profile.org)
    else:
        qs = AnalysisResult.objects.filter(document__user=profile)

    qs = qs.order_by("-created_at").values(
        "result_id", "compliance_score", "risk_level", "created_at", "document__original_filename",
    )

    def _summary(row):
        return {
            "result_id":        str(row["result_id"]),
            "display_name":     row["document__original_filename"],
            "compliance_score": row["compliance_score"],
            "risk_level":       row["risk_level"],
            "created_at":       row["created_at"].isoformat(),
        }

    last_7  = list(qs.filter(created_at__gte=cutoff_7))
    last_30 = list(qs.filter(created_at__gte=cutoff_30, created_at__lt=cutoff_7))

    return JsonResponse(
        {"last_7_days": [_summary(r) for r in last_7], "last_30_days": [_summary(r) for r in last_30]},
        status=200,
    )


@csrf_exempt
@require_http_methods(["GET"])
def get_findings_for_result(request, result_id):
    """GET /api/analysis/<result_id>/findings/"""
    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error

    try:
        analysis = AnalysisResult.objects.select_related("document").get(result_id=result_id)
    except AnalysisResult.DoesNotExist:
        return JsonResponse({"detail": "Analysis result not found"}, status=404)

    is_owner = str(analysis.document.user_id) == str(profile.user_id)
    is_org_admin = (
        profile.role == UserProfile.Role.ADMIN
        and analysis.document.org_id is not None
        and str(analysis.document.org_id) == str(profile.org_id)
    )
    if not is_owner and not is_org_admin:
        return JsonResponse({"detail": "You do not have access to this result"}, status=403)

    findings   = list(Finding.objects.filter(result=analysis).order_by("finding_type", "title").values("finding_id", "finding_type", "title", "description"))
    gap_count  = sum(1 for f in findings if f["finding_type"] == Finding.FindingType.GAP)
    risk_count = sum(1 for f in findings if f["finding_type"] == Finding.FindingType.RISK)

    return JsonResponse(
        {
            "result_id":  str(result_id),
            "total":      len(findings),
            "gap_count":  gap_count,
            "risk_count": risk_count,
            "findings": [
                {"finding_id": str(f["finding_id"]), "finding_type": f["finding_type"],
                 "title": f["title"], "description": f["description"]}
                for f in findings
            ],
        },
        status=200,
    )


# ──────────────────────────────────────────────
# Recommendations
# ──────────────────────────────────────────────

@csrf_exempt
def save_recommendations(request):
    """POST /api/recommendations/save/"""
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error
    assert profile is not None

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    result_id       = (payload.get("result_id") or "").strip()
    recommendations = payload.get("recommendations", [])

    if not result_id:
        return JsonResponse({"detail": "result_id is required"}, status=400)
    if not isinstance(recommendations, list) or len(recommendations) == 0:
        return JsonResponse({"detail": "A non-empty recommendations list is required"}, status=400)

    try:
        import uuid as uuid_module
        result_uuid = uuid_module.UUID(result_id)
    except ValueError:
        return JsonResponse({"detail": "Invalid result_id format"}, status=400)

    try:
        analysis_result = AnalysisResult.objects.get(result_id=result_uuid)
    except AnalysisResult.DoesNotExist:
        return JsonResponse({"detail": "Analysis result not found. Run analysis first."}, status=404)

    created = []
    for item in recommendations:
        recommendation_text = (item.get("recommendation_text") or "").strip()
        act_name            = (item.get("act_name") or "").strip()
        steps_to_achieve    = item.get("steps_to_achieve") or []
        section             = (item.get("section") or "").strip()
        status              = (item.get("status") or Recommendation.Status.MEDIUM).strip()

        if not recommendation_text or not act_name:
            continue

        valid_statuses = [s.value for s in Recommendation.Status]
        if status not in valid_statuses:
            status = Recommendation.Status.MEDIUM

        if not isinstance(steps_to_achieve, list):
            steps_to_achieve = []

        rec = Recommendation.objects.create(
            result=analysis_result,
            recommendation_text=recommendation_text,
            status=status,
            act_name=act_name,
            steps_to_achieve=steps_to_achieve,
            section=section,
        )
        created.append(str(rec.rec_id))

    return JsonResponse(
        {"detail": f"{len(created)} recommendation(s) saved successfully.", "result_id": str(result_uuid), "rec_ids": created},
        status=201,
    )


@csrf_exempt
def get_recommendations(request):
    """GET /api/recommendations/?result_id=<uuid>"""
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error
    assert profile is not None

    result_id = (request.GET.get("result_id") or "").strip()
    if not result_id:
        return JsonResponse({"detail": "result_id is required"}, status=400)

    try:
        analysis_result = AnalysisResult.objects.select_related("document").get(result_id=result_id)
    except AnalysisResult.DoesNotExist:
        return JsonResponse({"detail": "Analysis result not found"}, status=404)

    is_owner = str(analysis_result.document.user_id) == str(profile.user_id)
    is_org_admin = (
        profile.role == UserProfile.Role.ADMIN
        and analysis_result.document.org_id is not None
        and str(analysis_result.document.org_id) == str(profile.org_id)
    )
    if not is_owner and not is_org_admin:
        return JsonResponse({"detail": "You do not have access to these recommendations"}, status=403)

    recommendations = Recommendation.objects.filter(result=analysis_result).order_by("created_at").values(
        "rec_id", "recommendation_text", "status", "act_name", "steps_to_achieve", "section", "created_at",
    )

    return JsonResponse(
        {
            "result_id": result_id,
            "recommendations": [
                {**rec, "rec_id": str(rec["rec_id"]), "created_at": rec["created_at"].isoformat()}
                for rec in recommendations
            ],
        },
        status=200,
    )


# ──────────────────────────────────────────────
# Reports
# ──────────────────────────────────────────────

@csrf_exempt
def list_reports(request):
    """GET /api/reports/ — Last 7 / last 30 days, ordered by generated_at desc."""
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error

    now       = timezone.now()
    cutoff_7  = now - timedelta(days=7)
    cutoff_30 = now - timedelta(days=30)
    dept_ids_raw = (request.GET.get("dept_ids") or "").strip()
    dept_ids = [d.strip() for d in dept_ids_raw.split(",") if d.strip()] if dept_ids_raw else []

    if profile.role == UserProfile.Role.ADMIN:
        base_filter = (
            {"result__document__user__org": profile.org}
            if profile.org_id
            else {"result__document__user": profile}
        )
        qs = Report.objects.select_related(
            "result__document__org", "result__document__dept", "dept"
        ).filter(generated_at__gte=cutoff_30, **base_filter)
    else:
        qs = Report.objects.select_related(
            "result__document__org", "result__document__dept", "dept"
        ).filter(
            result__document__user=profile, generated_at__gte=cutoff_30,
        )

    qs = qs.order_by("-generated_at")

    def _get_effective_dept_id(r):
        """Report.dept_id if set, else fall back to the source document's dept_id."""
        if r.dept_id:
            return str(r.dept_id)
        if r.result and r.result.document and r.result.document.dept_id:
            return str(r.result.document.dept_id)
        return None

    def _serialize(r):
        snapshot     = r.report_snapshot or {}
        meta         = snapshot.get("metadata", {})
        company      = meta.get("company", "").strip()
        filename     = meta.get("file_analyzed", r.report_s3_key).strip()
        display_name = f"{company} — {filename}" if company else filename
        return {
            "report_id":    str(r.report_id),
            "display_name": display_name,
            "dept_id":      _get_effective_dept_id(r),
            "generated_at": r.generated_at.isoformat(),
            "expires_at":   r.expires_at.isoformat(),
        }

    def _matches_dept(r):
        """Return True if this report belongs to any of the selected dept_ids."""
        if not dept_ids:
            return True
        return _get_effective_dept_id(r) in dept_ids

    all_reports  = [r for r in qs if _matches_dept(r)]
    last_7_days  = [_serialize(r) for r in all_reports if r.generated_at >= cutoff_7]
    last_30_days = [_serialize(r) for r in all_reports if r.generated_at < cutoff_7]

    return JsonResponse({"last_7_days": last_7_days, "last_30_days": last_30_days}, status=200)

@csrf_exempt
def debug_reports_dept(request):
    """GET /api/debug-reports-dept/ — Temporary: shows dept data for all admin reports."""
    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error
    if profile.role != UserProfile.Role.ADMIN:
        return JsonResponse({"detail": "Admin only"}, status=403)

    base_filter = (
        {"result__document__user__org": profile.org}
        if profile.org_id
        else {"result__document__user": profile}
    )
    reports = Report.objects.select_related(
        "result__document__dept", "dept"
    ).filter(**base_filter)

    rows = []
    for r in reports:
        rows.append({
            "report_id":        str(r.report_id),
            "report_dept_id":   str(r.dept_id) if r.dept_id else None,
            "doc_dept_id":      str(r.result.document.dept_id) if r.result and r.result.document and r.result.document.dept_id else None,
            "doc_dept_name":    r.result.document.dept.dept_name if r.result and r.result.document and r.result.document.dept_id else None,
            "display_name":     r.report_s3_key,
        })
    return JsonResponse({"reports": rows}, status=200)

@csrf_exempt
def list_departments(request):
    """GET /api/departments/ — Returns departments for the admin's org. Admin only."""
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error

    if profile.role != UserProfile.Role.ADMIN:
        return JsonResponse({"detail": "Admin access required"}, status=403)

    base_filter = (
        {"documents__user__org": profile.org}
        if profile.org_id
        else {"documents__user": profile}
    )
    depts = Department.objects.filter(
        **base_filter
    ).distinct().order_by("dept_name").values("dept_id", "dept_name")

    # Group by dept_name — collect all dept_ids that share the same name.
    # The frontend uses dept_name as the filter key so all synonymous dept rows match.
    from collections import defaultdict
    name_to_ids = defaultdict(list)
    for d in depts:
        name_to_ids[d["dept_name"]].append(str(d["dept_id"]))

    departments = [
        {"dept_name": name, "dept_ids": ids}
        for name, ids in sorted(name_to_ids.items())
    ]
    return JsonResponse({"departments": departments}, status=200)


@csrf_exempt
def generate_report(request):
    """POST /api/reports/generate/"""
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error
    assert profile is not None

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    result_id       = (payload.get("result_id") or "").strip()
    report_snapshot = payload.get("report_snapshot")
    report_s3_key   = (payload.get("report_s3_key") or "").strip()
    file_size       = payload.get("file_size")
    expires_in_days = payload.get("expires_in_days", 30)
    dept_id = (payload.get("dept_id") or "").strip() or None

    if not result_id or not report_snapshot or not report_s3_key or file_size is None:
        return JsonResponse({"detail": "result_id, report_snapshot, report_s3_key and file_size are required"}, status=400)

    try:
        analysis_result = AnalysisResult.objects.get(result_id=result_id)
    except (AnalysisResult.DoesNotExist, Exception):
        return JsonResponse({"detail": "analysis_result not found"}, status=404)
    
    dept = None
    if dept_id:
        try:
            dept = Department.objects.get(dept_id=dept_id)
        except Department.DoesNotExist:
            return JsonResponse({"detail": "Department not found"}, status=404)

    try:
        report = Report.objects.create(
            result=analysis_result, report_snapshot=report_snapshot,
            report_s3_key=report_s3_key, file_size=int(file_size),
            expires_at=timezone.now() + timedelta(days=int(expires_in_days)),
            dept=dept,
        )
    except Exception as e:
        return JsonResponse({"detail": f"Failed to create report: {str(e)}"}, status=500)

    _record_audit_log(profile, "GENERATE_REPORT", "report", report.report_id, True, request, AuditLog.Severity.LOW)
    return JsonResponse(
        {"detail": "Report generated successfully", "report_id": str(report.report_id),
         "generated_at": report.generated_at.isoformat(), "expires_at": report.expires_at.isoformat()},
        status=201,
    )


@csrf_exempt
def get_report(request, report_id):
    """GET /api/reports/<report_id>/"""
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error
    assert profile is not None

    try:
        report = Report.objects.select_related("result__document", "dept").get(report_id=report_id)
    except Report.DoesNotExist:
        return JsonResponse({"detail": "Report not found"}, status=404)

    doc = report.result.document
    is_owner    = str(doc.user_id) == str(profile.user_id)
    is_org_admin = (
        profile.role == UserProfile.Role.ADMIN
        and doc.org_id is not None
        and str(doc.org_id) == str(profile.org_id)
    )
    if not is_owner and not is_org_admin:
        return JsonResponse({"detail": "You do not have access to this report"}, status=403)

    _record_audit_log(profile, "VIEW_REPORT", "report", report.report_id, True, request, AuditLog.Severity.LOW)
    return JsonResponse(
        {
            "report_id":       str(report.report_id),
            "result_id":       str(report.result.result_id),
            "dept_id":         str(report.dept_id) if report.dept_id else None,
            "report_snapshot": report.report_snapshot,
            "report_s3_key":   report.report_s3_key,
            "file_size":       report.file_size,
            "generated_at":    report.generated_at.isoformat(),
            "expires_at":      report.expires_at.isoformat(),
        },
        status=200,
    )


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_report(request, report_id):
    """DELETE /api/reports/<report_id>/"""
    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error

    try:
        report = Report.objects.select_related("result__document").get(report_id=report_id)
    except Report.DoesNotExist:
        return JsonResponse({"detail": "Report not found"}, status=404)

    doc = report.result.document
    is_owner    = str(doc.user_id) == str(profile.user_id)
    is_org_admin = (
        profile.role == UserProfile.Role.ADMIN
        and doc.org_id is not None
        and str(doc.org_id) == str(profile.org_id)
    )
    if not is_owner and not is_org_admin:
        return JsonResponse({"detail": "You do not have permission to delete this report"}, status=403)

    _record_audit_log(profile, "DELETE_REPORT", "report", report.report_id, True, request, AuditLog.Severity.MEDIUM)
    report.delete()
    return JsonResponse({"detail": "Report deleted"}, status=200)


@csrf_exempt
def download_report(request):
    """POST /api/download-report/ — Records a download event. Admin only."""
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error

    if profile.role != UserProfile.Role.ADMIN:
        return JsonResponse({"error": "Only administrative users can download reports"}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    report_id = (data.get("report_id") or "").strip()
    if not report_id:
        return JsonResponse({"error": "report_id is required"}, status=400)

    try:
        report = Report.objects.select_related("result__document__user__org").get(report_id=report_id)
    except Report.DoesNotExist:
        return JsonResponse({"error": "Report not found"}, status=404)

    doc = report.result.document
    is_owner    = str(doc.user_id) == str(profile.user_id)
    is_org_admin = profile.org_id is not None and str(doc.org_id) == str(profile.org_id)
    if not is_owner and not is_org_admin:
        return JsonResponse({"error": "You do not have access to this report"}, status=403)

    ReportDownload.objects.create(downloaded_by=profile, report_id=report_id)
    _record_audit_log(profile, "DOWNLOAD_REPORT", "report", report.report_id, True, request, AuditLog.Severity.MEDIUM)
    return JsonResponse({"message": "Download recorded"})


@csrf_exempt
def share_report(request):
    """POST /api/share-report/ — Creates a share token. Admin only."""
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=405)

    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error

    if profile.role != UserProfile.Role.ADMIN:
        return JsonResponse({"error": "Only administrative users can share reports"}, status=403)
    
    report_id = request.POST.get("report_id", "").strip()
    pdf_file  = request.FILES.get("pdf")

    if not report_id:
        return JsonResponse({"error": "report_id is required"}, status=400)
    if not pdf_file:
        return JsonResponse({"error": "pdf file is required"}, status=400)

    try:
        report = Report.objects.select_related("result__document__user__org").get(report_id=report_id)
    except Report.DoesNotExist:
        return JsonResponse({"error": "Report not found"}, status=404)

    doc = report.result.document
    is_owner    = str(doc.user_id) == str(profile.user_id)
    is_org_admin = profile.org_id is not None and str(doc.org_id) == str(profile.org_id)
    if not is_owner and not is_org_admin:
        return JsonResponse({"error": "You do not have access to this report"}, status=403)
    
    # Reuse existing active share if one exists
    existing_share = ReportShare.objects.filter(
        report=report, shared_by=profile, is_active=True, expires_at__gt=timezone.now()
    ).first()

    if existing_share:
        return JsonResponse({
            "message": "Report shared successfully",
            "share_url": existing_share.access_token
        })
    
    # Write PDF to temp file and upload to S3
    try:
        s3_key = f"shared-reports/{report_id}.pdf"

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            for chunk in pdf_file.chunks():
                tmp.write(chunk)
            temp_path = tmp.name

        try:
            s3 = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME,
            )

            s3.upload_file(
                temp_path,
                settings.AWS_SHARED_REPORTS_BUCKET_NAME,
                s3_key,
                ExtraArgs={'ContentType': 'application/pdf'}
            )

            # Generate pre-signed URL (7 days)
            presigned_url = s3.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': settings.AWS_SHARED_REPORTS_BUCKET_NAME,
                    'Key': s3_key,
                },
                ExpiresIn=604800  # 7 days in seconds
            )

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    except (BotoCoreError, ClientError) as e:
        logger.error("S3 upload failed for shared report %s: %s", report_id, str(e))
        return JsonResponse({"error": "Failed to upload report. Please try again."}, status=500)

    # Store pre-signed URL as access_token in ReportShare
    ReportShare.objects.create(
        report=report, shared_by=profile,
        shared_with_email=profile.auth_user.email,
        access_token=presigned_url, expires_at=timezone.now() + timedelta(days=7),
    )

    _record_audit_log(profile, "SHARE_REPORT", "report", report.report_id, True, request, AuditLog.Severity.MEDIUM)
    return JsonResponse({"message": "Report shared successfully", "share_url": presigned_url})


# ──────────────────────────────────────────────
# Admin Access Request
# ──────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def request_admin_access(request):
    """POST /api/admin-access/request/ — Body: { "org_email": "user@company.com" }"""
    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error
    assert profile is not None

    if profile.role == UserProfile.Role.ADMIN:
        return JsonResponse({"detail": "Your account already has administrative access."}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    org_email = (data.get("org_email") or "").strip().lower()
    if not org_email:
        return JsonResponse({"detail": "org_email is required"}, status=400)

    try:
        validate_email(org_email)
    except ValidationError:
        return JsonResponse({"detail": "Please enter a valid email address."}, status=400)

    is_valid_org, org_error = validate_org_email(org_email)
    if not is_valid_org:
        return JsonResponse({"detail": org_error}, status=400)

    existing = AdminAccessRequest.objects.filter(user=profile, status=AdminAccessRequest.Status.PENDING).first()
    if existing:
        return JsonResponse({"detail": "You already have a pending admin access request."}, status=409)

    OtpVerification.objects.filter(
        user=profile, purpose=OtpVerification.Purpose.ADMIN_REQUEST_VERIFY, used_at__isnull=True
    ).update(used_at=timezone.now())

    raw_otp = _generate_and_store_otp(profile, OtpVerification.Purpose.ADMIN_REQUEST_VERIFY)
    otp_row = OtpVerification.objects.filter(
        user=profile, purpose=OtpVerification.Purpose.ADMIN_REQUEST_VERIFY, used_at__isnull=True
    ).order_by("-created_at").first()

    access_request = AdminAccessRequest.objects.create(
        user=profile, verification_otp=otp_row, org_email=org_email,
        status=AdminAccessRequest.Status.PENDING,
    )

    if not send_otp_email(org_email, raw_otp, purpose="admin_access"):
        access_request.delete()
        return JsonResponse({"detail": "Failed to send verification code. Please try again."}, status=500)

    _record_audit_log(profile, "ADMIN_ACCESS_REQUEST", "admin_access_request", access_request.request_id, True, request, AuditLog.Severity.HIGH)
    return JsonResponse(
        {"detail": "A verification code has been sent to your organisation email.", "request_id": str(access_request.request_id)},
        status=201,
    )


@csrf_exempt
@require_http_methods(["POST"])
def verify_admin_access(request):
    """POST /api/admin-access/verify/ — Body: { "otp": "123456", "request_id": "..." }"""
    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    otp        = (data.get("otp")        or "").strip()
    request_id = (data.get("request_id") or "").strip()

    if not otp or not request_id:
        return JsonResponse({"detail": "otp and request_id are required"}, status=400)
    if not otp.isdigit() or len(otp) != 6:
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    try:
        access_request = AdminAccessRequest.objects.select_related("verification_otp").get(
            request_id=request_id, user=profile, status=AdminAccessRequest.Status.PENDING,
        )
    except AdminAccessRequest.DoesNotExist:
        return JsonResponse({"detail": "No pending request found with this ID"}, status=404)

    otp_row = access_request.verification_otp
    if not otp_row or otp_row.used_at is not None:
        return JsonResponse({"detail": "No valid OTP associated with this request"}, status=400)

    if otp_row.attempt_count >= MAX_OTP_ATTEMPTS:
        otp_row.used_at = timezone.now()
        otp_row.save(update_fields=["used_at"])
        access_request.status         = AdminAccessRequest.Status.REJECTED
        access_request.verified_at    = timezone.now()
        access_request.failure_reason = "Too many incorrect OTP attempts."
        access_request.save(update_fields=["status", "verified_at", "failure_reason"])
        return JsonResponse({"detail": "Too many verification attempts. Please submit a new request."}, status=401)

    if otp_row.expires_at <= timezone.now():
        otp_row.used_at = timezone.now()
        otp_row.save(update_fields=["used_at"])
        access_request.status         = AdminAccessRequest.Status.REJECTED
        access_request.verified_at    = timezone.now()
        access_request.failure_reason = "Verification code expired."
        access_request.save(update_fields=["status", "verified_at", "failure_reason"])
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    incoming_hash = hashlib.sha256(otp.encode()).hexdigest()
    if incoming_hash != otp_row.otp_hash:
        otp_row.attempt_count += 1
        otp_row.save(update_fields=["attempt_count"])
        return JsonResponse({"detail": "Invalid verification code"}, status=401)

    now = timezone.now()
    with transaction.atomic():
        otp_row.used_at = now
        otp_row.save(update_fields=["used_at"])
        access_request.status      = AdminAccessRequest.Status.APPROVED
        access_request.verified_at = now
        access_request.save(update_fields=["status", "verified_at"])
        profile.role       = UserProfile.Role.ADMIN
        profile.updated_at = now
        profile.save(update_fields=["role", "updated_at"])

    _record_audit_log(profile, "ADMIN_ACCESS_APPROVED", "admin_access_request", access_request.request_id, True, request, AuditLog.Severity.HIGH)
    return JsonResponse({"detail": "Administrative access granted successfully.", "role": profile.role}, status=200)


@csrf_exempt
@require_http_methods(["GET"])
def get_admin_access_status(request):
    """GET /api/admin-access/status/"""
    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error
    assert profile is not None

    latest = AdminAccessRequest.objects.filter(user=profile).order_by("-requested_at").first()
    if not latest:
        return JsonResponse({"detail": "No admin access request found."}, status=404)

    return JsonResponse(
        {
            "request_id":     str(latest.request_id),
            "status":         latest.status,
            "org_email":      latest.org_email,
            "requested_at":   latest.requested_at.isoformat(),
            "verified_at":    latest.verified_at.isoformat() if latest.verified_at else None,
            "failure_reason": latest.failure_reason,
        },
        status=200,
    )