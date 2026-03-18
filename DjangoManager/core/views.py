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
from botocore.exceptions import BotoCoreError, ClientError

from .models import UserProfile, LoginHistory, OtpVerification, Document, Organization, Department

# ──────────────────────────────────────────────
# Security Configuration
# ──────────────────────────────────────────────

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
MAX_OTP_ATTEMPTS = 5

AI_API_URL = "http://127.0.0.1:5000/api"


# ──────────────────────────────────────────────
# Helper: home view
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
        return str(e)


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
            region_name=settings.AWS_S3_REGION_NAME
        )
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        s3.upload_file(file_path, bucket_name, file_name)

        s3_key = file_name
        s3_url = f"https://{bucket_name}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{file_name}"
        return s3_key, s3_url

    except (BotoCoreError, ClientError):
        return None, None


# ──────────────────────────────────────────────
# Auth helper — resolve UserProfile from the
# X-Session-Token header sent by home.html.
# Returns (profile, None) on success or
# (None, JsonResponse) on failure.
# ──────────────────────────────────────────────

def _get_profile_from_token(request) -> "tuple[UserProfile, None] | tuple[None, JsonResponse]":
    """
    Validates the signed session token from the Authorization: Bearer <token> header.
    This is the JWT-ready interface — when full JWT is implemented, only the
    signing/validation internals below change; all callers stay identical.

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
# Called immediately when the user selects a file
# from their device. Does NOT call the AI service.
# ──────────────────────────────────────────────

@csrf_exempt
def upload_file(request):
    """
    Receives a single file from the frontend, runs security checks, stores
    it in S3, and creates a Document record in the database.

    Requires a valid X-Session-Token header (issued by api/session-token/).
    The AI analysis step is intentionally absent — it is triggered separately
    by the Analyse button via analyze_compliance or analyze_batch.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    # ── Auth: resolve the logged-in user ──────────────────────────────────
    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error
    assert profile is not None  # guaranteed: auth_error is None only when profile is set

    uploaded_file = request.FILES.get('document')
    company_name  = request.POST.get('company_name', '').strip()
    department    = request.POST.get('department', '').strip()

    if not uploaded_file:
        return JsonResponse({'error': 'No file provided'}, status=400)

    # ── Resolve Organisation & Department ────────────────────────────────
    #
    # ADMINISTRATIVE_USER:
    #   - company_name is typed freely in the UI per upload session.
    #   - department is selected per file via the dept pill.
    #   - Both are required. The org/dept are get_or_created so admins can
    #     register new organisations on first upload without a separate step.
    #
    # GENERAL_USER:
    #   - No org name field or dept pill is shown in the UI.
    #   - We use the org already linked to their UserProfile (set by an admin).
    #   - If their profile has no org, we still allow the upload but store
    #     org/dept as NULL — the Document FK allows null for this case.
    #     (If you later make org/dept mandatory for all roles, add a guard here.)
    # ─────────────────────────────────────────────────────────────────────────
    org  = None
    dept = None

    if profile.role == UserProfile.Role.ADMIN:
        if not company_name:
            return JsonResponse({'error': 'Organisation name is required.'}, status=400)
        if not department:
            return JsonResponse({'error': 'Department is required for each file.'}, status=400)

        # get_or_create so admins can introduce new orgs on first upload
        org, _ = Organization.objects.get_or_create(org_name=company_name)

        # get_or_create dept within this org
        dept, _ = Department.objects.get_or_create(org=org, dept_name=department)

    else:
        # General user — use profile-linked org if available (informational only)
        org  = profile.org           # may be None — FK is nullable
        dept = None                  # no dept concept for general users

    # ── Detect file type ───────────────────────────────────────────────────
    ext = uploaded_file.name.lower().rsplit('.', 1)[-1]
    file_type_map = {'pdf': 'PDF', 'docx': 'DOCX', 'txt': 'TXT'}
    file_type = file_type_map.get(ext)
    if not file_type:
        return JsonResponse({'error': 'Unsupported file type. Only PDF, DOCX, and TXT are allowed.'}, status=400)

    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        for chunk in uploaded_file.chunks():
            temp_file.write(chunk)
        temp_path = temp_file.name

    try:
        if is_password_protected(temp_path, uploaded_file.name):
            return JsonResponse(
                {'error': 'File rejected — password protected files are not allowed'},
                status=400
            )

        scan_result = scan_file(temp_path)
        if scan_result is not None:
            return JsonResponse(
                {'error': 'File rejected — malware detected', 'detail': scan_result},
                status=400
            )

        s3_key, s3_url = upload_to_s3(temp_path, uploaded_file.name)
        if s3_key is None:
            return JsonResponse({'error': 'Failed to upload file to S3'}, status=500)

        # Keep the file bytes in the Django cache so analyze_compliance can
        # forward them directly to the AI without touching S3 again.
        with open(temp_path, 'rb') as f:
            file_bytes = f.read()
        cache.set(f'file_bytes_{uploaded_file.name}', file_bytes, timeout=3600)

        # ── Create Document record ─────────────────────────────────────────
        # org and dept are None for GENERAL_USER — the model FK fields allow null.
        document = Document.objects.create(
            user=profile,
            org=org,           # None for general users
            dept=dept,         # None for general users
            original_filename=uploaded_file.name,
            file_type=file_type,
            size_bytes=uploaded_file.size,
            s3_key=s3_key,
            status=Document.Status.UPLOADED,
        )

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
# Triggered by the Analyse button when exactly
# one file is ready.
# ──────────────────────────────────────────────

