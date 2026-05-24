// tests/e2e/helpers/verificationHelper.js
//
// Shells out to reset_verification.py to flip the is_verified flag
// on a user account in the Django DB.
//
// Used by login OTP happy-path tests that need the account to be
// UNVERIFIED before the test and VERIFIED again after.
//
// SETUP
//   1. Place reset_verification.py at DJANGO_PROJECT_ROOT (next to manage.py).
//   2. Edit DJANGO_PROJECT_ROOT and PYTHON_BIN below to match your machine.
//      (These should match the values in otpSeeder.js)

const { execSync } = require('child_process');
const path         = require('path');

// ── Edit these values to match your machine ───────────────────────────────────
const DJANGO_PROJECT_ROOT    = path.resolve(__dirname, '../../../../DjangoManager');
const DJANGO_SETTINGS_MODULE = 'DjangoManager.settings';                              
const PYTHON_BIN             = '/Users/ibrahim/Documents/ccp/sd04_2025/venv/bin/python'; // ← your venv python
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Sets is_verified = False for the given account.
 * Call this in beforeEach before a FIRST_LOGIN OTP test.
 *
 * @param {string} email
 */
function setUnverified(email) {
    _run(email, 'unverified');
}

/**
 * Sets is_verified = True for the given account.
 * Call this in afterEach to restore the account after a FIRST_LOGIN OTP test.
 *
 * @param {string} email
 */
function setVerified(email) {
    _run(email, 'verified');
}

function _run(email, state) {
    const scriptPath = path.join(DJANGO_PROJECT_ROOT, 'reset_verification.py');
    const cmd = `"${PYTHON_BIN}" "${scriptPath}" "${email}" "${state}"`;
    try {
        const output = execSync(cmd, {
            cwd: DJANGO_PROJECT_ROOT,
            env: { ...process.env, DJANGO_SETTINGS_MODULE },
            stdio: 'pipe',
        });
        console.log('[verificationHelper]', output.toString().trim());
    } catch (err) {
        throw new Error(
            `[verificationHelper] Failed to set ${email} → ${state}:\n` +
            (err.stderr?.toString() || err.message)
        );
    }
}

module.exports = { setUnverified, setVerified };