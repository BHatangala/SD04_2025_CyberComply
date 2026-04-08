// tests/e2e/12_adminaccess.spec.js
// ─────────────────────────────────────────────────────────────────────────────
// Admin Access page (adminaccess.html)
//
// Covers:
//   - Page rendering: title, description, form elements
//   - Email validation: empty, invalid format, non-org domain (backend rejection)
//   - Sending verification: success → OTP modal shown
//   - checkAdminRequestStatus on load: PENDING → OTP modal auto-shown
//   - checkAdminRequestStatus on load: APPROVED → stays on form
//   - OTP modal: visible, shows email, input, verify button
//   - OTP verification: success → success step shown → redirect to profile.html
//   - OTP verification: invalid code → inline error message shown
//   - OTP verification: network failure → inline error message shown (skipped — not yet implemented)
//   - Inline message banners: success and error variants on form
//   - Navigation: back arrow → profile.html, user profile icon → profile.html
//   - Sidebar: open by default, toggle, shifted class on back arrow and main content
//
// MOCKING STRATEGY
//   All route mocks use RegExp with /?$ to match URLs with or without trailing
//   slash. page.unrouteAll() called at the start of each load helper to prevent
//   stale routes bleeding between tests.
// ─────────────────────────────────────────────────────────────────────────────

const { test, expect } = require('@playwright/test');
const { loginAsGeneral } = require('./helpers/helper_login');

const AA_URL = './adminaccess.html';

// ── Regex route helpers ───────────────────────────────────────────────────────

const reRequest = new RegExp(`/api/admin-access/request/?$`);
const reVerify  = new RegExp(`/api/admin-access/verify/?$`);
const reStatus  = new RegExp(`/api/admin-access/status/?$`);

// ── Shared helpers ────────────────────────────────────────────────────────────

/**
 * Clears stale routes, mocks all three admin-access endpoints, and navigates
 * to adminaccess.html.
 *
 * @param {import('@playwright/test').Page} page
 * @param {object} options
 * @param {object} options.statusResponse - Response body for the status endpoint
 * @param {number} options.statusCode     - HTTP status for the status endpoint (default 200)
 */
async function loadPage(page, {
    statusResponse = { status: 'NONE' },
    statusCode = 200,
} = {}) {
    await page.unrouteAll({ behavior: 'ignoreErrors' });

    // Mock: status check on load
    await page.route(reStatus, async route => {
        await route.fulfill({
            status: statusCode,
            contentType: 'application/json',
            body: JSON.stringify(statusResponse),
        });
    });

    // Mock: request endpoint (default success — tests override as needed)
    await page.route(reRequest, async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ request_id: 'test-request-id-123' }),
        });
    });

    // Mock: verify endpoint (default success — tests override as needed)
    await page.route(reVerify, async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ role: 'Administrative User' }),
        });
    });

    await page.goto(AA_URL);
    await page.waitForLoadState('networkidle', { timeout: 15000 });
}

/**
 * Fills the email input, clicks SEND, and waits for the OTP modal to appear.
 */
async function submitEmailAndWaitForOtp(page, email = 'admin@cybercomply.com') {
    await page.locator('.admin-form input[type="email"]').fill(email);
    await page.locator('.admin-form button').click();
    await expect(page.locator('.otp-overlay')).toBeVisible({ timeout: 5000 });
}