@csrf_exempt
def analyze_compliance(request):
    """
    Triggered by the Analyse button (single file).
    Reads file bytes from the Django cache (stored by upload_file) and forwards
    them to the AI service as multipart/form-data — identical to the original
    pipeline. Streams SSE events back to the frontend.

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

    # Retrieve the file bytes stored in cache by upload_file.
    # No S3 round-trip needed — the bytes are already in memory.
    file_bytes = cache.get(f'file_bytes_{file_name}')
    if file_bytes is None:
        return JsonResponse(
            {'error': f'File bytes for "{file_name}" not found in cache. Please re-upload.'},
            status=400
        )

    def event_stream():
        try:
            yield f"data: {json.dumps({'status': 'analysing'})}\n\n".encode('utf-8')

            # Forward to AI exactly as the original — multipart/form-data with raw bytes
            files = {'file': (file_name, file_bytes, _mime_type_for(file_name))}
            data  = {'company_name': company_name, 'department': department}

            response = requests.post(
                f"{AI_API_URL}/analyze",
                files=files,
                data=data,
                timeout=300
            )
            result = response.json()

            yield f"data: {json.dumps({'status': 'analysed', 'result': result})}\n\n".encode('utf-8')

            # Clean up cache entry once analysis is done
            cache.delete(f'file_bytes_{file_name}')

        except requests.exceptions.ConnectionError:
            yield f"data: {json.dumps({'status': 'error', 'message': 'AI Server is not running.'})}\n\n".encode('utf-8')
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n".encode('utf-8')

    return StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream',
        headers={
            'Cache-Control':     'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


# ──────────────────────────────────────────────
# Phase 2b — Analyse multiple files (batch)
# Triggered by the Analyse button when two or
# more files are ready.
# ──────────────────────────────────────────────

@csrf_exempt
def analyze_batch(request):
    """
    Receives a JSON body listing already-uploaded file names plus metadata,
    generates S3 pre-signed URLs for each, and forwards the batch to the AI
    service in a single request.

    Expected request body:
    {
        "company_name": "Acme Corp",
        "files": [
            {"file_name": "policy.pdf",  "department": "IT"},
            {"file_name": "report.docx", "department": "Finance"}
        ]
    }

    Response (success):  {"status": "analysed", "result": {...}}
    Response (error):    {"error": "..."}
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

    # Build multipart files list from cache — same bytes stored by upload_file
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
                status=400
            )

        multipart_files.append({
            'file_name':  file_name,
            'department': department,
            'file_bytes': file_bytes
        })

    try:
        # Forward each file as multipart to the AI batch endpoint
        files_payload = [
            ('files', (f['file_name'], f['file_bytes'], _mime_type_for(f['file_name'])))
            for f in multipart_files
        ]
        data_payload = {
            'company_name': company_name,
            'departments':  ','.join(f['department'] for f in multipart_files)
        }

        response = requests.post(
            f"{AI_API_URL}/analyze-batch",
            files=files_payload,
            data=data_payload,
            timeout=600
        )
        result = response.json()

        # Clean up cache entries for all analysed files
        for f in multipart_files:
            cache.delete(f'file_bytes_{f["file_name"]}')

        return JsonResponse({'status': 'analysed', 'result': result})

    except requests.exceptions.ConnectionError:
        return JsonResponse({'error': 'AI Server is not running.'}, status=503)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ──────────────────────────────────────────────
# Delete file(s) from S3
# ──────────────────────────────────────────────

