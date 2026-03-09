from django.shortcuts import render
import requests
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.models import User
from django.db import transaction
from django.core.validators import validate_email
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.contrib.auth import authenticate
from django.utils import timezone
from datetime import timedelta
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.conf import settings
from django.core.mail import send_mail
import random
import hashlib
import json, time
import socket
import tempfile
import os
import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .models import UserProfile, LoginHistory, OtpVerification

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

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
    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        s3.upload_file(file_path, bucket_name, file_name)

        s3_url = f"https://{bucket_name}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{file_name}"
        return s3_url

    except (BotoCoreError, ClientError):
        return None


# ──────────────────────────────────────────────
# analyze_compliance — AWS checks first, then AI
# ──────────────────────────────────────────────

@csrf_exempt
def analyze_compliance(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    uploaded_file = request.FILES.get('document')
    company_name = request.POST.get('company_name', '')
    department = request.POST.get('department', '')

    if not uploaded_file:
        return JsonResponse({'error': 'No file provided'}, status=400)

    # Step 1 — Save file temporarily
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        for chunk in uploaded_file.chunks():
            temp_file.write(chunk)
        temp_path = temp_file.name

    try:
        # Step 2 — Check if password protected
        if is_password_protected(temp_path, uploaded_file.name):
            return JsonResponse(
                {'error': 'File rejected — password protected files are not allowed'},
                status=400
            )

        # Step 3 — Scan for malware
        scan_result = scan_file(temp_path)
        if scan_result is not None:
            return JsonResponse(
                {'error': 'File rejected — malware detected', 'detail': scan_result},
                status=400
            )

        # Step 4 — Upload clean file to S3
        s3_url = upload_to_s3(temp_path, uploaded_file.name)
        if s3_url is None:
            return JsonResponse({'error': 'Failed to upload file to S3'}, status=500)

        # Step 5 — Reset file pointer, then stream to AI with SSE
        uploaded_file.seek(0)

        def event_stream():
            yield f"data: {json.dumps({'status': 'uploaded', 's3_url': s3_url})}\n\n".encode('utf-8')
            time.sleep(2)

            try:
                files = {'file': (uploaded_file.name, uploaded_file.read(), uploaded_file.content_type)}
                data = {'company_name': company_name, 'department': department}

                yield f"data: {json.dumps({'status': 'analysing'})}\n\n".encode('utf-8')

                response = requests.post(
                    f"{AI_API_URL}/analyze",
                    files=files,
                    data=data,
                    timeout=300
                )
                result = response.json()

                yield f"data: {json.dumps({'status': 'analysed', 'result': result})}\n\n".encode('utf-8')

            except requests.exceptions.ConnectionError:
                yield f"data: {json.dumps({'status': 'error', 'message': 'AI Server is not running.'})}\n\n".encode('utf-8')
            except Exception as e:
                yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n".encode('utf-8')

        return StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
            }
        )

    finally:
        # Always clean up temp file
        if os.path.exists(temp_path):
            os.unlink(temp_path)


# ──────────────────────────────────────────────
# Delete file(s) from S3
# ──────────────────────────────────────────────

