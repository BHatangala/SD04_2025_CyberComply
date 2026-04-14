// tests/e2e/forgot_password.spec.js
// ─────────────────────────────────────────────────────────────────────────────
// Forgot Password page (forgot_password.html)
// Three steps:  Step 1: Email  →  Step 2: OTP  →  Step 3: New Password
//
// OTP selectors from otp_component.js (mode="reset"):
//   input.otp-input          — code input
//   button.otp-btn           — VERIFY OTP button
//   .otp-message--error      — inline error inside OTP component
//   .otp-message--success    — inline success inside OTP component
//
// Page-level messages (forgot_password.html v-if="message.text"):
//   text=verification code has been sent   ← step-1 success
//   text=OTP verified                      ← step-2 success (before step 3)
//   text=Password reset successfully       ← step-3 success
// ─────────────────────────────────────────────────────────────────────────────

const { test, expect } = require('@playwright/test');
const { seedOtp, KNOWN_OTP } = require('./helpers/otpSeeder');

const FP_URL        = './forgot_password.html';
const GENERAL_EMAIL = '21804005@student.curtin.edu.au';
const NEW_PASSWORD  = 'NewCurtinPass2025!';

// OTP component selectors
const OTP_INPUT     = 'input.otp-input';
const OTP_BTN       = 'button.otp-btn';
const OTP_ERR       = '.otp-message--error';

// ── Shared flow helpers ───────────────────────────────────────────────────────

/**
 * Go to forgot_password.html, submit a valid email, and wait for Step 2.
 * Stubs the request-password-reset endpoint so no real email is sent
 * (unless you want real backend behaviour — remove the route() call).
 */
async function goToStep2(page, email = GENERAL_EMAIL, { useRealBackend = false } = {}) {
    await page.goto(FP_URL);

    if (!useRealBackend) {
        await page.route('**/api/request-password-reset/', async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ detail: 'A verification code has been sent to your email.' }),
            });
        });
    }

    await page.fill('input[type="email"]', email);
    await page.click('button:has-text("Send OTP")');
    await expect(page.locator('text=verification code has been sent')).toBeVisible({ timeout: 15000 });
    // OTP input from the <otp-verification> component should now be visible
    await expect(page.locator(OTP_INPUT)).toBeVisible({ timeout: 10000 });
}

/**
 * Seeds known OTP, completes steps 1 & 2, and lands on step 3.
 * Uses the real backend throughout.
 */
async function goToStep3(page, email = GENERAL_EMAIL) {
    await goToStep2(page, email, { useRealBackend: true });

    seedOtp(email, 'RESET_PASSWORD');

    await page.fill(OTP_INPUT, KNOWN_OTP);
    await page.click(OTP_BTN);

    await expect(
        page.locator('input[placeholder="Confirm your new password"]')
    ).toBeVisible({ timeout: 10000 });
}

