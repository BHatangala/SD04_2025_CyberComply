// tests/e2e/helpers/helper_login.js
//
// Shared login helpers used by any test that requires an authenticated session.
// Handles both direct-login accounts and first-time-login OTP accounts.

const { expect }    = require('@playwright/test');
const { seedOtp, KNOWN_OTP } = require('./otpSeeder');

const BASE = 'http://127.0.0.1:5500/frontend';

// ── Credentials ───────────────────────────────────────────────────────────────
// Change your email and passwords to the actual accounts (General & Admin) setup in your DB before running
const GENERAL_EMAIL = '21804005@student.curtin.edu.au';
const GENERAL_PASS  = 'Curtin1781*';
const ADMIN_EMAIL   = 'edirisinghev82oth@gmail.com';
const ADMIN_PASS    = 'Curtin1781*';

// OTP selectors (from otp_component.js)
const OTP_INPUT  = 'input.otp-input';
const OTP_BTN    = 'button.otp-btn';

/**
 * Logs in as a verified general user (no OTP required).
 * Waits until home.html is fully loaded.
 */
async function loginAsGeneral(page) {
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
    await page.goto('./login.html');
    // Dismiss any success popup that may be covering the form
    await page.evaluate(() => {
        const modal = document.querySelector('.modal');
        if (modal) modal.style.display = 'none';
    }).catch(() => {});
    await page.fill('#email', GENERAL_EMAIL);
    await page.fill('#password', GENERAL_PASS);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home.html', { timeout: 30000 });
}

/**
 * Logs in as an admin user (no OTP required).
 * Waits until home.html is fully loaded.
 */
async function loginAsAdmin(page) {
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
    await page.goto('./login.html');
    await page.evaluate(() => {
        const modal = document.querySelector('.modal');
        if (modal) modal.style.display = 'none';
    }).catch(() => {});
    await page.fill('#email', ADMIN_EMAIL);
    await page.fill('#password', ADMIN_PASS);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home.html', { timeout: 30000 });
}

/**
 * Logs in as a user whose account requires a FIRST_LOGIN OTP.
 * Seeds the known OTP into the DB first so we never need to read the inbox.
 *
 * @param {string} email
 * @param {string} password
 */
async function loginWithFirstLoginOtp(page, email, password) {
    seedOtp(email, 'FIRST_LOGIN');

    await page.goto('./login.html');
    await page.fill('#email', email);
    await page.fill('#password', password);
    await page.click('button[type="submit"]');

    // Wait for OTP step to appear
    await expect(page.locator('h1:has-text("Verify OTP")')).toBeVisible({ timeout: 10000 });

    await page.fill(OTP_INPUT, KNOWN_OTP);
    await page.click(OTP_BTN);

    await page.waitForURL('**/home.html', { timeout: 15000 });
}

/**
 * Logs in as a user who has 2FA enabled.
 * Seeds the known OTP into the DB first.
 *
 * @param {string} email
 * @param {string} password
 */
async function loginWith2FA(page, email, password) {
    seedOtp(email, 'LOGIN_2FA');

    await page.goto('./login.html');
    await page.fill('#email', email);
    await page.fill('#password', password);
    await page.click('button[type="submit"]');

    await expect(page.locator('h1:has-text("Verify OTP")')).toBeVisible({ timeout: 10000 });

    await page.fill(OTP_INPUT, KNOWN_OTP);
    await page.click(OTP_BTN);

    await page.waitForURL('**/home.html', { timeout: 15000 });
}

module.exports = {
    loginAsGeneral,
    loginAsAdmin,
    loginWithFirstLoginOtp,
    loginWith2FA,
    GENERAL_EMAIL,
    GENERAL_PASS,
    ADMIN_EMAIL,
    ADMIN_PASS,
    OTP_INPUT,
    OTP_BTN,
    KNOWN_OTP,
};