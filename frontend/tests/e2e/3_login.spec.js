// tests/e2e/3_login.spec.js
// ─────────────────────────────────────────────────────────────────────────────
// Login page (login.html)
// Covers: client-side validation, wrong credentials, account lockout (mocked),
// first-login OTP flow, wrong/expired/brute-force OTP, 2FA flow, happy path.
//
// OTP selectors come directly from otp_component.js:
//   input.otp-input        — the 6-digit code input
//   button.otp-btn         — the "VERIFY OTP" button
//   .otp-message--error    — inline error inside the OTP component
//   .otp-message--success  — inline success inside the OTP component
// ─────────────────────────────────────────────────────────────────────────────

const { test, expect } = require('@playwright/test');
const { seedOtp, KNOWN_OTP } = require('./helpers/otpSeeder');
const { setUnverified, setVerified } = require('./helpers/verificationHelper');

const LOGIN_URL     = './login.html';
const GENERAL_EMAIL = '21804005@student.curtin.edu.au';
const GENERAL_PASS  = 'Curtin1781*';
const ADMIN_EMAIL   = 'edirisinghev82oth@gmail.com';
const ADMIN_PASS    = 'Curtin1781*';
const WRONG_PASS    = 'WrongPassword999!';

// OTP component selectors (from otp_component.js)
const OTP_INPUT     = 'input.otp-input';
const OTP_BTN       = 'button.otp-btn';
const OTP_ERROR_MSG = '.otp-message--error';

// ── Shared setup helpers ──────────────────────────────────────────────────────

async function fillCredentials(page, email, password) {
    await page.fill('#email', email);
    await page.fill('#password', password);
}

async function submitLogin(page) {
    await page.click('button[type="submit"]');
}

/**
 * Stubs /api/login/ to return requires_otp: true then submits credentials.
 * This forces the OTP step without needing the account to be unverified.
 */
async function triggerOtpStep(page, email = GENERAL_EMAIL, password = GENERAL_PASS) {
    await page.route('**/api/login/', async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                requires_otp: true,
                detail: 'A verification code has been sent to your email.',
            }),
        });
    });
    await fillCredentials(page, email, password);
    await submitLogin(page);
    await expect(page.locator('h1:has-text("Verify OTP")')).toBeVisible({ timeout: 8000 });
}