@csrf_exempt
def delete_file(request):
    """
    Deletes one or more files.
    - Hard-deletes from S3 (existing behaviour).
    - Soft-deletes the corresponding Document record(s) in the database
      by setting deleted_at and status = DELETED.

    Requires a valid X-Session-Token header.
    Users may only soft-delete documents they own.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    # ── Auth ──────────────────────────────────────────────────────────────
    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error
    assert profile is not None  # guaranteed: auth_error is None only when profile is set

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    file_name  = data.get('file_name', '').strip()
    file_names = data.get('file_names', [])
    # document_id(s) from the frontend — preferred over filename for DB lookup
    document_id  = data.get('document_id', '').strip()
    document_ids = data.get('document_ids', [])

    if file_name:
        file_names.append(file_name)
    if document_id:
        document_ids.append(document_id)

    if not file_names and not document_ids:
        return JsonResponse({'error': 'No file names or document IDs provided'}, status=400)

    # ── Soft-delete Document records ──────────────────────────────────────
    now = timezone.now()

    if document_ids:
        # Preferred path: look up by UUID, enforce ownership
        docs_qs = Document.objects.filter(
            document_id__in=document_ids,
            deleted_at__isnull=True
        )
        # ADMIN can delete any doc in their org; GENERAL_USER only their own
        if profile.role != UserProfile.Role.ADMIN:
            docs_qs = docs_qs.filter(user=profile)
        docs_qs.update(status=Document.Status.DELETED, deleted_at=now)

    elif file_names:
        # Fallback path: look up by s3_key (= filename), enforce ownership
        docs_qs = Document.objects.filter(
            s3_key__in=file_names,
            deleted_at__isnull=True
        )
        if profile.role != UserProfile.Role.ADMIN:
            docs_qs = docs_qs.filter(user=profile)
        docs_qs.update(status=Document.Status.DELETED, deleted_at=now)

    # ── Hard-delete from S3 ───────────────────────────────────────────────
    # Determine the actual S3 keys to delete.
    # If document_ids were provided, retrieve their s3_keys.
    keys_to_delete = list(file_names)  # already have these
    if document_ids and not file_names:
        # Fetch s3_keys for the soft-deleted documents (already marked deleted above)
        keys_to_delete = list(
            Document.objects.filter(
                document_id__in=document_ids
            ).values_list('s3_key', flat=True)
        )

    if not keys_to_delete:
        return JsonResponse({'status': 'Document record(s) soft-deleted (no S3 keys to remove)'})

    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        objects = [{'Key': k} for k in keys_to_delete]
        s3.delete_objects(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Delete={'Objects': objects}
        )
        return JsonResponse({'status': f'{len(keys_to_delete)} file(s) deleted'})

    except (BotoCoreError, ClientError) as e:
        # S3 deletion failed but DB record is already soft-deleted — report the error
        # without rolling back the soft-delete (the record is correctly marked DELETED).
        return JsonResponse({'error': f'DB record soft-deleted but S3 deletion failed: {str(e)}'}, status=500)


# ──────────────────────────────────────────────
# Google Drive Upload — Phase 1 only
# Frontend sends file_id + OAuth token; Django
# downloads the file from Drive, scans it, and
# stores it in S3. Stops at 'uploaded' — AI
# analysis is triggered separately via the
# Analyse button (analyze_compliance / analyze_batch).
# ──────────────────────────────────────────────

@csrf_exempt
def upload_from_drive(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    # ── Auth: resolve the logged-in user ──────────────────────────────────
    profile, auth_error = _get_profile_from_token(request)
    if auth_error:
        return auth_error
    assert profile is not None  # guaranteed: auth_error is None only when profile is set

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
        return JsonResponse(
            {'error': f'"{file_name}" is not supported. Only PDF, DOCX and TXT files are allowed.'},
            status=400
        )

    # ── Resolve Organisation & Department (same rules as upload_file) ────
    org  = None
    dept = None

    if profile.role == UserProfile.Role.ADMIN:
        if not company_name:
            return JsonResponse({'error': 'Organisation name is required.'}, status=400)
        if not department:
            return JsonResponse({'error': 'Department is required for each file.'}, status=400)
        org, _  = Organization.objects.get_or_create(org_name=company_name)
        dept, _ = Department.objects.get_or_create(org=org, dept_name=department)
    else:
        org  = profile.org   # may be None
        dept = None

    # ── Detect file type ───────────────────────────────────────────────────
    ext = file_name.lower().rsplit('.', 1)[-1]
    file_type_map = {'pdf': 'PDF', 'docx': 'DOCX', 'txt': 'TXT'}
    file_type = file_type_map.get(ext, 'PDF')

    # Step 1 — Download the file from Google Drive using the OAuth token
    download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    try:
        drive_response = requests.get(
            download_url,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=60,
            stream=True
        )
    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': f'Failed to reach Google Drive: {str(e)}'}, status=502)

    if drive_response.status_code == 401:
        return JsonResponse({'error': 'Google access token is invalid or expired'}, status=401)
    if drive_response.status_code == 403:
        return JsonResponse({'error': 'Permission denied — cannot access this Google Drive file'}, status=403)
    if not drive_response.ok:
        return JsonResponse(
            {'error': f'Google Drive returned HTTP {drive_response.status_code}'},
            status=502
        )

    # Step 2 — Write downloaded content to a temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as tmp:
        for chunk in drive_response.iter_content(chunk_size=8192):
            tmp.write(chunk)
        temp_path = tmp.name

    # streaming_started tracks whether we handed off to StreamingHttpResponse.
    # If True, event_stream()'s finally block owns cleanup.
    # If False (early validation failure), we clean up here.
    streaming_started = False

    try:
        # Step 3 — Size check (50 MB limit)
        file_size = os.path.getsize(temp_path)
        if file_size > 50 * 1024 * 1024:
            return JsonResponse(
                {'error': f'"{file_name}" exceeds the 50 MB limit.'},
                status=400
            )

        # Step 4 — Password protection check
        if is_password_protected(temp_path, file_name):
            return JsonResponse(
                {'error': 'File rejected — password protected files are not allowed'},
                status=400
            )

        # Step 5 — Malware scan
        scan_result = scan_file(temp_path)
        if scan_result is not None:
            return JsonResponse(
                {'error': 'File rejected — malware detected', 'detail': scan_result},
                status=400
            )

        # Step 6 — Upload to S3
        s3_key, s3_url = upload_to_s3(temp_path, file_name)
        if s3_key is None:
            return JsonResponse({'error': 'Failed to upload file to S3'}, status=500)

        # Step 6b — Store file bytes in cache so analyze_compliance can forward
        #           them to the AI without another network round-trip.
        with open(temp_path, 'rb') as f:
            file_bytes = f.read()
        cache.set(f'file_bytes_{file_name}', file_bytes, timeout=3600)

        # Step 6c — Create Document record
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

        # Step 7 — Stream a single SSE 'uploaded' event back to the frontend.
        #          No AI call here — analysis is deferred to the Analyse button.
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
            headers={
                'Cache-Control':     'no-cache',
                'X-Accel-Buffering': 'no',
            }
        )

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    finally:
        if not streaming_started and os.path.exists(temp_path):
            os.unlink(temp_path)


def _mime_type_for(file_name):
    """Return the correct MIME type based on file extension."""
    ext = file_name.lower().split('.')[-1]
    return {
        'pdf':  'application/pdf',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'txt':  'text/plain',
    }.get(ext, 'application/octet-stream')


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

    full_name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    role_ui = (payload.get("role") or "").strip()

    if not full_name or not email or not password or not role_ui:
        return JsonResponse({"detail": "All fields are required"}, status=400)
    
    full_name = " ".join(full_name.split())

    if len(full_name) < 3:
        return JsonResponse({"detail": "Please enter your full name (first and last name)"}, status=400)

    full_name_pattern = r"^[A-Za-z'-]+(?:\s[A-Za-z'-]+)+$"
    if not re.match(full_name_pattern, full_name):
        return JsonResponse(
            {"detail": "Please enter your full name (first and last name)"},
            status=400
        ) 

    name_parts = full_name.split()
    if any(len(part) < 2 for part in name_parts):
        return JsonResponse(
            {"detail": "Please enter your full name (first and last name)"},
            status=400
        )

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Please enter a valid email address."}, status=400)
    
    try:
        validate_password(password)
    except ValidationError as e:
        return JsonResponse({"detail": e.messages[0]}, status=400)    

    role_map = {
        "General user": UserProfile.Role.GENERAL,
        "Administrative user": UserProfile.Role.ADMIN,
    }

    role_db = role_map.get(role_ui)
    if not role_db:
        return JsonResponse({"detail": "Invalid role selected"}, status=400)

    if User.objects.filter(username=email).exists():
        return JsonResponse({"detail": "Email already registered"}, status=409)

    # This ensures that if creating the UserProfile fails, the User record is also rolled back.
    try:
        with transaction.atomic():
            auth_user = User.objects.create_user(
                username=email,
                email=email,
                password=password
            )

            UserProfile.objects.create(
                auth_user=auth_user,
                full_name=full_name,
                role=role_db
            )

    # Handle duplicate creation race condition safely
    except IntegrityError:
        return JsonResponse({"detail": "Email already registered"}, status=409)

    # Handle unexpected server/database errors gracefully
    except Exception:
        return JsonResponse(
            {"detail": "Account creation failed. Please try again."},
            status=500
        )

    # Success response
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

    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    # Check required login fields
    if not email or not password:
        return JsonResponse({"detail": "Email and password are required"}, status=400)

    # Validate email format before attempting authentication
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Please enter a valid email address."}, status=400)

    profile = None
    try:
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=email)
    except ObjectDoesNotExist:
        profile = None

    # Auto-unlock if lock time expired
    if profile and profile.locked_until and profile.locked_until <= timezone.now():
        profile.locked_until = None
        profile.failed_login_count = 0
        profile.save(update_fields=["locked_until", "failed_login_count"])

    # Block soft-deleted users
    if profile and profile.deleted_at is not None:
        _record_login_attempt(profile, request, LoginHistory.Status.LOCKED, LoginHistory.Purpose.LOGIN)
        return JsonResponse({"detail": "Invalid email or password"}, status=401)

    # Block locked accounts
    if profile and profile.locked_until and profile.locked_until > timezone.now():
        _record_login_attempt(profile, request, LoginHistory.Status.LOCKED, LoginHistory.Purpose.LOGIN)
        return JsonResponse({"detail": "Account is temporarily locked. Please try again in 15 minutes."}, status=423)

    # Handle unexpected authentication/server errors gracefully
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
                    status=423
                )

            _record_login_attempt(profile, request, LoginHistory.Status.FAILED, LoginHistory.Purpose.LOGIN)

        return JsonResponse({"detail": "Invalid email or password"}, status=401)
    
    profile = UserProfile.objects.get(auth_user=user)

    # First login — require OTP verification
    if not profile.is_verified:
        raw_otp = _generate_and_store_otp(profile, OtpVerification.Purpose.FIRST_LOGIN)
    
        # Stop if OTP email sending failed
        if not send_otp_email(profile.auth_user.email, raw_otp, purpose="verification"):
            return JsonResponse(
                {"detail": "Failed to send verification code. Please try again."},
                status=500
            )

        _record_login_attempt(profile, request, LoginHistory.Status.PENDING_OTP, LoginHistory.Purpose.FIRST_LOGIN_OTP)

        return JsonResponse(
            {"requires_otp": True, "detail": "A verification code has been sent to your email."},
            status=200
        )

    # 2FA enabled — require OTP
    if profile.otp_is_enabled:
        raw_otp = _generate_and_store_otp(profile, OtpVerification.Purpose.LOGIN_2FA)

        # Stop if OTP email sending failed
        if not send_otp_email(profile.auth_user.email, raw_otp, purpose="login"):
            return JsonResponse(
                {"detail": "Failed to send verification code. Please try again."},
                status=500
            )

        _record_login_attempt(profile, request, LoginHistory.Status.PENDING_OTP, LoginHistory.Purpose.LOGIN_2FA_OTP)

        return JsonResponse(
            {"requires_otp": True, "detail": "A verification code has been sent to your email."},
            status=200
        )

    # No 2FA — complete login
    profile.failed_login_count = 0
    profile.locked_until = None
    profile.last_login_at = timezone.now()
    profile.save(update_fields=["failed_login_count", "locked_until", "last_login_at"])

    _record_login_attempt(profile, request, LoginHistory.Status.SUCCESS, LoginHistory.Purpose.LOGIN)

    return JsonResponse(
        {
            "detail": "Login successful",
            "email": user.email,
            "role": profile.role,
            "full_name": profile.full_name,
        },
        status=200
    )


# ──────────────────────────────────────────────
# Auth — Issue session token
# Called by the frontend immediately after a
# successful login (or OTP verification) to
# exchange the user's email for a signed token
# that home.html will store in localStorage and
# attach to every subsequent API request.
# ──────────────────────────────────────────────

@csrf_exempt
def issue_session_token(request):
    """
    POST { "email": "user@example.com" }
    Returns { "token": "<signed-token>" }

    The token is a Django-signed payload containing the user_id.
    It is valid for 24 hours (enforced in _get_profile_from_token).
    This endpoint should only be called after the login flow has already
    authenticated the user — it does NOT re-check the password.
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
        profile = UserProfile.objects.select_related("auth_user").get(
            auth_user__username=email
        )
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "User not found"}, status=404)

    if profile.deleted_at is not None:
        return JsonResponse({"detail": "Account not found"}, status=404)

    if not profile.is_verified:
        return JsonResponse({"detail": "Account not verified"}, status=403)

    token = signing.dumps(
        {"uid": str(profile.user_id)},
        salt="session-token"
    )

    return JsonResponse({
        "token": token,
        "role":  profile.role,
    }, status=200)


