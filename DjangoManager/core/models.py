import uuid
from django.db import models
from django.contrib.auth.models import User

# Database Models

# =========================
# Table: organization
# =========================
class Organization(models.Model):
    org_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org_name = models.CharField(max_length=200, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "organization"

    def __str__(self):
        return self.org_name


# =========================
# Table: department
# =========================
class Department(models.Model):
    dept_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="departments")
    dept_name = models.CharField(max_length=150)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "department"
        constraints = [
            models.UniqueConstraint(fields=["org", "dept_name"], name="unique_dept_per_org")
        ]

    def __str__(self):
        return f"{self.org.org_name} - {self.dept_name}"


# =========================
# Table: user_profile
# =========================
class UserProfile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "ADMINISTRATIVE_USER", "Administrative User"
        GENERAL = "GENERAL_USER", "General User"

    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    auth_user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")

    org = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users"
    )

    full_name = models.CharField(max_length=150, null=True, blank=True)

    role = models.CharField(max_length=25, choices=Role.choices, default=Role.GENERAL)

    is_verified = models.BooleanField(default=False)
    otp_is_enabled = models.BooleanField(default=False)

    failed_login_count = models.IntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_profile"

    def __str__(self):
        return self.full_name if self.full_name else self.auth_user.username


# =========================
# Table: otp_verification
# =========================
class OtpVerification(models.Model):
    class Purpose(models.TextChoices):
        VERIFY_EMAIL = "VERIFY_EMAIL", "VERIFY_EMAIL"
        LOGIN_2FA = "LOGIN_2FA", "LOGIN_2FA"
        RESET_PASSWORD = "RESET_PASSWORD", "RESET_PASSWORD"
        DELETE_ACCOUNT = "DELETE_ACCOUNT", "DELETE_ACCOUNT"
        ADMIN_REQUEST_VERIFY = "ADMIN_REQUEST_VERIFY", "ADMIN_REQUEST_VERIFY"

    otp_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="otps")

    otp_hash = models.CharField(max_length=255)
    purpose = models.CharField(max_length=30, choices=Purpose.choices)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "otp_verification"

    def __str__(self):
        return f"{self.user} - {self.purpose}"


# =========================
# Table: login_history
# =========================
class LoginHistory(models.Model):
    class Status(models.TextChoices):
        SUCCESS = "SUCCESS", "SUCCESS"
        FAILED = "FAILED", "FAILED"

    login_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="login_history")

    attempt_time = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=Status.choices)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "login_history"

    def __str__(self):
        return f"{self.user} - {self.status}"