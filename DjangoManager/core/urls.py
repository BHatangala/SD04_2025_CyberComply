from django.urls import path
from . import views

# URL patterns for core application APIs
urlpatterns = [

    path('', views.home, name='home'),  # This makes home.html show at http://127.0.0.1:8000/ai/

    # ── Two-phase document pipeline ──
    #
    # Phase 1 — called immediately on file selection (device or Google Drive):
    #   Validates → malware scans → uploads to S3. No AI call.
    path('upload/', views.upload_file, name='upload_file'),

    # Phase 2a — called when the Analyse button is clicked (single file):
    #   Fetches file from S3 via pre-signed URL → streams to AI → SSE events.
    path('analyze/', views.analyze_compliance, name='analyze_compliance'),

    # Phase 2b — called when the Analyse button is clicked (multiple files):
    #   Fetches files from S3 via pre-signed URLs → batch to AI → JSON result.
    path('analyze-batch/', views.analyze_batch, name='analyze_batch'),

    # Google Drive upload — frontend sends file_id + OAuth token,
    # Django downloads & stores in S3 (phase 1 only, no AI call).
    path('upload-from-drive/', views.upload_from_drive, name='upload_from_drive'),

    # S3 file deletion (called by frontend × button)
    path('api/delete-file/', views.delete_file, name='delete_file'),

    # User registration endpoint
    path("api/signup/", views.signup, name="signup"),

    # User authentication (login) endpoint
    path("api/login/", views.login, name="login"),

    # Login 2FA OTP verification endpoint
    path("api/verify-otp/", views.verify_otp, name="verify_otp"),

    # Password reset OTP request endpoint
    path("api/request-password-reset/", views.request_password_reset, name="request_password_reset"),

    # Password reset OTP verification endpoint
    path("api/verify-reset-otp/", views.verify_reset_otp, name="verify_reset_otp"),

    # Password reset execution endpoint
    path("api/reset-password/", views.reset_password, name="reset_password"),

    # Fetch user profile details endpoint
    path("api/profile/", views.get_profile, name="get_profile"),

    # Profile update (name change)
    path("api/profile/update/", views.update_profile, name="update_profile"),

    # Email change endpoints
    path("api/request-email-change/", views.request_email_change, name="request_email_change"),
    path("api/verify-email-change/", views.verify_email_change, name="verify_email_change"),

    # Update 2FA preference endpoint
    path("api/profile/twofa/", views.update_twofa, name="update_twofa"),

    # Request delete account OTP endpoint
    path("api/request-delete-account/", views.request_delete_account, name="request_delete_account"),

    # Verify delete account OTP endpoint
    path("api/verify-delete-account-otp/", views.verify_delete_account_otp, name="verify_delete_account_otp"),

    # Delete user account endpoint
    path("api/delete-account/", views.delete_account, name="delete_account"),

    # Issue a signed session token after successful login
    path("api/session-token/", views.issue_session_token, name="issue_session_token"),

]