# ──────────────────────────────────────────────
# Auth helpers
# ──────────────────────────────────────────────

def _record_login_attempt(profile: UserProfile, request, status: str, purpose: str) -> None:
    ip = request.META.get("REMOTE_ADDR")
    user_agent = request.META.get("HTTP_USER_AGENT")
    LoginHistory.objects.create(
        user=profile,
        status=status,
        purpose=purpose,
        ip_address=ip,
        user_agent=user_agent
    )


def _generate_and_store_otp(profile: UserProfile, purpose: str) -> str:
    raw_otp = f"{random.randint(100000, 999999)}"
    otp_hash = hashlib.sha256(raw_otp.encode()).hexdigest()
    OtpVerification.objects.create(
        user=profile,
        otp_hash=otp_hash,
        purpose=purpose,
        expires_at=timezone.now() + timedelta(minutes=5)
    )
    return raw_otp


# def _send_otp_email(email: str, otp: str) -> bool:
#    """Send OTP to user via AWS SES (configured as Django email backend)."""
#    try:
#        send_mail(
#            subject='Your CyberComply Verification Code',
#            message=(
#                f'Your OTP verification code is: {otp}\n\n'
#                f'This code is valid for 5 minutes.\n\n'
#                f'If you did not request this, please ignore this email.'
#            ),
#            from_email=settings.DEFAULT_FROM_EMAIL,
#            recipient_list=[email],
#        )
#        return True
#    except Exception as e:
        # Log but don't crash — OTP is still stored in DB
