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
    org = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, blank=True, related_name="users")
    full_name = models.CharField(max_length=150)
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
        FIRST_LOGIN = "FIRST_LOGIN", "FIRST_LOGIN"
        LOGIN_2FA = "LOGIN_2FA", "LOGIN_2FA"
        RESET_PASSWORD = "RESET_PASSWORD", "RESET_PASSWORD"
        DELETE_ACCOUNT = "DELETE_ACCOUNT", "DELETE_ACCOUNT"
        ADMIN_REQUEST_VERIFY = "ADMIN_REQUEST_VERIFY", "ADMIN_REQUEST_VERIFY"

    otp_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(UserProfile, on_delete=models.PROTECT, related_name="otps")
    otp_hash = models.CharField(max_length=255)
    attempt_count = models.IntegerField(default=0)
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
        LOCKED = "LOCKED", "LOCKED"
        PENDING_OTP = "PENDING_OTP", "PENDING_OTP"

    class Purpose(models.TextChoices):
        LOGIN = "LOGIN", "LOGIN"
        FIRST_LOGIN_OTP = "FIRST_LOGIN_OTP", "FIRST_LOGIN_OTP"
        LOGIN_2FA_OTP = "LOGIN_2FA_OTP", "LOGIN_2FA_OTP"
        RESET_PASSWORD_OTP = "RESET_PASSWORD_OTP", "RESET_PASSWORD_OTP"
        RESET_PASSWORD = "RESET_PASSWORD", "RESET_PASSWORD"
        DELETE_ACCOUNT_OTP = "DELETE_ACCOUNT_OTP", "DELETE_ACCOUNT_OTP"
        UPDATE_2FA = "UPDATE_2FA", "UPDATE_2FA"
        UPDATE_EMAIL = "UPDATE_EMAIL", "UPDATE_EMAIL"
        OTP_SUBMISSION = "OTP_SUBMISSION", "OTP_SUBMISSION"

    login_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(UserProfile, on_delete=models.PROTECT, related_name="login_history")
    attempt_time = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    purpose = models.CharField(max_length=30, choices=Purpose.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "login_history"

    def __str__(self):
        return f"{self.user} - {self.status}"


# =========================
# Table: document
# =========================
class Document(models.Model):
    class Status(models.TextChoices):
        UPLOADED = "UPLOADED", "Uploaded"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        DELETED = "DELETED", "Deleted"

    document_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="documents")
    org = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents")
    dept = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents")
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=20, choices=[("PDF", "PDF"), ("DOCX", "DOCX"), ("TXT", "TXT")])
    size_bytes = models.BigIntegerField(null=True, blank=True)
    s3_key = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADED)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "document"

    def __str__(self):
        return self.original_filename


# =========================
# Table: analysis_result
# =========================
class AnalysisResult(models.Model):
    result_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        db_table = "analysis_result"

    def __str__(self):
        return str(self.result_id)


# =========================
# Table: recommendations
# =========================
class Recommendation(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        DONE = "DONE", "Done"

    rec_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    result = models.ForeignKey(AnalysisResult, on_delete=models.CASCADE, related_name="recommendations")
    recommendation_text = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices)
    act_name = models.CharField(max_length=255)
    page_no = models.IntegerField()
    line_no = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "recommendations"

    def __str__(self):
        return f"{self.act_name} - {self.status}"


# =========================
# Table: reports
# =========================
class Report(models.Model):
    report_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    result = models.ForeignKey(AnalysisResult, on_delete=models.CASCADE, related_name="reports", db_column="result_id")
    report_snapshot = models.JSONField()
    report_s3_key = models.CharField(max_length=255)
    file_size = models.BigIntegerField()
    generated_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "reports"

    def __str__(self):
        return str(self.report_id)
