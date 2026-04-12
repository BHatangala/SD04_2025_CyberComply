import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

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
        EMAIL_CHANGE = "EMAIL_CHANGE", "EMAIL_CHANGE"

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
    """
    One row per compliance analysis run, linked 1-to-1 with the Document analysed.
    """

    class RiskLevel(models.TextChoices):
        LOW    = "LOW",    "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH   = "HIGH",   "High"

    result_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # OneToOneField enforces NOT NULL + UNIQUE per the schema spec
    document = models.OneToOneField(
        Document,
        on_delete=models.CASCADE,
        related_name="analysis_result",
        db_column="document_id",
    )

    compliance_score = models.IntegerField(default=0)
    risk_level       = models.CharField(
        max_length=10,
        choices=RiskLevel.choices,
        default=RiskLevel.MEDIUM,
    )
    summary    = models.TextField(null=True, blank=True)
    raw_output = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "analysis_result"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(compliance_score__gte=0) & models.Q(compliance_score__lte=100),
                name="compliance_score_range",
            ),
            models.CheckConstraint(
                check=models.Q(risk_level__in=["LOW", "MEDIUM", "HIGH"]),
                name="risk_level_valid",
            ),
        ]

    def __str__(self):
        return f"{self.document.original_filename} — {self.compliance_score}%"


# =========================
# Table: finding
# =========================
class Finding(models.Model):
    """
    One row per identified compliance gap or risk item within an AnalysisResult.
    finding_type='GAP'  — a clause that is not satisfied.
    finding_type='RISK' — a risk item derived from the AI risk assessment.
    """

    class FindingType(models.TextChoices):
        GAP  = "GAP",  "Gap"
        RISK = "RISK", "Risk"

    finding_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    result = models.ForeignKey(
        AnalysisResult,
        on_delete=models.CASCADE,
        related_name="findings",
        db_column="result_id",
    )

    finding_type = models.CharField(max_length=10, choices=FindingType.choices, default=FindingType.GAP)
    title        = models.CharField(max_length=200, default='')
    description  = models.TextField(default='')
    created_at   = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "finding"
        ordering = ["finding_type", "title"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(finding_type__in=["GAP", "RISK"]),
                name="finding_type_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["result", "finding_type"], name="finding_result_type_idx"),
        ]

    def __str__(self):
        return f"[{self.finding_type}] {self.title}"


# =========================
# Table: recommendations
# =========================
class Recommendation(models.Model):
    class Status(models.TextChoices):
        CRITICAL = "CRITICAL", "Critical"
        HIGH     = "HIGH",     "High"
        MEDIUM   = "MEDIUM",   "Medium"
        LOW      = "LOW",      "Low"

    rec_id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    result              = models.ForeignKey(AnalysisResult, on_delete=models.CASCADE, related_name="recommendations")
    recommendation_text = models.TextField()
    status              = models.CharField(max_length=10, choices=Status.choices, default=Status.MEDIUM)
    act_name            = models.CharField(max_length=255)
    steps_to_achieve    = models.JSONField(default=list)   # stores list of step strings
    section             = models.CharField(max_length=255, blank=True, default='')  # e.g. "Section 4 — Compliance with the Data Protection Obligations"
    created_at          = models.DateTimeField(auto_now_add=True)

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
    dept = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="reports")
    report_snapshot = models.JSONField()
    report_s3_key = models.CharField(max_length=255)
    file_size = models.BigIntegerField()
    generated_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "reports"

    def __str__(self):
        return str(self.report_id)
    

# =========================
# Table: audit_logs
# =========================
class AuditLog(models.Model):

    class Severity(models.TextChoices):
        LOW         = "LOW",        "Low"
        MEDIUM      = "MEDIUM",     "Medium"
        HIGH        = "HIGH",      "High"
        CRITICAL    = "CRITICAL",  "Critical"
    
    audit_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs")
    action_type = models.CharField(max_length=50)
    target_type = models.CharField(max_length=50)
    target_id = models.UUIDField(null=True, blank=True)
    success = models.BooleanField()
    severity    = models.CharField(max_length=10, choices=Severity.choices, default=Severity.LOW)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_logs"

    def __str__(self):
        return f"{self.user} - {self.action_type} - {self.target_type}"