#        print(f"ERROR sending OTP email to {email}: {e}")
#        return False


# ──────────────────────────────────────────────
# Auth — Verify OTP (login / first login)
# ──────────────────────────────────────────────

@csrf_exempt
def verify_otp(request):
    """
    Verifies OTP for first login verification or 2FA login.
    """
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    email = (payload.get("email") or "").strip().lower()
    otp = (payload.get("otp") or "").strip()

    if not email or not otp:
        return JsonResponse({"detail": "Email and OTP are required"}, status=400)
    
    # Validate email format before OTP verification
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Please enter a valid email address."}, status=400)    

    if not otp.isdigit() or len(otp) != 6:
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)
    
    # Reusable invalid OTP response to reduce repetition
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
        .filter(
            user=profile,
            purpose__in=[OtpVerification.Purpose.LOGIN_2FA, OtpVerification.Purpose.FIRST_LOGIN],
            used_at__isnull=True
        )
        .order_by("-created_at")
        .first()
    )

    # Limit OTP brute-force attempts
    if otp_row and otp_row.attempt_count >= MAX_OTP_ATTEMPTS:
        otp_row.used_at = timezone.now()
        otp_row.save(update_fields=["used_at"])
        return JsonResponse(
            {"detail": "Too many verification attempts. Please login again to request a new verification code."},
            status=401
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

    # Mark OTP used
    otp_row.used_at = timezone.now()
    otp_row.save(update_fields=["used_at"])

    profile.failed_login_count = 0
    profile.locked_until = None
    profile.last_login_at = timezone.now()

    if otp_row.purpose == OtpVerification.Purpose.FIRST_LOGIN:
        profile.is_verified = True

    profile.save(update_fields=["failed_login_count", "locked_until", "last_login_at", "is_verified"])

    _record_login_attempt(profile, request, LoginHistory.Status.SUCCESS, otp_purpose)

    return JsonResponse(
        {
            "detail": "Login successful",
            "email": profile.auth_user.email,
            "role": profile.role,
            "full_name": profile.full_name,
        },
        status=200
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

    # Invalidate previous reset OTPs
    OtpVerification.objects.filter(
        user=profile,
        purpose=OtpVerification.Purpose.RESET_PASSWORD,
        used_at__isnull=True
    ).update(used_at=timezone.now())

    raw_otp = _generate_and_store_otp(profile, OtpVerification.Purpose.RESET_PASSWORD)
    
    # Log password reset OTP request in login history
    _record_login_attempt(
        profile,
        request,
        LoginHistory.Status.PENDING_OTP,
        LoginHistory.Purpose.RESET_PASSWORD_OTP
    )

    # Stop if OTP email sending failed
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
    otp = (payload.get("otp") or "").strip()

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
        .filter(
            user=profile,
            purpose=OtpVerification.Purpose.RESET_PASSWORD,
            used_at__isnull=True
        )
        .order_by("-created_at")
        .first()
    )  

    # Limit OTP brute-force attempts
    if otp_row and otp_row.attempt_count >= MAX_OTP_ATTEMPTS:
        otp_row.used_at = timezone.now()
        otp_row.save(update_fields=["used_at"])
        return JsonResponse(
            {"detail": "Too many verification attempts. Please request a new code."},
            status=401
        )

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

    reset_token = signing.dumps(
        {"uid": str(profile.user_id), "purpose": "password_reset"},
        salt="pwd-reset"
    )
    return JsonResponse({"detail": "OTP verified.", "reset_token": reset_token}, status=200)


@csrf_exempt
def reset_password(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    reset_token = (payload.get("reset_token") or "").strip()
    new_password = payload.get("new_password") or ""

    if not reset_token or not new_password:
        return JsonResponse({"detail": "Reset token and new password are required"}, status=400)

    # Validate password strength
    try:
        validate_password(new_password)
    except ValidationError as e:
        return JsonResponse({"detail": e.messages[0]}, status=400)

    try:
        data = signing.loads(reset_token, salt="pwd-reset", max_age=600)  # 10 mins
    except SignatureExpired:
        return JsonResponse({"detail": "Reset token expired. Please request OTP again."}, status=401)
    except BadSignature:
        return JsonResponse({"detail": "Invalid reset token"}, status=401)

    # Ensure token purpose is correct
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

    # Prevent password reuse (new password same as current)
    if auth_user.check_password(new_password):
        return JsonResponse(
            {"detail": "Your new password cannot be the same as your current password."},
            status=400
        )

    # Set new password
    auth_user.set_password(new_password)
    auth_user.save(update_fields=["password"])

    # Log successful password reset
    _record_login_attempt(
        profile,
        request,
        LoginHistory.Status.SUCCESS,
        LoginHistory.Purpose.RESET_PASSWORD
    )

    # Invalidate any remaining reset OTPs
    OtpVerification.objects.filter(
        user=profile,
        purpose=OtpVerification.Purpose.RESET_PASSWORD,
        used_at__isnull=True
    ).update(used_at=timezone.now())

    profile.failed_login_count = 0
    profile.locked_until = None
    profile.save(update_fields=["failed_login_count", "locked_until"])

    return JsonResponse({"detail": "Password reset successful"}, status=200)

# ──────────────────────────────────────────────
# Profile — Get user profile details
# ──────────────────────────────────────────────

@csrf_exempt
def get_profile(request):
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    email = (request.GET.get("email") or "").strip().lower()

    if not email:
        return JsonResponse({"detail": "Email is required"}, status=400)

    # Validate email format
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Please enter a valid email address."}, status=400)

    # Fetch user profile
    try:
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=email)
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "User not found"}, status=404)

    # Prevent access to deleted accounts
    if profile.deleted_at is not None:
        return JsonResponse({"detail": "User not found"}, status=404)

    # Return profile data to frontend
    return JsonResponse(
        {
            "full_name": profile.full_name,
            "email": profile.auth_user.email,
            "role": UserProfile.Role(profile.role).label,
            "otp_is_enabled": profile.otp_is_enabled
        },
        status=200
    )