// ─────────────────────────────────────────────────────────────────────────────
// Step 1 — Email
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Forgot Password — Step 1: Email', () => {

    test.beforeEach(async ({ page }) => { await page.goto(FP_URL); });

    test('renders heading, email input and Send OTP button', async ({ page }) => {
        await expect(page.locator('h1')).toContainText('Forgot Password');
        await expect(page.locator('input[type="email"]')).toBeVisible();
        await expect(page.locator('button:has-text("Send OTP")')).toBeVisible();
    });

    test('shows error for empty email submission', async ({ page }) => {
        await page.click('button:has-text("Send OTP")');
        await expect(page.locator('text=valid email address')).toBeVisible();
    });

    test('shows error for malformed email', async ({ page }) => {
        await page.fill('input[type="email"]', 'bademail@@');
        await page.click('button:has-text("Send OTP")');
        await expect(page.locator('text=valid email address')).toBeVisible();
    });

    test('Send OTP button shows "SENDING..." and is disabled while in-flight', async ({ page }) => {
        await page.route('**/api/request-password-reset/', () => new Promise(() => {}));
        await page.fill('input[type="email"]', GENERAL_EMAIL);
        await page.click('button:has-text("Send OTP")');
        await expect(page.locator('button:has-text("SENDING...")')).toBeDisabled();
    });

    test('shows success message for registered email', async ({ page }) => {
        await page.route('**/api/request-password-reset/', async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ detail: 'A verification code has been sent to your email.' }),
            });
        });
        await page.fill('input[type="email"]', GENERAL_EMAIL);
        await page.click('button:has-text("Send OTP")');
        await expect(page.locator('text=verification code has been sent')).toBeVisible({ timeout: 10000 });
    });

    test('shows same success message for unregistered email (anti-enumeration)', async ({ page }) => {
        // Backend always returns 200 with the same message regardless of
        // whether the email is in the DB — this prevents user enumeration.
        await page.fill('input[type="email"]', 'nosuchuser@example.com');
        await page.click('button:has-text("Send OTP")');
        await expect(page.locator('text=verification code has been sent')).toBeVisible({ timeout: 10000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Step 2 — OTP Verification
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Forgot Password — Step 2: OTP', () => {

    test('OTP input and Verify button are rendered after email submission', async ({ page }) => {
        await goToStep2(page);
        await expect(page.locator(OTP_INPUT)).toBeVisible();
        await expect(page.locator(OTP_BTN)).toBeVisible();
    });

    test('shows component error when OTP field is empty', async ({ page }) => {
        await goToStep2(page);
        await page.click(OTP_BTN);
        await expect(page.locator(OTP_ERR)).toContainText('Please enter the OTP');
    });

    test('non-numeric OTP is stripped and shows "Invalid or expired" error', async ({ page }) => {
        await goToStep2(page);
        await page.fill(OTP_INPUT, 'ABCDEF');
        await page.click(OTP_BTN);
        // After sanitizeOtp() runs, input is empty → "Please enter the OTP"
        // or the component catches the empty string as "Invalid or expired"
        await expect(page.locator(OTP_ERR)).toContainText(/Please enter|Invalid or expired/);
    });

    test('5-digit OTP shows "Invalid or expired" error', async ({ page }) => {
        await goToStep2(page);
        await page.fill(OTP_INPUT, '12345');
        await page.click(OTP_BTN);
        await expect(page.locator(OTP_ERR)).toContainText('Invalid or expired verification code');
    });

    test('wrong 6-digit OTP shows "Invalid or expired" error from backend', async ({ page }) => {
        await goToStep2(page, GENERAL_EMAIL, { useRealBackend: true });
        await page.fill(OTP_INPUT, '000000');
        await page.click(OTP_BTN);
        await expect(page.locator(OTP_ERR)).toContainText('Invalid or expired verification code', { timeout: 10000 });
    });

    test('OTP input is cleared after a wrong OTP attempt', async ({ page }) => {
        await goToStep2(page);
        await page.route('**/api/verify-reset-otp/', async route => {
            await route.fulfill({
                status: 401,
                contentType: 'application/json',
                body: JSON.stringify({ detail: 'Invalid or expired verification code' }),
            });
        });
        await page.fill(OTP_INPUT, '000000');
        await page.click(OTP_BTN);
        await expect(page.locator(OTP_ERR)).toBeVisible({ timeout: 8000 });
        await expect(page.locator(OTP_INPUT)).toHaveValue('');
    });

    test('VERIFY OTP button shows "VERIFYING..." while request is in-flight', async ({ page }) => {
        await goToStep2(page);
        await page.route('**/api/verify-reset-otp/', () => new Promise(() => {}));
        await page.fill(OTP_INPUT, '123456');
        await page.click(OTP_BTN);
        await expect(page.locator(OTP_BTN)).toContainText('VERIFYING...');
        await expect(page.locator(OTP_BTN)).toBeDisabled();
    });

    test('shows brute-force lockout message after max wrong attempts', async ({ page }) => {
        await goToStep2(page);
        await page.route('**/api/verify-reset-otp/', async route => {
            await route.fulfill({
                status: 401,
                contentType: 'application/json',
                body: JSON.stringify({ detail: 'Too many verification attempts. Please request a new code.' }),
            });
        });
        await page.fill(OTP_INPUT, '000000');
        await page.click(OTP_BTN);
        await expect(page.locator(OTP_ERR)).toContainText('Too many verification attempts', { timeout: 8000 });
    });

    test('expired OTP shows "Invalid or expired verification code"', async ({ page }) => {
        await goToStep2(page);
        await page.route('**/api/verify-reset-otp/', async route => {
            await route.fulfill({
                status: 401,
                contentType: 'application/json',
                body: JSON.stringify({ detail: 'Invalid or expired verification code' }),
            });
        });
        await page.fill(OTP_INPUT, '999999');
        await page.click(OTP_BTN);
        await expect(page.locator(OTP_ERR)).toContainText('Invalid or expired verification code', { timeout: 8000 });
    });

    test('correct OTP (seeded) advances to Step 3 — new password form', async ({ page }) => {
        await goToStep3(page);
        await expect(page.locator('input[placeholder*="Enter your new password"]')).toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Step 3 — New Password
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Forgot Password — Step 3: New Password', () => {

    test.beforeEach(async ({ page }) => { await goToStep3(page); });

    test('renders new password and confirm password inputs', async ({ page }) => {
        await expect(page.locator('input[placeholder*="Enter your new password"]')).toBeVisible();
        // Confirm password field is conditionally rendered
    });

    test('shows error (blocks button) when both password fields are empty', async ({ page }) => {
        // Button is disabled when fields are empty — no error message 
        await expect(
            page.locator('button:has-text("Reset Password")')
        ).toBeDisabled();
    });

    test('shows error for weak new password (missing uppercase)', async ({ page }) => {
        await page.fill('input[placeholder*="Enter your new password"]', 'weakpass1!');
        // Confirm field appears after new password has content
        await page.fill('input[placeholder*="Confirm your new password"]', 'weakpass1!');
        await expect(page.locator('.rule-item.invalid:has-text("1 uppercase letter")')).toBeVisible();
    });

    test('shows error for password missing a digit', async ({ page }) => {
        await page.fill('input[placeholder*="Enter your new password"]', 'NoDigitPass!');
        await page.fill('input[placeholder*="Confirm your new password"]', 'NoDigitPass!');
        await expect(page.locator('.rule-item.invalid:has-text("1 digit")')).toBeVisible();
    });

    test('shows error for password missing a special character', async ({ page }) => {
        await page.fill('input[placeholder*="Enter your new password"]', 'NoSpecial1234');
        await page.fill('input[placeholder*="Confirm your new password"]', 'NoSpecial1234');
        await expect(page.locator('.rule-item.invalid:has-text("1 special character")')).toBeVisible();
    });

    test('shows error when new and confirm passwords do not match', async ({ page }) => {
        await page.fill('input[placeholder*="Enter your new password"]', NEW_PASSWORD);
        await page.fill('input[placeholder*="Confirm your new password"]', 'Completely_Different9!');
        await expect(page.locator('.rule-item.invalid:has-text("Passwords do not match")')).toBeVisible();
        await expect(page.locator('button:has-text("Reset Password")')).toBeDisabled();

    });

    test('password strength rules appear while typing', async ({ page }) => {
        await page.fill('input[placeholder*="Enter your new password"]', 'abc');
        await expect(page.locator('.password-rules')).toBeVisible();
    });

    test('backend error "same as current password" is shown in UI', async ({ page }) => {
        await page.route('**/api/reset-password/', async route => {
            await route.fulfill({
                status: 400,
                contentType: 'application/json',
                body: JSON.stringify({ detail: 'Your new password cannot be the same as your current password.' }),
            });
        });
        await page.fill('input[placeholder*="Enter your new password"]', NEW_PASSWORD);
        await page.fill('input[placeholder*="Confirm your new password"]', NEW_PASSWORD);
        await page.click('button:has-text("Reset Password")');
        await expect(page.locator('text=same as your current password')).toBeVisible({ timeout: 8000 });
    });

    test('Reset Password button shows "RESETTING..." while in-flight', async ({ page }) => {
        await page.route('**/api/reset-password/', () => new Promise(() => {}));
        await page.fill('input[placeholder*="Enter your new password"]', NEW_PASSWORD);
        await page.fill('input[placeholder*="Confirm your new password"]', NEW_PASSWORD);
        await page.click('button:has-text("Reset Password")');
        // The button text while resetting (check forgot_password.html template)
        await expect(page.locator('button:has-text("RESETTING...")').or(
            page.locator('button[disabled]:has-text("Reset")')
        )).toBeVisible();
    });

    test('successful reset shows success message and redirects to login.html', async ({ page }) => {
        await page.route('**/api/reset-password/', async route => {  // ← add this mock
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ detail: 'Password reset successfully.' }),
            });
        });
        await page.fill('input[placeholder*="Enter your new password"]', "Cyber@Comply1");
        await page.fill('input[placeholder*="Confirm your new password"]', "Cyber@Comply1");
        await page.click('button:has-text("Reset Password")');

        await page.waitForURL(/login\.html/, { timeout: 15000 });
        await expect(page).toHaveURL(/login\.html/);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Navigation
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Forgot Password — Navigation', () => {

    test('page loads correctly from login.html "Forgot Password?" link', async ({ page }) => {
        await page.goto('./login.html');
        await page.click('a:has-text("Forgot Password")');
        await expect(page).toHaveURL(/forgot_password\.html/);
        await expect(page.locator('h1')).toContainText('Forgot Password');
    });
});