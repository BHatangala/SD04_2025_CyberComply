from django.shortcuts import render
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse, StreamingHttpResponse
from django.contrib.auth.models import User
from django.db import transaction
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate
from django.utils import timezone
from datetime import timedelta
from django.core.exceptions import ObjectDoesNotExist
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
import random
import hashlib
import json, time

from .models import UserProfile, LoginHistory, OtpVerification

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

AI_API_URL = "http://127.0.0.1:5000/api"  # Change this if your Flask server runs on a different address or port

# 1. New view to display your home.html from the frontend folder
def home(request):
    return render(request, 'home.html')

# 2. Your existing logic to communicate with the Flask AI
@csrf_exempt
def analyze_compliance(request):
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST requests allowed"}, status=405)

    uploaded_file = request.FILES.get('document')
    company_name = request.POST.get('company_name', '')
    department = request.POST.get('department', '')

    def event_stream():
        # Stage 1: Django has received the file
        yield f"data: {json.dumps({'status': 'uploaded'})}\n\n".encode('utf-8')
        time.sleep(2)

        # Stage 2: Forward to Flask AI server
        try:
            files = {'file': (uploaded_file.name, uploaded_file.read(), uploaded_file.content_type)}
            data = {'company_name': company_name, 'department': department}

            # Stage 3: Request is now with the AI — notify frontend
            yield f"data: {json.dumps({'status': 'analysing'})}\n\n".encode('utf-8')

            response = requests.post(
                f"{AI_API_URL}/analyze",
                files=files,
                data=data,
                timeout=300  # 5 min timeout for large docs
            )
            result = response.json()

            # Stage 4: AI finished — send full result
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
            'X-Accel-Buffering': 'no',  # Disables Nginx buffering if used
        }
    )
    
@csrf_exempt
def signup(request):
    """
    API endpoint for user registration.
    Creates auth_user and corresponding UserProfile.
    """

    # Only allow POST requests
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    # Parse JSON request body
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    full_name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    role_ui = (payload.get("role") or "").strip()

    # Basic validation
    if not full_name or not email or not password or not role_ui:
        return JsonResponse({"detail": "All fields are required"}, status=400)

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"detail": "Invalid email format"}, status=400)

    # Map frontend role text to database enum
    role_map = {
        "General user": UserProfile.Role.GENERAL,
        "Administrative user": UserProfile.Role.ADMIN,
    }

    role_db = role_map.get(role_ui)
    if not role_db:
        return JsonResponse({"detail": "Invalid role selected"}, status=400)

    # Prevent duplicate registrations
    if User.objects.filter(username=email).exists():
        return JsonResponse({"detail": "Email already registered"}, status=409)

    # Create both records atomically
    with transaction.atomic():

        # Django automatically hashes the password
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

    return JsonResponse(
        {"detail": "Account created successfully"},
        status=201
    )  