# ──────────────────────────────────────────────
# Profile — Update 2FA setting
# ──────────────────────────────────────────────

@csrf_exempt
def update_twofa(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    email = (payload.get("email") or "").strip().lower()
    otp_is_enabled = payload.get("otp_is_enabled")

    if not email or otp_is_enabled is None:
        return JsonResponse({"detail": "Email and otp_is_enabled are required"}, status=400)

    # Validate email format
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Please enter a valid email address."}, status=400)

    # Fetch user profile
    try:
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=email)
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "User not found"}, status=404)

    if profile.deleted_at is not None:
        return JsonResponse({"detail": "User not found"}, status=404)

    # Update 2FA preference
    profile.otp_is_enabled = bool(otp_is_enabled)
    profile.updated_at = timezone.now()
    profile.save(update_fields=["otp_is_enabled", "updated_at"])

    _record_login_attempt(
        profile,
        request,
        LoginHistory.Status.SUCCESS,
        LoginHistory.Purpose.UPDATE_2FA
    )

    return JsonResponse(
        {
            "detail": "Two-factor authentication setting updated successfully.",
            "otp_is_enabled": profile.otp_is_enabled
        },
        status=200
    )


# ──────────────────────────────────────────────
# Profile — Request delete account OTP
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

    # Validate email format
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Please enter a valid email address."}, status=400)

    # Return generic response if account does not exist
    try:
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=email)
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "A verification code has been sent to your email."}, status=200)

    if profile.deleted_at is not None:
        return JsonResponse({"detail": "A verification code has been sent to your email."}, status=200)

    # Invalidate previous delete-account OTPs
    OtpVerification.objects.filter(
        user=profile,
        purpose=OtpVerification.Purpose.DELETE_ACCOUNT,
        used_at__isnull=True
    ).update(used_at=timezone.now())

    # Generate and send new OTP
    raw_otp = _generate_and_store_otp(profile, OtpVerification.Purpose.DELETE_ACCOUNT)

    _record_login_attempt(
        profile,
        request,
        LoginHistory.Status.PENDING_OTP,
        LoginHistory.Purpose.DELETE_ACCOUNT_OTP
    )

    if not send_otp_email(profile.auth_user.email, raw_otp, purpose="delete_account"):
        return JsonResponse(
            {"detail": "Failed to send verification code. Please try again."},
            status=500
        )

    return JsonResponse({"detail": "A verification code has been sent to your email."}, status=200)