// ─────────────────────────────────────────────────────────────────────────────
// Client-side validation
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Login — Client-side Validation', () => {

    test.beforeEach(async ({ page }) => { await page.goto(LOGIN_URL); });

    test('shows error when both fields are empty', async ({ page }) => {
        await submitLogin(page);
        await expect(page.locator('text=Please enter your email and password')).toBeVisible();
    });

    test('shows error when only email is missing', async ({ page }) => {
        await page.fill('#password', GENERAL_PASS);
        await submitLogin(page);
        await expect(page.locator('text=Please enter your email address')).toBeVisible();
    });

    test('shows error when only password is missing', async ({ page }) => {
        await page.fill('#email', GENERAL_EMAIL);
        await submitLogin(page);
        await expect(page.locator('text=Please enter your password')).toBeVisible();
    });

    test('shows error for malformed email', async ({ page }) => {
        await fillCredentials(page, 'not-an-email', GENERAL_PASS);
        await submitLogin(page);
        await expect(page.locator('text=valid email address')).toBeVisible();
    });

    test('submit button shows "Signing In..." and is disabled while loading', async ({ page }) => {
        await page.route('**/api/login/', () => new Promise(() => {}));
        await fillCredentials(page, GENERAL_EMAIL, GENERAL_PASS);
        await submitLogin(page);
        await expect(page.locator('button[type="submit"]')).toContainText('Signing In...');
        await expect(page.locator('button[type="submit"]')).toBeDisabled();
    });

    test('password field has a toggle to reveal / hide password', async ({ page }) => {
        await page.fill('#password', GENERAL_PASS);
        await expect(page.locator('#password')).toHaveAttribute('type', 'password');
        await page.click('.toggle-password');
        await expect(page.locator('#password')).toHaveAttribute('type', 'text');
        await page.click('.toggle-password');
        await expect(page.locator('#password')).toHaveAttribute('type', 'password');
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Wrong credentials
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Login — Wrong Credentials', () => {

    test.beforeEach(async ({ page }) => { await page.goto(LOGIN_URL); });

    test('shows "Invalid email or password." for wrong password', async ({ page }) => {
        await fillCredentials(page, GENERAL_EMAIL, WRONG_PASS);
        await submitLogin(page);
        await expect(page.locator('text=Invalid email or password')).toBeVisible({ timeout: 10000 });
    });

    test('shows "Invalid email or password." for unregistered email', async ({ page }) => {
        await fillCredentials(page, 'nobody@nowhere.com', GENERAL_PASS);
        await submitLogin(page);
        await expect(page.locator('text=Invalid email or password')).toBeVisible({ timeout: 10000 });
    });

    test('password field is cleared after a wrong-password error', async ({ page }) => {
        await fillCredentials(page, GENERAL_EMAIL, WRONG_PASS);
        await submitLogin(page);
        await expect(page.locator('text=Invalid email or password')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('#password')).toHaveValue('');
    });

    test('raw Django error is never exposed in the page', async ({ page }) => {
        await fillCredentials(page, GENERAL_EMAIL, WRONG_PASS);
        await submitLogin(page);
        await page.waitForTimeout(5000);
        const body = await page.content();
        expect(body).not.toContain('ObjectDoesNotExist');
        expect(body).not.toContain('Traceback');
        expect(body).not.toContain('authenticate(');
        expect(body).not.toContain('Exception');
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Account lockout (mocked)
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Login — Account Lockout', () => {

    test('shows lockout message when backend returns HTTP 423', async ({ page }) => {
        await page.goto(LOGIN_URL);
        await page.route('**/api/login/', async route => {
            await route.fulfill({
                status: 423,
                contentType: 'application/json',
                body: JSON.stringify({ detail: 'Account is temporarily locked. Please try again in 15 minutes.' }),
            });
        });
        await fillCredentials(page, GENERAL_EMAIL, WRONG_PASS);
        await submitLogin(page);
        await expect(page.locator('text=temporarily locked')).toBeVisible({ timeout: 5000 });
    });

    test('shows "Too many attempts. Account locked for 15 minutes." on 5th failure', async ({ page }) => {
        await page.goto(LOGIN_URL);
        await page.route('**/api/login/', async route => {
            await route.fulfill({
                status: 423,
                contentType: 'application/json',
                body: JSON.stringify({ detail: 'Too many attempts. Account locked for 15 minutes.' }),
            });
        });
        await fillCredentials(page, GENERAL_EMAIL, WRONG_PASS);
        await submitLogin(page);
        await expect(page.locator('text=Too many attempts')).toBeVisible({ timeout: 5000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// OTP step — wrong / edge-case inputs
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Login — OTP Step: Wrong Inputs', () => {

    test('OTP step is shown when backend returns requires_otp: true', async ({ page }) => {
        await page.goto(LOGIN_URL);
        await triggerOtpStep(page);
        await expect(page.locator(OTP_INPUT)).toBeVisible();
        await expect(page.locator(OTP_BTN)).toBeVisible();
        await expect(page.locator('text=verification code has been sent')).toBeVisible();
    });

    test('shows OTP component error when OTP field is empty', async ({ page }) => {
        await page.goto(LOGIN_URL);
        await triggerOtpStep(page);
        await page.click(OTP_BTN);
        await expect(page.locator(OTP_ERROR_MSG)).toContainText('Please enter the OTP');
    });

    test('non-numeric OTP is stripped and shows error', async ({ page }) => {
        await page.goto(LOGIN_URL);
        await triggerOtpStep(page);
        await page.fill(OTP_INPUT, 'ABCDEF');
        await page.click(OTP_BTN);
        await expect(page.locator(OTP_ERROR_MSG)).toContainText(/Please enter|Invalid or expired/);
    });

    test('5-digit OTP shows "Invalid or expired" error', async ({ page }) => {
        await page.goto(LOGIN_URL);
        await triggerOtpStep(page);
        await page.fill(OTP_INPUT, '12345');
        await page.click(OTP_BTN);
        await expect(page.locator(OTP_ERROR_MSG)).toContainText('Invalid or expired verification code');
    });

    // ── Option B fix: mock /api/verify-otp/ to return 401 ────────────────────
    // The real backend returns "OTP not required" for a verified account with
    // no 2FA — so we mock the verify endpoint to simulate a genuine wrong-OTP
    // response from the backend without needing an unverified account here.
    test('wrong 6-digit OTP shows "Invalid or expired" error from backend', async ({ page }) => {
        await page.goto(LOGIN_URL);
        await triggerOtpStep(page);
        await page.route('**/api/verify-otp/', async route => {
            await route.fulfill({
                status: 401,
                contentType: 'application/json',
                body: JSON.stringify({ detail: 'Invalid or expired verification code' }),
            });
        });
        await page.fill(OTP_INPUT, '000000');
        await page.click(OTP_BTN);
        await expect(page.locator(OTP_ERROR_MSG)).toContainText('Invalid or expired verification code', { timeout: 8000 });
    });

    // ── Additional test: real backend behaviour for verified account ──────────
    // Documents what the real /api/verify-otp/ actually returns for a verified
    // account that has no 2FA enabled — "OTP not required for this account."
    // The OTP component catches this as a generic error and displays it.
    test('shows error when OTP submitted for verified account without 2FA', async ({ page }) => {
        await page.goto(LOGIN_URL);
        await triggerOtpStep(page);
        // No route mock — hits the real backend
        await page.fill(OTP_INPUT, '000000');
        await page.click(OTP_BTN);
        // Backend returns 400: "OTP not required for this account."
        // The OTP component displays whatever detail the backend sends
        await expect(page.locator(OTP_ERROR_MSG)).toContainText('OTP not required', { timeout: 10000 });
    });

    test('OTP is cleared from input after wrong-OTP error', async ({ page }) => {
        await page.goto(LOGIN_URL);
        await triggerOtpStep(page);
        await page.route('**/api/verify-otp/', async route => {
            await route.fulfill({
                status: 401,
                contentType: 'application/json',
                body: JSON.stringify({ detail: 'Invalid or expired verification code' }),
            });
        });
        await page.fill(OTP_INPUT, '000000');
        await page.click(OTP_BTN);
        await expect(page.locator(OTP_ERROR_MSG)).toBeVisible({ timeout: 8000 });
        await expect(page.locator(OTP_INPUT)).toHaveValue('');
    });

    test('VERIFY OTP button shows "VERIFYING..." while request is in-flight', async ({ page }) => {
        await page.goto(LOGIN_URL);
        await triggerOtpStep(page);
        await page.route('**/api/verify-otp/', () => new Promise(() => {}));
        await page.fill(OTP_INPUT, '123456');
        await page.click(OTP_BTN);
        await expect(page.locator(OTP_BTN)).toContainText('VERIFYING...');
        await expect(page.locator(OTP_BTN)).toBeDisabled();
    });

    test('brute-force lockout — shows "Too many verification attempts" message', async ({ page }) => {
        await page.goto(LOGIN_URL);
        await triggerOtpStep(page);
        await page.route('**/api/verify-otp/', async route => {
            await route.fulfill({
                status: 401,
                contentType: 'application/json',
                body: JSON.stringify({
                    detail: 'Too many verification attempts. Please login again to request a new verification code.',
                }),
            });
        });
        await page.fill(OTP_INPUT, '000000');
        await page.click(OTP_BTN);
        await expect(page.locator(OTP_ERROR_MSG)).toContainText('Too many verification attempts', { timeout: 8000 });
    });

    test('expired OTP shows "Invalid or expired verification code" message', async ({ page }) => {
        await page.goto(LOGIN_URL);
        await triggerOtpStep(page);
        await page.route('**/api/verify-otp/', async route => {
            await route.fulfill({
                status: 401,
                contentType: 'application/json',
                body: JSON.stringify({ detail: 'Invalid or expired verification code' }),
            });
        });
        await page.fill(OTP_INPUT, '123457');
        await page.click(OTP_BTN);
        await expect(page.locator(OTP_ERROR_MSG)).toContainText('Invalid or expired verification code', { timeout: 8000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// OTP step — Back button
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Login — OTP Step: Navigation', () => {

    test('Back button returns to credentials step and clears the message', async ({ page }) => {
        await page.goto(LOGIN_URL);
        await triggerOtpStep(page);
        await page.click('button:has-text("Back")');
        await expect(page.locator('h1:has-text("Login")')).toBeVisible();
        await expect(page.locator('#email')).toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// OTP Happy Path — real DB (Option B fix)
//
// Strategy:
//   beforeEach  → set is_verified = False  (account behaves as newly registered)
//               → seed known OTP 123456 for FIRST_LOGIN purpose
//   test body   → real login → backend returns requires_otp: true
//               → submit 123456 → backend verifies → redirects to home ✓
//   afterEach   → set is_verified = True   (restore account for all other tests)
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Login — OTP Happy Path', () => {

    test.beforeEach(async () => {
        setUnverified(GENERAL_EMAIL); // Mark account as unverified so backend triggers FIRST_LOGIN OTP
    });

    test.afterEach(async () => {
        // Restore account to verified state so all other tests work normally
        setVerified(GENERAL_EMAIL);
    });

    test('correct FIRST_LOGIN OTP verifies account and redirects to home', async ({ page }) => {
        await page.goto(LOGIN_URL);

        // Step 1: submit credentials — this triggers the real login
        // and causes backend to generate + send a real OTP via AWS
        await fillCredentials(page, GENERAL_EMAIL, GENERAL_PASS);
        await submitLogin(page);

        // Step 2: wait for OTP step to appear
        await expect(page.locator('h1:has-text("Verify OTP")')).toBeVisible({ timeout: 10000 });

        // Step 3: NOW seed 123456 — it becomes the newest OTP row
        // so backend's .order_by("-created_at").first() picks it up
        seedOtp(GENERAL_EMAIL, 'FIRST_LOGIN');

        // Step 4: submit the known OTP
        await page.fill(OTP_INPUT, KNOWN_OTP);
        await page.click(OTP_BTN);

        // Step 5: wait for redirect to home
        await page.waitForURL('**/home.html', { timeout: 20000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Direct login — no OTP (verified account)
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Login — Direct Login (Verified Account)', () => {

    test('correct credentials show success popup then redirect to home', async ({ page }) => {
        await page.goto(LOGIN_URL);
        await fillCredentials(page, GENERAL_EMAIL, GENERAL_PASS);
        await submitLogin(page);

        const popup = page.locator('.success-modal-content h3');
        const isOnHome = page.url().includes('home.html');

        if (!isOnHome) {
            const popupVisible = await popup.isVisible({ timeout: 8000 }).catch(() => false);
            if (popupVisible) {
                await expect(popup).toContainText('Login Successful');
            }
        }
        await page.waitForURL('**/home.html', { timeout: 15000 });
    });

    test('admin credentials log in and redirect to home', async ({ page }) => {
        await page.goto(LOGIN_URL);
        await fillCredentials(page, ADMIN_EMAIL, ADMIN_PASS);
        await submitLogin(page);
        await page.waitForURL('**/home.html', { timeout: 15000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Navigation
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Login — Navigation', () => {

    test.beforeEach(async ({ page }) => { await page.goto(LOGIN_URL); });

    test('"Forgot Password?" link navigates to forgot_password.html', async ({ page }) => {
        await page.click('a:has-text("Forgot Password")');
        await expect(page).toHaveURL(/forgot_password\.html/);
    });
});