# =========================
# Table: admin_access_request
# =========================
class AdminAccessRequest(models.Model):
    class Status(models.TextChoices):
        PENDING  = "PENDING",  "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
 
    request_id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user                = models.ForeignKey(
                            UserProfile,
                            on_delete=models.CASCADE,
                            related_name="admin_access_requests"
                          )
    verification_otp    = models.ForeignKey(
                            OtpVerification,
                            on_delete=models.SET_NULL,
                            null=True, blank=True,
                            related_name="+",
                            db_column="verification_otp_id"
                          )
    org_email           = models.CharField(max_length=255, db_column="org_email")
    status              = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requested_at        = models.DateTimeField(default=timezone.now, db_column="requested_at")
    verified_at         = models.DateTimeField(null=True, blank=True, db_column="verified_at")
    failure_reason      = models.TextField(null=True, blank=True, db_column="failure_reason")
 
    class Meta:
        db_table = "admin_access_request"
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "requested_at"]),
        ]
 
    def __str__(self):
        return f"{self.user} — {self.status} ({self.org_email})"
 
# =========================
# Table: report_downloads
# =========================
class ReportDownload(models.Model):
    download_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Which report was downloaded
    report_id = models.UUIDField()

    # Who downloaded
    downloaded_by = models.ForeignKey(
        UserProfile,
        on_delete=models.PROTECT,
        related_name="report_downloads"
    )

    downloaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "report_downloads"

    def __str__(self):
        return f"{self.downloaded_by} - {self.report_id}"


# =========================
# Table: deletion_request
# =========================
class DeletionRequest(models.Model):
    class RequestType(models.TextChoices):
        ACCOUNT   = "ACCOUNT",   "Account Deletion"
        DATA_ONLY = "DATA_ONLY", "Data Only"
 
    class Status(models.TextChoices):
        PENDING   = "PENDING",   "Pending"
        COMPLETED = "COMPLETED", "Completed"
        FAILED    = "FAILED",    "Failed"
 
    deletion_id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
 
    # SET_NULL so the erasure certificate row survives after the user row is gone
    user                = models.ForeignKey(
                            UserProfile,
                            on_delete=models.SET_NULL,
                            null=True, blank=True,
                            related_name="deletion_requests"
                          )
 
    # Snapshot of email at request time — once auth_user is anonymised this is
    # the only record that links the certificate back to the original identity
    user_email_snapshot = models.CharField(max_length=255)
 
    request_type        = models.CharField(
                            max_length=10,
                            choices=RequestType.choices,
                            default=RequestType.ACCOUNT
                          )
    status              = models.CharField(
                            max_length=10,
                            choices=Status.choices,
                            default=Status.PENDING
                          )
 
    # Optional reason provided by the user before confirming deletion
    reason              = models.TextField(null=True, blank=True)
 
    # JSON snapshot of exactly what was erased — counts + S3 keys
    # Example:
    # {
    #   "documents_erased": 4,
    #   "s3_keys_deleted": ["docs/policy.pdf", "docs/report.docx"],
    #   "analysis_results_erased": 4,
    #   "findings_erased": 23,
    #   "recommendations_erased": 11,
    #   "reports_erased": 4,
    #   "report_s3_keys_deleted": ["reports/fintech-iso27001.pdf"]
    # }
    erasure_summary     = models.JSONField(null=True, blank=True)
 
    requested_at        = models.DateTimeField(default=timezone.now)
    completed_at        = models.DateTimeField(null=True, blank=True)
 
    # IP at time of the verified deletion request
    ip_address          = models.GenericIPAddressField(null=True, blank=True)
 
    class Meta:
        db_table = "deletion_request"
        ordering = ["-requested_at"]
        indexes  = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "requested_at"]),
        ]
 
    def __str__(self):
        return f"{self.user_email_snapshot} — {self.request_type} — {self.status}"
    
# =========================
# Table: report_share
# =========================
class ReportShare(models.Model):

    share_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    report = models.ForeignKey(
        'Report',
        on_delete=models.CASCADE,
        related_name='shares'
    )

    shared_by = models.ForeignKey(
        'UserProfile',
        on_delete=models.CASCADE,
        related_name='shared_reports'
    )

    shared_with_email = models.EmailField()

    access_token = models.TextField(unique=True)

    expires_at = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'report_shares'