# ──────────────────────────────────────────────
# Profile — Verify delete account OTP
# ──────────────────────────────────────────────

@csrf_exempt
def verify_delete_account_otp(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    email = (payload.get("email") or "").strip().lower()
    otp = (payload.get("otp") or "").strip()

    if not email or not otp:
        return JsonResponse({"detail": "Email and OTP are required"}, status=400)

    if not otp.isdigit() or len(otp) != 6:
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    # Validate email format
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Please enter a valid email address."}, status=400)

    # Fetch user profile
    try:
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=email)
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    if profile.deleted_at is not None:
        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    # Get latest unused delete-account OTP
    otp_row = (
        OtpVerification.objects
        .filter(
            user=profile,
            purpose=OtpVerification.Purpose.DELETE_ACCOUNT,
            used_at__isnull=True
        )
        .order_by("-created_at")
        .first()
    )

    if not otp_row:

        _record_login_attempt(
            profile,
            request,
            LoginHistory.Status.FAILED,
            LoginHistory.Purpose.DELETE_ACCOUNT_OTP
        )

        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    # Limit brute-force attempts
    if otp_row.attempt_count >= MAX_OTP_ATTEMPTS:
        otp_row.used_at = timezone.now()
        otp_row.save(update_fields=["used_at"])

        _record_login_attempt(
            profile,
            request,
            LoginHistory.Status.FAILED,
            LoginHistory.Purpose.DELETE_ACCOUNT_OTP
        )

        return JsonResponse(
            {"detail": "Too many verification attempts. Please request a new code."},
            status=401
        )

    # Check OTP expiration
    if otp_row.expires_at <= timezone.now():
        otp_row.used_at = timezone.now()
        otp_row.save(update_fields=["used_at"])

        _record_login_attempt(
            profile,
            request,
            LoginHistory.Status.FAILED,
            LoginHistory.Purpose.DELETE_ACCOUNT_OTP
        )

        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    # Compare hashed OTP
    incoming_hash = hashlib.sha256(otp.encode()).hexdigest()
    if incoming_hash != otp_row.otp_hash:
        otp_row.attempt_count += 1
        otp_row.save(update_fields=["attempt_count"])

        _record_login_attempt(
            profile,
            request,
            LoginHistory.Status.FAILED,
            LoginHistory.Purpose.DELETE_ACCOUNT_OTP
        )

        return JsonResponse({"detail": "Invalid or expired verification code"}, status=401)

    # Mark OTP used
    otp_row.used_at = timezone.now()
    otp_row.save(update_fields=["used_at"])

    _record_login_attempt(
        profile,
        request,
        LoginHistory.Status.SUCCESS,
        LoginHistory.Purpose.DELETE_ACCOUNT_OTP
    )

    # Generate secure signed delete token
    delete_token = signing.dumps(
        {"uid": str(profile.user_id), "purpose": "delete_account"},
        salt="delete-account"
    )

    return JsonResponse(
        {"detail": "OTP verified.", "delete_token": delete_token},
        status=200
    )