@csrf_exempt
def delete_file(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    file_name = data.get('file_name', '').strip()
    file_names = data.get('file_names', [])

    if file_name:
        file_names.append(file_name)

    if not file_names:
        return JsonResponse({'error': 'No file names provided'}, status=400)

    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        objects = [{'Key': name} for name in file_names]
        s3.delete_objects(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Delete={'Objects': objects}
        )
        return JsonResponse({'status': f'{len(file_names)} file(s) deleted from S3'})

    except (BotoCoreError, ClientError) as e:
        return JsonResponse({'error': f'Failed to delete file(s): {str(e)}'}, status=500)


# ──────────────────────────────────────────────
# Google Drive Upload — frontend sends file_id + OAuth token,
# Django downloads the file from Drive and runs the same pipeline
# ──────────────────────────────────────────────

@csrf_exempt
def upload_from_drive(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

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

    # Validate file extension (same rules as device uploads)
    valid_exts = ('.pdf', '.docx', '.txt')
    if not file_name.lower().endswith(valid_exts):
        return JsonResponse(
            {'error': f'"{file_name}" is not supported. Only PDF, DOCX and TXT files are allowed.'},
            status=400
        )

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
    # If True, the event_stream() generator owns temp file cleanup via its finally block.
    # If False (early validation failure or unexpected exception), we clean up here.
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

        # Step 5 — Malware scan (skips gracefully if ClamAV unavailable)
        scan_result = scan_file(temp_path)
        if scan_result is not None:
            return JsonResponse(
                {'error': 'File rejected — malware detected', 'detail': scan_result},
                status=400
            )

        # Step 6 — Upload to S3
        s3_url = upload_to_s3(temp_path, file_name)
        if s3_url is None:
            return JsonResponse({'error': 'Failed to upload file to S3'}, status=500)

        # Step 7 — Stream SSE status events back to frontend (same as device upload)
        def event_stream():
            yield f"data: {json.dumps({'status': 'uploaded', 's3_url': s3_url})}\n\n".encode('utf-8')
            time.sleep(2)

            try:
                with open(temp_path, 'rb') as f:
                    file_bytes = f.read()

                files = {'file': (file_name, file_bytes, _mime_type_for(file_name))}
                data  = {'company_name': company_name, 'department': department}

                yield f"data: {json.dumps({'status': 'analysing'})}\n\n".encode('utf-8')

                ai_response = requests.post(
                    f"{AI_API_URL}/analyze",
                    files=files,
                    data=data,
                    timeout=300
                )
                result = ai_response.json()

                yield f"data: {json.dumps({'status': 'analysed', 'result': result})}\n\n".encode('utf-8')

            except requests.exceptions.ConnectionError:
                yield f"data: {json.dumps({'status': 'error', 'message': 'AI Server is not running.'})}\n\n".encode('utf-8')
            except Exception as e:
                yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n".encode('utf-8')
            finally:
                # Streaming is done — clean up the temp file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        streaming_started = True
        return StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
            }
        )

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    finally:
        # Only clean up here if we never reached the streaming response.
        # If streaming started, event_stream()'s finally block owns the cleanup.
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

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Invalid email format"}, status=400)

    role_map = {
        "General user": UserProfile.Role.GENERAL,
        "Administrative user": UserProfile.Role.ADMIN,
    }

    role_db = role_map.get(role_ui)
    if not role_db:
        return JsonResponse({"detail": "Invalid role selected"}, status=400)

    if User.objects.filter(username=email).exists():
        return JsonResponse({"detail": "Email already registered"}, status=409)

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

    if not email or not password:
        return JsonResponse({"detail": "Email and password are required"}, status=400)

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
        return JsonResponse({"detail": "Invalid credentials"}, status=401)

    # Block locked accounts
    if profile and profile.locked_until and profile.locked_until > timezone.now():
        _record_login_attempt(profile, request, LoginHistory.Status.LOCKED, LoginHistory.Purpose.LOGIN)
        return JsonResponse({"detail": "Account is temporarily locked. Try again later."}, status=423)

    user = authenticate(username=email, password=password)

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

        return JsonResponse({"detail": "Invalid credentials"}, status=401)

    profile = UserProfile.objects.get(auth_user=user)

    # First login — require OTP verification
    if not profile.is_verified:
        raw_otp = _generate_and_store_otp(profile, OtpVerification.Purpose.FIRST_LOGIN)
        _send_otp_email(profile.auth_user.email, raw_otp)
        _record_login_attempt(profile, request, LoginHistory.Status.PENDING_OTP, LoginHistory.Purpose.FIRST_LOGIN_OTP)

        return JsonResponse(
            {"requires_otp": True, "detail": "OTP sent to your email (first login verification)."},
            status=200
        )

    # 2FA enabled — require OTP
    if profile.otp_is_enabled:
        raw_otp = _generate_and_store_otp(profile, OtpVerification.Purpose.LOGIN_2FA)
        _send_otp_email(profile.auth_user.email, raw_otp)
        _record_login_attempt(profile, request, LoginHistory.Status.PENDING_OTP, LoginHistory.Purpose.LOGIN_2FA_OTP)

        return JsonResponse(
            {"requires_otp": True, "detail": "OTP sent to your email."},
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
            "detail": "Login success",
            "email": user.email,
            "role": profile.role,
            "full_name": profile.full_name,
        },
        status=200
    )


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


