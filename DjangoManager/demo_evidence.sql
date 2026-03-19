-- ===================================================================
-- CyberComply Demo Evidence Script (Frontend -> Backend -> Database)
-- ===================================================================

-- Cleaner output in psql
\x off
\timing on

\echo ''
\echo ''
\echo ''
\echo '=============================='
\echo '1. USER REGISTRATION'
\echo '=============================='

\echo ''
\echo '1.1 Successful Signup - Recently Created Accounts'
\echo ''
SELECT
    up.user_id,
    au.username AS email,
    up.full_name,
    up.role,
    up.is_verified
FROM user_profile up
JOIN auth_user au ON au.id = up.auth_user_id
ORDER BY up.created_at DESC
LIMIT 5;

\echo ''
\echo '1.2 Duplicate / Invalid Registration Attempt - Unique Email Constraint Verified'
\echo ''
SELECT
    username AS email,
    COUNT(*) AS occurrences
FROM auth_user
GROUP BY username
HAVING COUNT(*) > 1;

\echo ''
\echo ''
\echo ''
\echo '======================================'
\echo '2. FIRST LOGIN & ACCOUNT VERIFICATION'
\echo '======================================'

\echo ''
\echo '2.1 Initial Login - OTP Generated for Account Verification'
\echo ''
SELECT
    ov.otp_id,
    au.username AS email,
    ov.purpose,
    ov.created_at,
    ov.expires_at,
    ov.used_at
FROM otp_verification ov
JOIN user_profile up ON up.user_id = ov.user_id
JOIN auth_user au ON au.id = up.auth_user_id
ORDER BY ov.created_at DESC
LIMIT 5;

\echo ''
\echo '2.2 Invalid FIRST LOGIN OTP Submission - Failed Attempt Log'
\echo ''
SELECT
    lh.login_id,
    au.username AS email,
    lh.status,
    lh.purpose,
    lh.ip_address,
    lh.attempt_time
FROM login_history lh
JOIN user_profile up ON up.user_id = lh.user_id
JOIN auth_user au ON au.id = up.auth_user_id
WHERE lh.status = 'FAILED'
  AND lh.purpose = 'FIRST_LOGIN_OTP'
ORDER BY lh.attempt_time DESC
LIMIT 10;

\echo ''
\echo '2.3 OTP Format Validation - Backend Enforcement (Not Stored in DB)'
\echo '    (Invalid format submissions are rejected before database logging)'

\echo ''
\echo '2.4 Successful OTP Verification - Account Status Updated to Verified'
\echo ''
SELECT
    au.username AS email,
    up.is_verified,
    ov.purpose,
    ov.used_at
FROM user_profile up
JOIN auth_user au ON au.id = up.auth_user_id
LEFT JOIN otp_verification ov ON ov.user_id = up.user_id
WHERE ov.purpose = 'FIRST_LOGIN'
ORDER BY ov.used_at DESC NULLS LAST, ov.created_at DESC
LIMIT 5;

\echo ''
\echo ''
\echo ''
\echo '=============================='
\echo '3. SUBSEQUENT LOGIN (NO OTP)'
\echo '=============================='


\echo ''
\echo '3.1 Verified User Login - No OTP Required (2FA Disabled)'
\echo ''
SELECT
    au.username AS email,
    up.otp_is_enabled,
    up.is_verified,
    lh.status,
    lh.attempt_time
FROM login_history lh
JOIN user_profile up ON up.user_id = lh.user_id
JOIN auth_user au ON au.id = up.auth_user_id
WHERE lh.status = 'SUCCESS'
ORDER BY lh.attempt_time DESC
LIMIT 10;

\echo ''
\echo ''
\echo ''
\echo '================================='
\echo '4. LOGIN SECURITY & ACCOUNT LOCK'
\echo '================================='

\echo ''
\echo '4.1 Failed Login Attempts - Security Log Records'
\echo ''
SELECT
    au.username AS email,
    lh.status,
    lh.attempt_time
FROM login_history lh
JOIN user_profile up ON up.user_id = lh.user_id
JOIN auth_user au ON au.id = up.auth_user_id
WHERE lh.status IN ('FAILED', 'LOCKED')
ORDER BY lh.attempt_time DESC
LIMIT 12;

\echo ''
\echo '4.2 Account Lock Status - Failed Attempt Count and Lock Duration'
\echo ''
SELECT
    au.username AS email,
    up.failed_login_count,
    up.locked_until
FROM user_profile up
JOIN auth_user au ON au.id = up.auth_user_id
ORDER BY up.locked_until DESC NULLS LAST
LIMIT 10;