@csrf_exempt
def login(request):
    """
    API endpoint for user authentication (login).
    Validates user credentials and records each login attempt in LoginHistory.
    """

    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    # Parse JSON request body
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not email or not password:
        return JsonResponse({"detail": "Email and password are required"}, status=400)

    # Find user profile (if not found, still return generic error)
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

    # If user exists but soft-deleted, block login
    if profile and profile.deleted_at is not None:
        _record_login_attempt(profile, request, LoginHistory.Status.LOCKED, LoginHistory.Purpose.LOGIN)
        return JsonResponse({"detail": "Invalid credentials"}, status=401)

    # If account is temporarily locked, block login
    if profile and profile.locked_until and profile.locked_until > timezone.now():
        _record_login_attempt(profile, request, LoginHistory.Status.LOCKED, LoginHistory.Purpose.LOGIN)
        return JsonResponse({"detail": "Account is temporarily locked. Try again later."}, status=423)

    # Authenticate using Django auth
    user = authenticate(username=email, password=password)

    if user is None:
        # Wrong password OR user not found
        if profile:
            profile.failed_login_count += 1

            # Lock the account if max attempts reached
            just_locked = False
            if profile.failed_login_count >= MAX_LOGIN_ATTEMPTS:
                profile.locked_until = timezone.now() + timedelta(minutes=LOCKOUT_MINUTES)
                just_locked = True

            profile.save(update_fields=["failed_login_count", "locked_until"])

            # Record history
            if just_locked:
                _record_login_attempt(profile, request, LoginHistory.Status.LOCKED, LoginHistory.Purpose.LOGIN)
                return JsonResponse(
                    {"detail": f"Too many attempts. Account locked for {LOCKOUT_MINUTES} minutes."},
                    status=423
                )

            _record_login_attempt(profile, request, LoginHistory.Status.FAILED, LoginHistory.Purpose.LOGIN)
            
        return JsonResponse({"detail": "Invalid credentials"}, status=401)
            
    # Success: get profile
    profile =  UserProfile.objects.get(auth_user=user)

    # Require OTP on first login
    if not profile.is_verified:
        raw_otp = _generate_and_store_otp(
            profile,
            OtpVerification.Purpose.FIRST_LOGIN
        )

        _record_login_attempt(
            profile,
            request,
            LoginHistory.Status.PENDING_OTP,
            LoginHistory.Purpose.FIRST_LOGIN_OTP
        )
    
        print(f"DEBUG FIRST LOGIN OTP for {profile.auth_user.email}: {raw_otp}")

        return JsonResponse(
            {
                "requires_otp": True,
                "detail": "OTP sent to your email (first login verification)."
            },
            status=200
        )

    # If 2FA enabled, generate OTP and require verification
    if profile.otp_is_enabled:
        raw_otp = _generate_and_store_otp(
            profile,
            OtpVerification.Purpose.LOGIN_2FA
        )

        _record_login_attempt(
            profile,
            request,
            LoginHistory.Status.PENDING_OTP,
            LoginHistory.Purpose.LOGIN_2FA_OTP
        )

        # TEMP: For backend testing only
        print(f"DEBUG OTP for {profile.auth_user.email}: {raw_otp}")

        return JsonResponse(
            {
                "requires_otp": True,
                "detail": "OTP sent to your email."
            },
            status=200
        )

    # If 2FA is NOT enabled, complete login normally
    profile.failed_login_count = 0
    profile.locked_until = None
    profile.last_login_at = timezone.now()
    profile.save(update_fields=["failed_login_count", "locked_until", "last_login_at"])

    _record_login_attempt(profile, request, LoginHistory.Status.SUCCESS, LoginHistory.Purpose.LOGIN)

    # Minimal response for frontend
    return JsonResponse(
        {
            "detail": "Login success",
            "email": user.email,
            "role": profile.role,
            "full_name": profile.full_name,
        },
        status=200
    )

def _record_login_attempt(profile: UserProfile, request, status: str, purpose: str) -> None:
    """Helper: saves one row in login_history for each login attempt."""
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
    """Generate 6-digit OTP, hash it, store in DB, return raw OTP."""

    raw_otp = f"{random.randint(100000, 999999)}"

    otp_hash = hashlib.sha256(raw_otp.encode()).hexdigest()

    OtpVerification.objects.create(
        user=profile,
        otp_hash=otp_hash,
        purpose=purpose,
        expires_at=timezone.now() + timedelta(minutes=5)
    )

    return raw_otp 