def _send_otp_email(email: str, otp: str) -> None:
    """Send OTP to user via AWS SES (configured as Django email backend)."""
    try:
        send_mail(
            subject='Your CyberComply Verification Code',
            message=(
                f'Your OTP verification code is: {otp}\n\n'
                f'This code is valid for 5 minutes.\n\n'
                f'If you did not request this, please ignore this email.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
        )
    except Exception as e:
        # Log but don't crash — OTP is still stored in DB
        print(f"ERROR sending OTP email to {email}: {e}")


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

    if not otp.isdigit() or len(otp) != 6:
        return JsonResponse({"detail": "OTP must be exactly 6 digits"}, status=400)

    try:
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=email)
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "Invalid OTP"}, status=401)

    if profile.deleted_at is not None:
        return JsonResponse({"detail": "Invalid OTP"}, status=401)

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
        return JsonResponse({"detail": "Invalid OTP"}, status=401)

    if otp_row.expires_at <= timezone.now():
        otp_row.used_at = timezone.now()
        otp_row.save(update_fields=["used_at"])
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, otp_purpose)
        return JsonResponse({"detail": "OTP expired. Please login again."}, status=401)

    incoming_hash = hashlib.sha256(otp.encode()).hexdigest()
    if incoming_hash != otp_row.otp_hash:
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, otp_purpose)
        return JsonResponse({"detail": "Invalid OTP"}, status=401)

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
            "detail": "Login success",
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
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=email)
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "If the email exists, an OTP will be sent."}, status=200)

    if profile.deleted_at is not None:
        return JsonResponse({"detail": "If the email exists, an OTP will be sent."}, status=200)

    raw_otp = _generate_and_store_otp(profile, OtpVerification.Purpose.RESET_PASSWORD)
    _send_otp_email(profile.auth_user.email, raw_otp)

    return JsonResponse({"detail": "If the email exists, an OTP will be sent."}, status=200)


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
        return JsonResponse({"detail": "OTP must be exactly 6 digits"}, status=400)

    try:
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=email)
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "Invalid OTP"}, status=401)

    if profile.deleted_at is not None:
        return JsonResponse({"detail": "Invalid OTP"}, status=401)

    otp_row = (
        OtpVerification.objects
        .filter(user=profile, purpose=OtpVerification.Purpose.RESET_PASSWORD, used_at__isnull=True)
        .order_by("-created_at")
        .first()
    )

    if not otp_row:
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, LoginHistory.Purpose.RESET_PASSWORD_OTP)
        return JsonResponse({"detail": "Invalid OTP"}, status=401)

    if otp_row.expires_at <= timezone.now():
        otp_row.used_at = timezone.now()
        otp_row.save(update_fields=["used_at"])
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, LoginHistory.Purpose.RESET_PASSWORD_OTP)
        return JsonResponse({"detail": "OTP expired. Please request a new one."}, status=401)

    incoming_hash = hashlib.sha256(otp.encode()).hexdigest()
    if incoming_hash != otp_row.otp_hash:
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, LoginHistory.Purpose.RESET_PASSWORD_OTP)
        return JsonResponse({"detail": "Invalid OTP"}, status=401)

    otp_row.used_at = timezone.now()
    otp_row.save(update_fields=["used_at"])

    _record_login_attempt(profile, request, LoginHistory.Status.SUCCESS, LoginHistory.Purpose.RESET_PASSWORD_OTP)

    reset_token = signing.dumps({"uid": str(profile.user_id)}, salt="pwd-reset")
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
        return JsonResponse({"detail": "reset_token and new_password are required"}, status=400)

    try:
        data = signing.loads(reset_token, salt="pwd-reset", max_age=600)  # 10 mins
    except SignatureExpired:
        return JsonResponse({"detail": "Reset token expired. Please request OTP again."}, status=401)
    except BadSignature:
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
    auth_user.set_password(new_password)
    auth_user.save(update_fields=["password"])

    profile.failed_login_count = 0
    profile.locked_until = None
    profile.save(update_fields=["failed_login_count", "locked_until"])

    return JsonResponse({"detail": "Password reset successful"}, status=200)