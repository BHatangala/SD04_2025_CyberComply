-- ===================================================================
-- CyberComply Demo Evidence Script for Milestone 2 & 3 (Database Overview)
-- ===================================================================

\x on
\timing on

\echo ''
\echo ''
\echo '=============================='
\echo 'SYSTEM SUMMARY'
\echo '=============================='
\echo 'Quick overview of total records in each key table.'
\echo ''

SELECT 
    (SELECT COUNT(*) FROM organization)        AS total_organizations,
    (SELECT COUNT(*) FROM department)          AS total_departments,
    (SELECT COUNT(*) FROM auth_user)           AS total_users,
    (SELECT COUNT(*) FROM user_profile)        AS total_user_profiles,
    (SELECT COUNT(*) FROM document)            AS total_documents,
    (SELECT COUNT(*) FROM analysis_result)     AS total_analysis_results,
    (SELECT COUNT(*) FROM finding)             AS total_findings,
    (SELECT COUNT(*) FROM recommendations)     AS total_recommendations,
    (SELECT COUNT(*) FROM reports)             AS total_reports,
    (SELECT COUNT(*) FROM report_downloads)    AS total_downloads,
    (SELECT COUNT(*) FROM report_shares)       AS total_shared_reports,
    (SELECT COUNT(*) FROM admin_access_request) AS total_admin_requests,
    (SELECT COUNT(*) FROM deletion_request)    AS total_deletion_requests,
    (SELECT COUNT(*) FROM audit_logs)          AS total_audit_logs;


\echo ''
\echo ''
\echo '=============================='
\echo '1. ORGANIZATIONS'
\echo '=============================='
\echo 'Displays all registered organizations in the system.'
\echo ''

SELECT org_id, org_name, created_at
FROM organization
ORDER BY created_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '2. DEPARTMENTS'
\echo '=============================='
\echo 'Displays departments linked to organizations.'
\echo ''

SELECT d.dept_id,
       d.dept_name,
       d.org_id,
       o.org_name,
       d.created_at
FROM department d
JOIN organization o ON d.org_id = o.org_id
ORDER BY d.created_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '3. USERS (AUTHENTICATION)'
\echo '=============================='
\echo 'Stores login credentials using Django authentication.'
\echo ''

SELECT id, username AS email, email, is_active, date_joined
FROM auth_user
ORDER BY date_joined DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '4. USER PROFILES'
\echo '=============================='
\echo 'Stores extended user details including role and security attributes.'
\echo ''

SELECT up.user_id,
       up.auth_user_id,
       up.full_name,
       up.role,
       up.is_verified,
       up.otp_is_enabled,
       up.failed_login_count,
       up.locked_until,
       up.last_login_at,
       up.deleted_at,
       up.org_id,
       o.org_name
FROM user_profile up
LEFT JOIN organization o ON up.org_id = o.org_id
ORDER BY up.updated_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '5. OTP VERIFICATIONS'
\echo '=============================='
\echo 'Tracks OTPs for login, reset password, and verification flows.'
\echo ''

SELECT otp_id, 
       user_id, 
       purpose, 
       created_at, 
       expires_at, 
       used_at, 
       attempt_count
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

SELECT lh.login_id,
       lh.user_id,
       up.full_name,
       lh.status,
       lh.purpose,
       lh.ip_address,
       lh.attempt_time
FROM login_history lh
LEFT JOIN user_profile up ON lh.user_id = up.user_id
ORDER BY lh.attempt_time DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '7. DOCUMENTS'
\echo '=============================='
\echo 'Stores metadata of uploaded documents including S3 reference and status.'
\echo ''

SELECT d.document_id,
       d.user_id,
       up.full_name,
       d.org_id,
       o.org_name,
       d.dept_id,
       dept.dept_name,
       d.original_filename,
       d.file_type,
       d.size_bytes,
       d.s3_key,
       d.status,
       d.uploaded_at,
       d.deleted_at
FROM document d
LEFT JOIN user_profile up ON d.user_id = up.user_id
LEFT JOIN organization o ON d.org_id = o.org_id
LEFT JOIN department dept ON d.dept_id = dept.dept_id
ORDER BY d.uploaded_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '8. ANALYSIS RESULTS'
\echo '=============================='
\echo 'Stores AI-generated compliance results with score and risk level.'
\echo ''

SELECT ar.result_id,
       ar.document_id,
       d.original_filename,
       ar.compliance_score,
       ar.risk_level,
       ar.summary,
       ar.created_at
FROM analysis_result ar
JOIN document d ON ar.document_id = d.document_id
ORDER BY ar.created_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '9. FINDINGS'
\echo '=============================='
\echo 'Contains GAP and RISK findings derived from analysis.'
\echo ''

SELECT f.finding_id,
       f.result_id,
       ar.document_id,
       d.original_filename,
       f.finding_type,
       f.title,
       f.description,
       f.created_at
