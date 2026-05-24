from django.urls import path
from . import views

urlpatterns = [

    # ── Core ──────────────────────────────────────────────────────────────
    path('', views.home, name='home'),

    # ── Two-phase document pipeline ───────────────────────────────────────
    # Phase 1: validate → malware scan → S3 (no AI call)
    path('upload/', views.upload_file, name='upload_file'),

    # Phase 2a: single file → SSE stream → AI → result
    path('analyze/', views.analyze_compliance, name='analyze_compliance'),
    # Phase 2b: multiple files → batch → AI → result
    path('analyze-batch/', views.analyze_batch, name='analyze_batch'),

    # ── Cloud Storage Uploads (Phase 1 only) ──────────────────────────────
    path('upload-from-drive/', views.upload_from_drive, name='upload_from_drive'),
    path('upload-from-onedrive/', views.upload_from_onedrive, name='upload_from_onedrive'),

    # ── S3 File Management ────────────────────────────────────────────────
    path('api/delete-file/', views.delete_file, name='delete_file'),

    # ── Authentication ────────────────────────────────────────────────────
    path("api/signup/", views.signup, name="signup"),
    path("api/login/", views.login, name="login"),
    path("api/verify-otp/", views.verify_otp, name="verify_otp"),
    path("api/session-token/", views.issue_session_token, name="issue_session_token"),

    # ── Password Reset ────────────────────────────────────────────────────
    path("api/request-password-reset/", views.request_password_reset, name="request_password_reset"),
    path("api/verify-reset-otp/", views.verify_reset_otp, name="verify_reset_otp"),
    path("api/reset-password/", views.reset_password, name="reset_password"),

    # ── User Profile ──────────────────────────────────────────────────────
    path("api/profile/", views.get_profile, name="get_profile"),
    path("api/profile/update/", views.update_profile, name="update_profile"),
    path("api/profile/twofa/", views.update_twofa, name="update_twofa"),
    path("api/request-email-change/", views.request_email_change, name="request_email_change"),
    path("api/verify-email-change/", views.verify_email_change, name="verify_email_change"),

    # ── Account Deletion ──────────────────────────────────────────────────
    path("api/request-delete-account/", views.request_delete_account, name="request_delete_account"),
    path("api/verify-delete-account-otp/", views.verify_delete_account_otp, name="verify_delete_account_otp"),
    path("api/delete-account/", views.delete_account, name="delete_account"),
    path("api/deletion-request/status/", views.get_deletion_request_status, name="get_deletion_request_status"),

    # ── Analysis Results ──────────────────────────────────────────────────
    path("api/analysis/save/", views.save_analysis_result, name="save_analysis_result"),
    path("api/analysis/latest/", views.get_latest_analysis, name="get_latest_analysis"),
    path("api/analysis/history/", views.get_analysis_history, name="get_analysis_history"),
    path("api/analysis/<uuid:result_id>/", views.get_analysis_by_id, name="get_analysis_by_id"),
    path("api/analysis/<uuid:result_id>/findings/", views.get_findings_for_result, name="get_findings_for_result"),
    path('api/analysis/org-comparison/', views.get_org_comparison),

    # ── Recommendations ───────────────────────────────────────────────────
    path("api/recommendations/save/", views.save_recommendations, name="save_recommendations"),
    path("api/recommendations/", views.get_recommendations, name="get_recommendations"),

    # ── Reports ───────────────────────────────────────────────────────────
    path("api/reports/", views.list_reports, name="list_reports"),
    path("api/departments/", views.list_departments, name="list_departments"),
    path("api/debug-reports-dept/", views.debug_reports_dept, name="debug_reports_dept"),
    path("api/reports/generate/", views.generate_report, name="generate_report"),
    path("api/reports/resolve-token/", views.resolve_report_token, name="resolve_report_token"),
    path("api/reports/<uuid:report_id>/", views.get_report, name="get_report"),
    path("api/reports/<uuid:report_id>/delete/", views.delete_report, name="delete_report"),
    path("api/download-report/", views.download_report, name="download_report"),
    path("api/share-report/", views.share_report, name="share_report"),
    path("api/client-error-log/", views.log_client_error, name="log_client_error"),

    # ── Admin Access ──────────────────────────────────────────────────────
    path("api/admin-access/request/", views.request_admin_access, name="request_admin_access"),
    path("api/admin-access/verify/", views.verify_admin_access, name="verify_admin_access"),
    path("api/admin-access/status/", views.get_admin_access_status, name="get_admin_access_status"),

    # ── Notifications ─────────────────────────────────────────────────────
    path("api/notifications/unread/", views.get_unread_notifications, name="get_unread_notifications"),
    path("api/notifications/mark-read/", views.mark_notifications_read, name="mark_notifications_read"),

    # ── Auth ──────────────────────────────────────────────────────────────
    path("api/logout/", views.logout, name="logout"),

    # ── Cloud Health ──────────────────────────────────────────────────────
    path("api/cloud-health/", views.cloud_health, name="cloud_health"),

]