from django.shortcuts import render

# Create your views here.
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from django.db import transaction
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate
from django.utils import timezone
from datetime import timedelta
from django.core.exceptions import ObjectDoesNotExist
import json
import random
import hashlib

from .models import UserProfile, LoginHistory, OtpVerification

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

AI_API_URL = "http://127.0.0.1:5000"

@csrf_exempt
def analyze_compliance(request):
    if request.method == 'POST':
        # Get file from request
        uploaded_file = request.FILES.get('document')
        company_name = request.POST.get('company_name', '')
        department = request.POST.get('department', '')
        
        # Forward to AI service
        files = {'file': uploaded_file}
        data = {
            'company_name': company_name,
            'department': department
        }
        
        response = requests.post(
            f"{AI_API_URL}/analyze",
            files=files,
            data=data
        )
        
        return JsonResponse(response.json())
    
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
        _record_login_attempt(profile, request, LoginHistory.Status.LOCKED)
        return JsonResponse({"detail": "Invalid credentials"}, status=401)

    # If account is temporarily locked, block login
    if profile and profile.locked_until and profile.locked_until > timezone.now():
        _record_login_attempt(profile, request, LoginHistory.Status.LOCKED)
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
                _record_login_attempt(profile, request, LoginHistory.Status.LOCKED)
                return JsonResponse(
                    {"detail": f"Too many attempts. Account locked for {LOCKOUT_MINUTES} minutes."},
                    status=423
                )

            _record_login_attempt(profile, request, LoginHistory.Status.FAILED)
            
        return JsonResponse({"detail": "Invalid credentials"}, status=401)
            
    # Success: reset failed login count, update last login
    profile =  UserProfile.objects.get(auth_user=user)

    # If 2FA enabled, generate OTP and require verification
    if profile.otp_is_enabled:

        raw_otp = _generate_and_store_otp(
            profile,
            OtpVerification.Purpose.LOGIN_2FA
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

    _record_login_attempt(profile, request, LoginHistory.Status.SUCCESS)

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

def _record_login_attempt(profile: UserProfile, request, status: str) -> None:
    """Helper: saves one row in login_history for each login attempt."""
    ip = request.META.get("REMOTE_ADDR")
    user_agent = request.META.get("HTTP_USER_AGENT")

    LoginHistory.objects.create(
        user=profile,
        status=status,
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

    # Block if currently locked
    if profile.locked_until and profile.locked_until > timezone.now():
        _record_login_attempt(profile, request, LoginHistory.Status.LOCKED)
        return JsonResponse({"detail": "Account is temporarily locked. Try again later."}, status=423)

    # Get latest unused OTP for LOGIN_2FA
    otp_row = (
        OtpVerification.objects
        .filter(
            user=profile,
            purpose=OtpVerification.Purpose.LOGIN_2FA,
            used_at__isnull=True
        )
        .order_by("-created_at")
        .first()
    )

    # No OTP found
    if not otp_row:
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED)
        return JsonResponse({"detail": "Invalid OTP"}, status=401)

    # OTP expired
    if otp_row.expires_at <= timezone.now():
        otp_row.used_at = timezone.now()                
        otp_row.save(update_fields=["used_at"])
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED)
        return JsonResponse({"detail": "OTP expired. Please login again."}, status=401)

    # Wrong OTP
    incoming_hash = hashlib.sha256(otp.encode()).hexdigest()
    if incoming_hash != otp_row.otp_hash:
        _record_login_attempt(profile, request, LoginHistory.Status.FAILED)
        return JsonResponse({"detail": "Invalid OTP"}, status=401)

    # Mark OTP used
    otp_row.used_at = timezone.now()
    otp_row.save(update_fields=["used_at"])

    # OTP success
    profile.failed_login_count = 0
    profile.locked_until = None
    profile.last_login_at = timezone.now()
    profile.save(update_fields=["failed_login_count", "locked_until", "last_login_at"])

    _record_login_attempt(profile, request, LoginHistory.Status.SUCCESS)

    return JsonResponse(
        {
            "detail": "Login success",
            "email": profile.auth_user.email,
            "role": profile.role,
            "full_name": profile.full_name,
        },
        status=200
    )   