FROM finding f
JOIN analysis_result ar ON f.result_id = ar.result_id
JOIN document d ON ar.document_id = d.document_id
ORDER BY f.created_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '10. RECOMMENDATIONS'
\echo '=============================='
\echo 'Stores AI-generated recommendations, severity levels, corrective steps, and legal section references.'
\echo ''

SELECT r.rec_id,
       r.result_id,
       ar.document_id,
       d.original_filename,
       r.recommendation_text,
       r.status,
       r.act_name,
       r.steps_to_achieve,
       r.section,
       r.created_at
FROM recommendations r
JOIN analysis_result ar ON r.result_id = ar.result_id
JOIN document d ON ar.document_id = d.document_id
ORDER BY r.created_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '11. REPORTS'
\echo '=============================='
\echo 'Stores generated reports with expiry and metadata.'
\echo ''

SELECT rp.report_id,
       rp.result_id,
       ar.document_id,
       d.original_filename,
       rp.report_s3_key,
       rp.file_size,
       rp.generated_at,
       rp.expires_at
FROM reports rp
JOIN analysis_result ar ON rp.result_id = ar.result_id
JOIN document d ON ar.document_id = d.document_id
ORDER BY rp.generated_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '12. REPORT DOWNLOAD HISTORY'
\echo '=============================='
\echo 'Tracks report download activity by users.'
\echo ''

SELECT rd.download_id,
       rd.report_id,
       rd.downloaded_by_id,
       up.full_name AS downloaded_by_name,
       rd.downloaded_at
FROM report_downloads rd
LEFT JOIN user_profile up ON rd.downloaded_by_id = up.user_id
ORDER BY rd.downloaded_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '13. REPORT SHARING'
\echo '=============================='
\echo 'Stores shared report access details including token and expiry.'
\echo ''

SELECT rs.share_id,
       rs.report_id,
       rs.shared_by_id,
       up.full_name AS shared_by_name,
       rs.shared_with_email,
       rs.access_token,
       rs.expires_at,
       rs.created_at,
       rs.is_active
FROM report_shares rs
LEFT JOIN user_profile up ON rs.shared_by_id = up.user_id
ORDER BY rs.created_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '14. ADMIN ACCESS REQUESTS'
\echo '=============================='
\echo 'Stores admin privilege requests verified via OTP.'
\echo ''

SELECT aar.request_id,
       aar.user_id,
       up.full_name,
       aar.verification_otp_id,
       aar.org_email,
       aar.status,
       aar.requested_at,
       aar.verified_at,
       aar.failure_reason
FROM admin_access_request aar
LEFT JOIN user_profile up ON aar.user_id = up.user_id
ORDER BY aar.requested_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '15. ACCOUNT DELETION REQUESTS'
\echo '=============================='
\echo 'Records account deletion requests and data erasure summaries for audit.'
\echo ''

SELECT deletion_id, 
       user_id, 
       user_email_snapshot, 
       request_type, 
       status,
       reason, 
       erasure_summary, 
       requested_at, 
       completed_at, 
       ip_address
FROM deletion_request
ORDER BY requested_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo '16. AUDIT LOG'
\echo '=============================='
\echo 'Tracks important system actions for monitoring, accountability, and compliance evidence.'
\echo ''

SELECT al.audit_id,
       al.user_id,
       up.full_name,
       al.action_type,
       al.target_type,
       al.target_id,
       al.success,
       al.severity,
       al.ip_address,
       al.created_at
FROM audit_logs al
LEFT JOIN user_profile up ON al.user_id = up.user_id
ORDER BY al.created_at DESC
LIMIT 10;


\echo ''
\echo ''
\echo '=============================='
\echo 'SLOW QUERY MONITORING'
\echo '=============================='
\echo 'Displays filtered application queries with average execution time above 10 ms.'
\echo ''

SELECT
    LEFT(query, 120)                    AS query_preview,
    calls,
    ROUND(total_exec_time::numeric, 2)  AS total_exec_time_ms,
    ROUND(mean_exec_time::numeric, 2)   AS avg_exec_time_ms
FROM
    pg_stat_statements
WHERE
    query ~* '(organization|department|auth_user|user_profile|document|analysis_result|finding|recommendations|reports|report_downloads|report_shares|admin_access_request|deletion_request|audit_logs)'
    AND mean_exec_time > 10
ORDER BY
    total_exec_time DESC;


\echo ''
\echo ''
\echo '=============================='
\echo 'MOST FREQUENT QUERIES'
\echo '=============================='
\echo 'Displays the most frequently executed queries.'
\echo ''

SELECT
    LEFT(query, 120)                   AS query_preview,
    calls,
    ROUND(mean_exec_time::numeric, 2)  AS avg_exec_time_ms
FROM
    pg_stat_statements
WHERE
    query ~* '(organization|department|auth_user|user_profile|document|analysis_result|finding|recommendations|reports|report_downloads|report_shares|admin_access_request|deletion_request|audit_logs)'
ORDER BY
    calls DESC
LIMIT 10;