\echo ''
\echo ''
\echo ''
\echo '=============================='
\echo '5. FORGOT PASSWORD WORKFLOW'
\echo '=============================='

\echo ''
\echo '5.1 Password Reset Request - Reset OTP Generated'
\echo ''
SELECT
    ov.otp_id,
    au.username AS email,
    ov.purpose,
    ov.created_at,
    ov.expires_at,
    ov.used_at
FROM otp_verification ov
JOIN user_profile up ON up.user_id = ov.user_id
JOIN auth_user au ON au.id = up.auth_user_id
WHERE ov.purpose = 'RESET_PASSWORD'
ORDER BY ov.created_at DESC
LIMIT 5;

\echo ''
\echo '5.2 Invalid RESET PASSWORD OTP Submission - Security Log Records'
\echo ''
SELECT
    lh.login_id,
    au.username AS email,
    lh.status,
    lh.purpose,
    lh.ip_address,
    lh.attempt_time
FROM login_history lh
JOIN user_profile up ON up.user_id = lh.user_id
JOIN auth_user au ON au.id = up.auth_user_id
WHERE lh.status = 'FAILED'
  AND lh.purpose = 'RESET_PASSWORD_OTP'
ORDER BY lh.attempt_time DESC
LIMIT 10;

\echo ''
\echo '5.3 Reset OTP Format Validation - Backend Enforcement (Not Stored in DB)'
\echo '    (Invalid format submissions are rejected before database logging)'
\echo ''
\echo '5.4 Successful Reset OTP Verification - Authorization Confirmed'
\echo ''
SELECT
    au.username AS email,
    ov.purpose,
    ov.used_at
FROM otp_verification ov
JOIN user_profile up ON up.user_id = ov.user_id
JOIN auth_user au ON au.id = up.auth_user_id
WHERE ov.purpose = 'RESET_PASSWORD'
ORDER BY ov.used_at DESC NULLS LAST, ov.created_at DESC
LIMIT 5;

\echo ''
\echo '5.5 Password Reset Completion - Account Lock Status Check'
\echo ''
SELECT
  au.username AS email,
  up.failed_login_count,
  up.locked_until,
  CASE
    WHEN up.locked_until IS NULL THEN 'UNLOCKED'
    WHEN up.locked_until <= NOW() THEN 'LOCK EXPIRED (will clear on next login)'
    ELSE 'STILL LOCKED'
  END AS lock_status,
  CASE
    WHEN up.locked_until IS NOT NULL AND up.locked_until > NOW()
      THEN (up.locked_until - NOW())
    ELSE NULL
  END AS time_remaining
FROM user_profile up
JOIN auth_user au ON au.id = up.auth_user_id
ORDER BY up.updated_at DESC
LIMIT 10;

\echo ''
\echo ''
\echo ''
\echo '========================================'
\echo '6. FULL DATABASE SNAPSHOT (MILESTONE 1)'
\echo '========================================'

\x on

\echo ''
\echo '6.1 organization table'
\echo ''
SELECT * FROM organization;

\echo ''
\echo '6.2 department table'
\echo ''
SELECT * FROM department;

\echo ''
\echo '6.3 user_profile table'
\echo ''
SELECT * FROM user_profile;

\echo ''
\echo '6.4 auth_user table'
\echo ''
SELECT id, username, email, is_staff, is_active, date_joined
FROM auth_user;

\echo ''
\echo '6.5 otp_verification table'
\echo ''
SELECT * FROM otp_verification
ORDER BY created_at DESC;

\echo ''
\echo '6.6 login_history table'
\echo ''
SELECT * FROM login_history
ORDER BY attempt_time DESC;

\echo ''
\echo '6.7 document table'
\echo ''
SELECT * FROM document
ORDER BY uploaded_at DESC;

\echo ''
\echo '6.8 analysis_result table'
\echo ''
SELECT * FROM analysis_result;

\echo ''
\echo '6.9 recommendations table'
\echo ''
SELECT * FROM recommendations
ORDER BY created_at DESC;

\echo ''
\echo ''
\echo ''
\echo '=============================='
\echo '7. RECOMMENDATIONS'
\echo '=============================='

\x off

\echo ''
\echo '7.1 Valid Insert - Recommendation with PENDING status'
\echo ''
INSERT INTO recommendations (rec_id, result_id, recommendation_text, status, act_name, page_no, line_no, created_at)
VALUES (
    gen_random_uuid(),
    (SELECT result_id FROM analysis_result LIMIT 1),
    'Ensure all personal data is encrypted at rest using AES-256.',
    'PENDING',
    'Personal Data Protection Act No. 9 of 2022',
    12,
    5,
    NOW()
);