# ──────────────────────────────────────────────
# Profile — Delete account
# ──────────────────────────────────────────────

@csrf_exempt
def delete_account(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    delete_token = (payload.get("delete_token") or "").strip()

    if not delete_token:
        return JsonResponse({"detail": "delete_token is required"}, status=400)

    # Validate signed delete token
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

    # Fetch user profile
    try:
        profile = UserProfile.objects.select_related("auth_user").get(user_id=user_id)
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "Invalid delete token"}, status=401)

    if profile.deleted_at is not None:
        return JsonResponse({"detail": "Account already deleted"}, status=400)

    # Soft delete account
    profile.deleted_at = timezone.now()
    profile.otp_is_enabled = False
    profile.locked_until = None
    profile.failed_login_count = 0
    profile.updated_at = timezone.now()
    profile.save(update_fields=[
        "deleted_at",
        "otp_is_enabled",
        "locked_until",
        "failed_login_count",
        "updated_at"
    ])

    # Disable account login immediately and free original email for future reuse
    deleted_suffix = timezone.now().strftime("%Y%m%d%H%M%S")
    profile.auth_user.username = f"deleted_{profile.user_id}_{deleted_suffix}"
    profile.auth_user.email = f"deleted_{profile.user_id}_{deleted_suffix}@deleted.local"
    profile.auth_user.is_active = False
    profile.auth_user.save(update_fields=["username", "email", "is_active"])

    # Invalidate remaining delete-account OTPs
    OtpVerification.objects.filter(
        user=profile,
        purpose=OtpVerification.Purpose.DELETE_ACCOUNT,
        used_at__isnull=True
    ).update(used_at=timezone.now())

    return JsonResponse({"detail": "Account deleted successfully"}, status=200)