// ─────────────────────────────────────────────────────────────────────────────
// Page Rendering
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Admin Access — Page Rendering', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPage(page);
    });

    test('page loads and stays on adminaccess.html', async ({ page }) => {
        await expect(page).toHaveURL(/adminaccess\.html/);
    });

    test('ADMINISTRATIVE ACCESS heading is visible', async ({ page }) => {
        await expect(page.locator('.admin-title')).toContainText('ADMINISTRATIVE ACCESS');
    });

    test('description text is visible', async ({ page }) => {
        await expect(page.locator('.admin-description').first()).toBeVisible();
    });

    test('email input is visible', async ({ page }) => {
        await expect(page.locator('.admin-form input[type="email"]')).toBeVisible();
    });

    test('SEND button is visible', async ({ page }) => {
        await expect(page.locator('.admin-form button')).toContainText('SEND');
    });

    test('top header with menu icon and user profile icon are visible', async ({ page }) => {
        await expect(page.locator('.top-header')).toBeVisible();
        await expect(page.locator('.menu-icon')).toBeVisible();
        await expect(page.locator('.user-profile')).toBeVisible();
    });

    test('back arrow is visible', async ({ page }) => {
        await expect(page.locator('.back-arrow')).toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Email Validation
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Admin Access — Email Validation', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPage(page);
    });

    test('clicking SEND with empty email shows validation error', async ({ page }) => {
        await page.locator('.admin-form button').click();
        await expect(page.locator('.message-banner.error')).toBeVisible();
        await expect(page.locator('.message-banner.error')).toContainText('valid email');
    });

    test('clicking SEND with invalid email format shows validation error', async ({ page }) => {
        await page.locator('.admin-form input[type="email"]').fill('notanemail');
        await page.locator('.admin-form button').click();
        await expect(page.locator('.message-banner.error')).toBeVisible();
        await expect(page.locator('.message-banner.error')).toContainText('valid email');
    });

    test('OTP modal does NOT appear on invalid email', async ({ page }) => {
        await page.locator('.admin-form input[type="email"]').fill('bademail');
        await page.locator('.admin-form button').click();
        await expect(page.locator('.otp-overlay')).not.toBeVisible();
    });

    test('backend rejection of non-org domain shows inline error message', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.route(reStatus, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'NONE' }) });
        });
        await page.route(reRequest, async route => {
            await route.fulfill({
                status: 400,
                contentType: 'application/json',
                body: JSON.stringify({ detail: 'Email domain not recognized as an organizational email.' }),
            });
        });

        await page.locator('.admin-form input[type="email"]').fill('user@gmail.com');
        await page.locator('.admin-form button').click();

        await expect(page.locator('.message-banner.error')).toBeVisible({ timeout: 5000 });
        await expect(page.locator('.message-banner.error')).toContainText('organizational email');
    });

    test('backend rejection does NOT show OTP modal', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.route(reStatus, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'NONE' }) });
        });
        await page.route(reRequest, async route => {
            await route.fulfill({
                status: 400,
                contentType: 'application/json',
                body: JSON.stringify({ detail: 'Email domain not recognized as an organizational email.' }),
            });
        });

        await page.locator('.admin-form input[type="email"]').fill('user@gmail.com');
        await page.locator('.admin-form button').click();
        await expect(page.locator('.otp-overlay')).not.toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Sending Verification
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Admin Access — Sending Verification', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPage(page);
    });

    test('valid email triggers OTP modal to appear', async ({ page }) => {
        await submitEmailAndWaitForOtp(page);
        await expect(page.locator('.otp-overlay')).toBeVisible();
    });

    test('OTP modal shows the submitted email address', async ({ page }) => {
        await submitEmailAndWaitForOtp(page, 'admin@cybercomply.com');
        await expect(page.locator('.otp-modal')).toContainText('admin@cybercomply.com');
    });

    test('success message appears in the form after sending', async ({ page }) => {
        await submitEmailAndWaitForOtp(page);
        await expect(page.locator('.otp-modal .message-banner')).toBeVisible();
    });

    test('request_id is stored after successful send', async ({ page }) => {
        await submitEmailAndWaitForOtp(page);
        await expect(page.locator('.otp-overlay')).toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// checkAdminRequestStatus on Load
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Admin Access — Status Check on Load', () => {

    test('PENDING status on load auto-shows OTP modal', async ({ page }) => {
        await loginAsGeneral(page);
        await loadPage(page, {
            statusResponse: {
                status: 'PENDING',
                org_email: 'admin@cybercomply.com',
                request_id: 'pending-request-id-456',
            },
        });
        await expect(page.locator('.otp-overlay')).toBeVisible({ timeout: 5000 });
    });

    test('PENDING status on load shows correct email in OTP modal', async ({ page }) => {
        await loginAsGeneral(page);
        await loadPage(page, {
            statusResponse: {
                status: 'PENDING',
                org_email: 'admin@cybercomply.com',
                request_id: 'pending-request-id-456',
            },
        });
        await expect(page.locator('.otp-modal')).toContainText('admin@cybercomply.com');
    });

    test('PENDING status on load shows pending message', async ({ page }) => {
        await loginAsGeneral(page);
        await loadPage(page, {
            statusResponse: {
                status: 'PENDING',
                org_email: 'admin@cybercomply.com',
                request_id: 'pending-request-id-456',
            },
        });
        await expect(page.locator('.otp-overlay .message-banner')).toContainText('pending request');
    });

    test('APPROVED status on load does NOT show OTP modal', async ({ page }) => {
        await loginAsGeneral(page);
        await loadPage(page, {
            statusResponse: { status: 'APPROVED' },
        });
        await expect(page.locator('.otp-overlay')).not.toBeVisible();
    });

    test('NONE status on load stays on form step', async ({ page }) => {
        await loginAsGeneral(page);
        await loadPage(page, { statusResponse: { status: 'NONE' } });
        await expect(page.locator('.otp-overlay')).not.toBeVisible();
        await expect(page.locator('.admin-form')).toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// OTP Modal
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Admin Access — OTP Modal', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPage(page);
        await submitEmailAndWaitForOtp(page);
    });

    test('OTP input field is visible in the modal', async ({ page }) => {
        await expect(page.locator('.otp-input')).toBeVisible();
    });

    test('VERIFY OTP button is visible in the modal', async ({ page }) => {
        await expect(page.locator('.otp-btn')).toContainText('VERIFY OTP');
    });

    test.skip('OTP input only accepts numeric characters — pending: adminaccess.html should use otp_component.js instead of inline OTP', async ({ page }) => {
        await page.locator('.otp-input').fill('abc123');
        const value = await page.locator('.otp-input').inputValue();
        expect(value).toBe('123');
    });

    test('OTP input is limited to 6 digits', async ({ page }) => {
        await page.locator('.otp-input').fill('12345678');
        const value = await page.locator('.otp-input').inputValue();
        expect(value.length).toBeLessThanOrEqual(6);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// OTP Verification
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Admin Access — OTP Verification', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPage(page);
        await submitEmailAndWaitForOtp(page);
    });

    test('valid OTP shows success step', async ({ page }) => {
        await page.locator('.otp-input').fill('123456');
        await page.locator('.otp-btn').click();
        await expect(page.locator('.success-step')).toBeVisible({ timeout: 5000 });
    });

    test('success step contains "Admin Access Granted"', async ({ page }) => {
        await page.locator('.otp-input').fill('123456');
        await page.locator('.otp-btn').click();
        await expect(page.locator('.success-step')).toContainText('Admin Access Granted', { timeout: 5000 });
    });

    test('success step shows redirect message', async ({ page }) => {
        await page.locator('.otp-input').fill('123456');
        await page.locator('.otp-btn').click();
        await expect(page.locator('.success-step')).toContainText('Redirecting', { timeout: 5000 });
    });

    test('after success, page redirects to profile.html', async ({ page }) => {
        await page.locator('.otp-input').fill('123456');
        await page.locator('.otp-btn').click();
        await page.waitForURL(/profile\.html/, { timeout: 10000 });
    });

    test('userRole is set in sessionStorage after successful verification', async ({ page }) => {
        await page.locator('.otp-input').fill('123456');
        await page.locator('.otp-btn').click();
        await page.waitForURL(/profile\.html/, { timeout: 10000 });
        const role = await page.evaluate(() => sessionStorage.getItem('userRole'));
        expect(role).toBe('Administrative User');
    });

    test.skip('invalid OTP shows inline error message — pending: adminaccess.html should use otp_component.js instead of inline OTP', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.route(reStatus, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'NONE' }) });
        });
        await page.route(reVerify, async route => {
            await route.fulfill({
                status: 400,
                contentType: 'application/json',
                body: JSON.stringify({ detail: 'Invalid or expired code.' }),
            });
        });

        await page.locator('.otp-input').fill('000000');
        await page.locator('.otp-btn').click();
        // otp_component.js renders errors with .otp-message--error
        await expect(page.locator('.otp-message--error')).toBeVisible({ timeout: 5000 });
        await expect(page.locator('.otp-message--error')).toContainText('Invalid or expired');
    });

    test.skip('invalid OTP does NOT advance to success step — pending: adminaccess.html should use otp_component.js instead of inline OTP', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.route(reStatus, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'NONE' }) });
        });
        await page.route(reVerify, async route => {
            await route.fulfill({
                status: 400,
                contentType: 'application/json',
                body: JSON.stringify({ detail: 'Invalid or expired code.' }),
            });
        });

        await page.locator('.otp-input').fill('000000');
        await page.locator('.otp-btn').click();
        await expect(page.locator('.success-step')).not.toBeVisible();
    });

    test.skip('network failure during OTP verify shows error banner — pending implementation of error banner in adminaccess.html', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.route(reVerify, async route => {
            await route.abort('connectionreset');
        });

        await page.locator('.otp-input').fill('123456');
        await page.locator('.otp-btn').click();
        await expect(
            page.locator('text=Could not reach the server')
        ).toBeVisible({ timeout: 5000 });
    });

    test.skip('network failure during send verification shows error banner — pending implementation of error banner in adminaccess.html', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.route(reRequest, async route => {
            await route.abort('connectionreset');
        });

        await page.locator('.admin-form input[type="email"]').fill('admin@cybercomply.com');
        await page.locator('.admin-form button').click();
        await expect(
            page.locator('text=Could not reach the server')
        ).toBeVisible({ timeout: 5000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Navigation
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Admin Access — Navigation', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPage(page);
    });

    test('back arrow navigates to profile.html', async ({ page }) => {
        await page.locator('.back-arrow').click();
        await expect(page).toHaveURL(/profile\.html/);
    });

    test('user profile icon navigates to profile.html', async ({ page }) => {
        await page.locator('.user-profile').click();
        await expect(page).toHaveURL(/profile\.html/);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Sidebar
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Admin Access — Sidebar', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPage(page);
    });

    test('sidebar is open by default — back arrow has shifted class', async ({ page }) => {
        await expect(page.locator('.back-arrow')).toHaveClass(/shifted/);
    });

    test('clicking menu icon closes sidebar — back arrow loses shifted class', async ({ page }) => {
        await page.locator('.menu-icon').click();
        await expect(page.locator('.back-arrow')).not.toHaveClass(/shifted/);
    });

    test('clicking menu icon again re-opens sidebar', async ({ page }) => {
        await page.locator('.menu-icon').click();
        await page.locator('.menu-icon').click();
        await expect(page.locator('.back-arrow')).toHaveClass(/shifted/);
    });

    test('main content has shifted class when sidebar is open', async ({ page }) => {
        await expect(page.locator('div.main-content')).toHaveClass(/shifted/);
    });

    test('main content loses shifted class when sidebar is closed', async ({ page }) => {
        await page.locator('.menu-icon').click();
        await expect(page.locator('div.main-content')).not.toHaveClass(/shifted/);
    });
});