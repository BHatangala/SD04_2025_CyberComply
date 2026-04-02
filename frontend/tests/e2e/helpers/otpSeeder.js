// tests/e2e/helpers/otpSeeder.js
//
// Shells out to seed_test_otp.py to inject a known OTP (123456) into
// the Django database for a specific user + purpose, so Playwright tests
// can complete OTP flows without reading a real AWS email inbox.
//
// SETUP
//   1. Edit DJANGO_PROJECT_ROOT to point at the folder that contains manage.py.
//   2. Edit DJANGO_SETTINGS_MODULE to match your project.
//   3. Make sure seed_test_otp.py is at DJANGO_PROJECT_ROOT.

const { execSync } = require('child_process');
const path         = require('path');

// ── Edit these two values ─────────────────────────────────────────────────────
const DJANGO_PROJECT_ROOT    = path.resolve(__dirname, '../../../../DjangoManager'); // ← folder with manage.py
const DJANGO_SETTINGS_MODULE = 'DjangoManager.settings';                         // ← your settings module
const PYTHON_BIN             = 'E:\\Capstone Computing Project\\sd04_2025\\AIModel\\venv\\Scripts\\python';  // change to 'python3' or venv path if needed
// ─────────────────────────────────────────────────────────────────────────────

/** Fixed OTP value seeded into the DB for all tests. */
const KNOWN_OTP = '123456';

/**
 * Seeds a known OTP into the DB for the given user + purpose.
 * Throws if the Django script exits non-zero.
 *
 * @param {string} email
 * @param {'FIRST_LOGIN'|'LOGIN_2FA'|'RESET_PASSWORD'} purpose
 */
function seedOtp(email, purpose) {
    const scriptPath = path.join(DJANGO_PROJECT_ROOT, 'seed_test_otp.py');
    const cmd = `"${PYTHON_BIN}" "${scriptPath}" "${email}" "${purpose}"`;
    try {
        const output = execSync(cmd, {
            cwd: DJANGO_PROJECT_ROOT,
            env: { ...process.env, DJANGO_SETTINGS_MODULE },
            stdio: 'pipe',
        });
        console.log('[otpSeeder]', output.toString().trim());
    } catch (err) {
        throw new Error(
            `[otpSeeder] Failed to seed OTP for ${email}/${purpose}:\n` +
            (err.stderr?.toString() || err.message)
        );
    }
}

module.exports = { seedOtp, KNOWN_OTP };