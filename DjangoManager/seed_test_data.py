from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.models import User
from core.models import Organization, Department, UserProfile, OtpVerification, LoginHistory

now = timezone.now()

# =========================
# ORGANIZATION
# =========================
org1 = Organization.objects.create(
    org_name="Lanka FinTech (Pvt) Ltd"
)

org2 = Organization.objects.create(
    org_name="Serendib Health Systems PLC"
)

# =========================
# DEPARTMENT
# =========================
dept1 = Department.objects.create(
    org=org1,
    dept_name="Information Technology"
)

dept2 = Department.objects.create(
    org=org2,
    dept_name="Human Resources"
)

# =========================
# AUTH USER
# =========================
auth1 = User.objects.create_user(
    username="n.perera",
    email="n.perera@lankafintech.lk",
    password="SecurePass123!"
)

auth2 = User.objects.create_user(
    username="s.jayasinghe",
    email="s.jayasinghe@serendibhealth.lk",
    password="SecurePass123!"
)

# =========================
# USER PROFILE
# =========================
profile1 = UserProfile.objects.create(
    auth_user=auth1,
    org=org1,
    full_name="Nimal Perera",
    role=UserProfile.Role.ADMIN,
    is_verified=True,
    otp_is_enabled=True,
    failed_login_count=0,
    locked_until=None,
    last_login_at=now - timedelta(hours=2),
    deleted_at=None
)

profile2 = UserProfile.objects.create(
    auth_user=auth2,
    org=org2,
    full_name="Sahan Jayasinghe",
    role=UserProfile.Role.GENERAL,
    is_verified=False,
    otp_is_enabled=False,
    failed_login_count=3,
    locked_until=now + timedelta(minutes=15),
    last_login_at=now - timedelta(days=1),
    deleted_at=None
)

# =========================
# OTP VERIFICATION
# =========================
otp1 = OtpVerification.objects.create(
    user=profile1,
    otp_hash="pbkdf2_sha256$600000$AbCdEf123$XyZHashValueExample1",
    purpose=OtpVerification.Purpose.LOGIN_2FA,
    expires_at=now + timedelta(minutes=3),
    used_at=now
)

otp2 = OtpVerification.objects.create(
    user=profile2,
    otp_hash="pbkdf2_sha256$600000$GhIjKl456$XyZHashValueExample2",
    purpose=OtpVerification.Purpose.RESET_PASSWORD,
    expires_at=now + timedelta(minutes=3),
    used_at=None
)

# =========================
# LOGIN HISTORY
# =========================
login1 = LoginHistory.objects.create(
    user=profile1,
    status=LoginHistory.Status.SUCCESS,
    ip_address="203.143.27.18",
    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/121.0 Safari/537.36"
)

login2 = LoginHistory.objects.create(
    user=profile2,
    status=LoginHistory.Status.FAILED,
    ip_address="112.134.45.201",
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0 Safari/537.36"
)

print("Inserted complete sample data for all tables.")