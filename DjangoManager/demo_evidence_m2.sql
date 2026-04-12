-- ===================================================================
-- CyberComply Demo Evidence Script for Milestone 2 (Database Overview)
-- ===================================================================

\x on
\timing on

\echo ''
\echo ''
\echo '=============================='
\echo '1. ORGANIZATIONS'
\echo '=============================='
\echo 'Displays all registered organizations in the system.'
\echo ''

SELECT *
FROM organization;


\echo ''
\echo ''
\echo '=============================='
\echo '2. DEPARTMENTS'
\echo '=============================='
\echo 'Displays departments linked to organizations.'
\echo ''

SELECT *
FROM department;


\echo ''
\echo ''
\echo '=============================='
\echo '3. USERS (AUTHENTICATION)'
\echo '=============================='
\echo 'Stores login credentials using Django authentication.'
\echo ''

SELECT id, username AS email, email, is_active
FROM auth_user
ORDER BY id DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '4. USER PROFILES'
\echo '=============================='
\echo 'Stores extended user details including role and security attributes.'
\echo ''

SELECT user_id, auth_user_id, full_name, role, is_verified,
       otp_is_enabled, failed_login_count, locked_until,
       last_login_at, deleted_at, org_id
FROM user_profile
ORDER BY updated_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '5. OTP VERIFICATIONS'
\echo '=============================='
\echo 'Tracks OTPs for login, reset password, and verification flows.'
\echo ''

SELECT otp_id, user_id, purpose, created_at, expires_at, used_at, attempt_count
FROM otp_verification
ORDER BY created_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '6. LOGIN HISTORY'
\echo '=============================='
\echo 'Logs all login attempts including failures and lockouts.'
\echo ''

SELECT login_id, user_id, status, purpose, ip_address, attempt_time
FROM login_history
ORDER BY attempt_time DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '7. DOCUMENTS'
\echo '=============================='
\echo 'Stores metadata of uploaded documents including S3 reference and status.'
\echo ''

SELECT document_id, user_id, org_id, dept_id, original_filename,
       file_type, size_bytes, s3_key, status, uploaded_at, deleted_at
FROM document
ORDER BY uploaded_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '8. ANALYSIS RESULTS'
\echo '=============================='
\echo 'Stores AI-generated compliance results with score and risk level.'
\echo ''

SELECT result_id, document_id, compliance_score, risk_level, summary, created_at
FROM analysis_result
ORDER BY created_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '9. FINDINGS'
\echo '=============================='
\echo 'Contains GAP and RISK findings derived from analysis.'
\echo ''

SELECT finding_id, result_id, finding_type, title, description, created_at
FROM finding
ORDER BY created_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '10. RECOMMENDATIONS'
\echo '=============================='
\echo 'Stores AI-generated recommendations with regulatory references.'
\echo ''

SELECT rec_id, result_id, recommendation_text, status, act_name, page_no, line_no, created_at
FROM recommendations
ORDER BY created_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '11. REPORTS'
\echo '=============================='
\echo 'Stores generated reports with expiry and metadata.'
\echo ''

SELECT report_id, result_id, report_s3_key, file_size, generated_at, expires_at
FROM reports
ORDER BY generated_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '12. REPORT DOWNLOAD HISTORY'
\echo '=============================='
\echo 'Tracks report download activity by users.'
\echo ''

SELECT download_id, report_id, downloaded_by_id, downloaded_at
FROM report_downloads
ORDER BY downloaded_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '13. REPORT SHARING'
\echo '=============================='
\echo 'Stores shared report access details including token and expiry.'
\echo ''

SELECT share_id, report_id, shared_by_id, shared_with_email, access_token, expires_at, created_at, is_active
FROM report_shares
ORDER BY created_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '14. ADMIN ACCESS REQUESTS'
\echo '=============================='
\echo 'Stores admin privilege requests verified via OTP.'
\echo ''

SELECT request_id, user_id, verification_otp_id, org_email, status,
       requested_at, verified_at, failure_reason
FROM admin_access_request
ORDER BY requested_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '15. ACCOUNT DELETION REQUESTS'
\echo '=============================='
\echo 'Records account deletion requests and data erasure summaries for audit.'
\echo ''

SELECT deletion_id, user_id, user_email_snapshot, request_type, status,
       reason, erasure_summary, requested_at, completed_at, ip_address
FROM deletion_request
ORDER BY requested_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '16. AUDIT LOG'
\echo '=============================='
\echo 'Tracks all critical system actions for monitoring and compliance.'
\echo ''

SELECT audit_id, user_id, action_type, target_type, target_id,
       success, severity, ip_address, created_at
FROM audit_logs
ORDER BY created_at DESC
LIMIT 10;