@csrf_exempt
def verify_otp(request):
    """
    API endpoint to verify OTP for login 2FA.
    Verifies the submitted OTP for login 2FA and completes authentication if valid.

    Logging rule:
    - If OTP record exists: log FIRST_LOGIN_OTP or LOGIN_2FA_OTP based on otp_row.purpose
    - If no OTP record exists: log OTP_SUBMISSION as a fallbacK
    """

    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    # Parse JSON request body
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

    # Find profile
    try:
        profile = UserProfile.objects.select_related("auth_user").get(auth_user__username=email)
    except ObjectDoesNotExist:
        return JsonResponse({"detail": "Invalid OTP"}, status=401)

    # Block if soft deleted
    if profile.deleted_at is not None:
        return JsonResponse({"detail": "Invalid OTP"}, status=401)
    
    # If user is already verified and 2FA is NOT enabled, OTP submission is not valid.
    if profile.is_verified and not profile.otp_is_enabled:
        _record_login_attempt(
            profile,
            request,
            LoginHistory.Status.FAILED,
            LoginHistory.Purpose.OTP_SUBMISSION
        )
        return JsonResponse({"detail": "OTP not required for this account."}, status=400)    

    # Get latest unused OTP for LOGIN_2FA
    otp_row = (
        OtpVerification.objects
        .filter(
            user=profile,
            purpose__in=[
                OtpVerification.Purpose.LOGIN_2FA,
                OtpVerification.Purpose.FIRST_LOGIN
            ],
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
        # Random/invalid/late OTP request where no OTP exists
        otp_purpose = LoginHistory.Purpose.OTP_SUBMISSION 

    # Block if currently locked
    if profile.locked_until and profile.locked_until > timezone.now():
        _record_login_attempt(profile, request, LoginHistory.Status.LOCKED, otp_purpose)
        return JsonResponse({"detail": "Account is temporarily locked. Try again later."}, status=423)    

    # No OTP found
    if not otp_row:
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, otp_purpose)
        return JsonResponse({"detail": "Invalid OTP"}, status=401)

    # OTP expired
    if otp_row.expires_at <= timezone.now():
        otp_row.used_at = timezone.now()                
        otp_row.save(update_fields=["used_at"])

        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, otp_purpose)

        return JsonResponse({"detail": "OTP expired. Please login again."}, status=401)

    # Wrong OTP
    incoming_hash = hashlib.sha256(otp.encode()).hexdigest()
    if incoming_hash != otp_row.otp_hash:
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, otp_purpose)
        return JsonResponse({"detail": "Invalid OTP"}, status=401)

    # Mark OTP used
    otp_row.used_at = timezone.now()
    otp_row.save(update_fields=["used_at"])

    # OTP success
    profile.failed_login_count = 0
    profile.locked_until = None
    profile.last_login_at = timezone.now()

    # Mark verified only if this OTP was for first login
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

@csrf_exempt
def request_password_reset(request):
    """
    Generates and stores a password reset OTP for the user (if exists).
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
        # Security: Do NOT reveal if email exists
        return JsonResponse(
            {"detail": "If the email exists, an OTP will be sent."},
            status=200
        )

    if profile.deleted_at is not None:
        return JsonResponse(
            {"detail": "If the email exists, an OTP will be sent."},
            status=200
        )

    # Generate OTP with RESET_PASSWORD purpose
    raw_otp = _generate_and_store_otp(
        profile,
        OtpVerification.Purpose.RESET_PASSWORD
    )

    # TEMP: For backend testing only
    print(f"DEBUG RESET OTP for {profile.auth_user.email}: {raw_otp}")

    return JsonResponse(
        {"detail": "If the email exists, an OTP will be sent."},
        status=200
    )

@csrf_exempt
def verify_reset_otp(request):
    """
    Verifies RESET_PASSWORD OTP and returns a short-lived reset token.
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

    # No OTP found
    if not otp_row:
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, LoginHistory.Purpose.RESET_PASSWORD_OTP)
        return JsonResponse({"detail": "Invalid OTP"}, status=401)

    # OTP expired
    if otp_row.expires_at <= timezone.now():
        otp_row.used_at = timezone.now()
        otp_row.save(update_fields=["used_at"])
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, LoginHistory.Purpose.RESET_PASSWORD_OTP)
        return JsonResponse({"detail": "OTP expired. Please request a new one."}, status=401)

    # Wrong OTP
    incoming_hash = hashlib.sha256(otp.encode()).hexdigest()
    if incoming_hash != otp_row.otp_hash:
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED, LoginHistory.Purpose.RESET_PASSWORD_OTP)
        return JsonResponse({"detail": "Invalid OTP"}, status=401)

    # Mark OTP used
    otp_row.used_at = timezone.now()
    otp_row.save(update_fields=["used_at"])

    _record_login_attempt(profile, request, LoginHistory.Status.SUCCESS, LoginHistory.Purpose.RESET_PASSWORD_OTP)

    # 10-min token
    reset_token = signing.dumps({"uid": str(profile.user_id)}, salt="pwd-reset")

    return JsonResponse({"detail": "OTP verified.", "reset_token": reset_token}, status=200)

@csrf_exempt
def reset_password(request):
    """
    Resets password using a verified reset token.
    """
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

    # clear lock
    profile.failed_login_count = 0
    profile.locked_until = None
    profile.save(update_fields=["failed_login_count", "locked_until"])

    return JsonResponse({"detail": "Password reset successful"}, status=200)