\echo ''
\echo '7.2 Valid Insert - Recommendation with IN_PROGRESS status'
\echo ''
INSERT INTO recommendations (rec_id, result_id, recommendation_text, status, act_name, page_no, line_no, created_at)
VALUES (
    gen_random_uuid(),
    (SELECT result_id FROM analysis_result LIMIT 1),
    'Update access control policies to restrict admin privileges.',
    'IN_PROGRESS',
    'Cybersecurity Act No. 19 of 2022',
    7,
    20,
    NOW()
);

\echo ''
\echo '7.3 Valid Insert - Recommendation with DONE status'
\echo ''
INSERT INTO recommendations (rec_id, result_id, recommendation_text, status, act_name, page_no, line_no, created_at)
VALUES (
    gen_random_uuid(),
    (SELECT result_id FROM analysis_result LIMIT 1),
    'Conduct annual staff training on data handling procedures.',
    'DONE',
    'Personal Data Protection Act No. 9 of 2022',
    3,
    10,
    NOW()
);

\echo ''
\echo '7.4 Valid Select - All recommendations for a given result'
\echo ''
SELECT * FROM recommendations
WHERE result_id = (SELECT result_id FROM analysis_result LIMIT 1)
ORDER BY created_at;

\echo ''
\echo '7.5 Valid Update - Change recommendation status from PENDING to IN_PROGRESS'
\echo ''
UPDATE recommendations
SET status = 'IN_PROGRESS'
WHERE recommendation_text LIKE '%encrypted at rest%';

\echo ''
\echo '7.6 Valid Select - Recommendations filtered by status'
\echo ''
SELECT * FROM recommendations WHERE status = 'PENDING';
SELECT * FROM recommendations WHERE status = 'IN_PROGRESS';
SELECT * FROM recommendations WHERE status = 'DONE';

\echo ''
\echo '7.7 Invalid Insert - Bad status value (violates CHECK constraint)'
\echo '    Expected: ERROR — invalid input value for check constraint'
\echo ''
INSERT INTO recommendations (rec_id, result_id, recommendation_text, status, act_name, page_no, line_no, created_at)
VALUES (
    gen_random_uuid(),
    (SELECT result_id FROM analysis_result LIMIT 1),
    'Test bad status.',
    'INVALID_STATUS',
    'Some Act',
    1,
    1,
    NOW()
);

\echo ''
\echo '7.8 Invalid Insert - Non-existent result_id (violates FK constraint)'
\echo '    Expected: ERROR — foreign key violation'
\echo ''
INSERT INTO recommendations (rec_id, result_id, recommendation_text, status, act_name, page_no, line_no, created_at)
VALUES (
    gen_random_uuid(),
    '00000000-0000-0000-0000-000000000000',
    'Orphaned recommendation.',
    'PENDING',
    'Some Act',
    1,
    1,
    NOW()
);

\echo ''
\echo '7.9 Invalid Insert - NULL recommendation_text (violates NOT NULL constraint)'
\echo '    Expected: ERROR — null value violates not-null constraint'
\echo ''
INSERT INTO recommendations (rec_id, result_id, recommendation_text, status, act_name, page_no, line_no, created_at)
VALUES (
    gen_random_uuid(),
    (SELECT result_id FROM analysis_result LIMIT 1),
    NULL,
    'PENDING',
    'Some Act',
    1,
    1,
    NOW()
);

\echo ''
\echo '7.10 Invalid Insert - NULL act_name (violates NOT NULL constraint)'
\echo '     Expected: ERROR — null value violates not-null constraint'
\echo ''
INSERT INTO recommendations (rec_id, result_id, recommendation_text, status, act_name, page_no, line_no, created_at)
VALUES (
    gen_random_uuid(),
    (SELECT result_id FROM analysis_result LIMIT 1),
    'Some recommendation.',
    'PENDING',
    NULL,
    1,
    1,
    NOW()
);

\echo ''
\echo '7.11 CASCADE Delete - Deleting analysis_result removes linked recommendations'
\echo '     Expected: All linked recommendations deleted automatically'
\echo ''
DELETE FROM analysis_result
WHERE result_id = (SELECT result_id FROM analysis_result LIMIT 1);

SELECT * FROM recommendations;
\echo '     Expected: 0 rows returned for the deleted result'

\echo ''
\echo '=============================='
\echo 'END OF DEMO SCRIPT'
\echo '=============================='