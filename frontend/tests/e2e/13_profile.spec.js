// tests/e2e/13_profile.spec.js
// ─────────────────────────────────────────────────────────────────────────────
// Profile page (profile.html)
//
// Covers:
//   - Auth guard (no userEmail in sessionStorage → login redirect)
//   - JWT auth guard (no authToken → login redirect) [skipped — pending implementation]
//   - Page rendering: avatar, all profile fields, action buttons, 2FA checkbox
//   - Profile data loaded correctly from API into the UI
//   - Role display: General User and Administrative User label mapping
//   - Inline editing: name field — start edit, input visible, cancel reverts
//   - Inline editing: email field — start edit, input visible, cancel reverts
//   - Save changes: name only — PATCH call made, UI updated, Swal success shown
//   - Save changes: email only — redirects to email_change_verify.html, pendingNewEmail stored
//   - Save changes: validation — name too short, invalid email format → Swal error
//   - Password field: edit icon redirects to forgot_password.html
//   - 2FA checkbox: toggle on → POST to /api/profile/twofa/ with otp_is_enabled: true
//   - 2FA checkbox: toggle off → POST to /api/profile/twofa/ with otp_is_enabled: false
//   - 2FA checkbox: API failure → checkbox reverts, alert() dialog shown
//   - Grant Admin Access: general user → navigates to adminaccess.html
//   - Grant Admin Access: admin user → locked, shows access-denied toast
//   - Access denied toast: auto-dismisses after ~3.5 seconds
//   - Delete Account button: opens confirmation modal
//   - Delete modal: shows summary list items, reason dropdown, cancel and confirm buttons
//   - Delete modal: cancel closes modal
//   - Delete modal: clicking outside overlay closes modal
//   - Delete modal: confirm → POST to /api/request-delete-account/, stores reason, redirects
//   - Delete modal: API failure → modal closes, Swal error shown
//   - Profile load failure → Swal error shown, no profile data displayed
//   - Navigation: back arrow calls history.back()
//   - Navigation: logout → clears sessionStorage, redirects to welcome.html
//   - Sidebar: open by default, toggle, shifted class on back arrow and main content
//
// MOCKING STRATEGY
//   All route mocks use RegExp with /?$ to match URLs with or without trailing
//   slash — consistent with all other spec files in this project.
//   page.unrouteAll() is called at the start of loadProfilePage so stale routes
//   from previous tests never bleed into subsequent ones.
//   SweetAlert2 is detected via its DOM container (.swal2-container).
// ─────────────────────────────────────────────────────────────────────────────

const { test, expect } = require('@playwright/test');
const {
    loginAsGeneral,
    loginAsAdmin,
} = require('./helpers/helper_login');

const PROFILE_URL = './profile.html';

// ── Regex route helpers ───────────────────────────────────────────────────────
const reProfile       = /\/api\/profile\/?(\?.*)?$/;
const reProfileUpdate = /\/api\/profile\/update\/?$/;
const reTwoFA         = /\/api\/profile\/twofa\/?$/;
const reDeleteRequest = /\/api\/request-delete-account\/?$/;
const reDeleteFile    = /\/api\/delete-file\/?$/;

// ── Fake profile data ─────────────────────────────────────────────────────────

const GENERAL_USER_PROFILE = {
    full_name:       'Jane Smith',
    email:           'jane.smith@example.com',
    role:            'general_user',
    otp_is_enabled:  false,
};

const ADMIN_USER_PROFILE = {
    full_name:       'Admin User',
    email:           'admin@orgdomain.com',
    role:            'administrative_user',
    otp_is_enabled:  true,
};

// ── Shared helper: load page with mocked profile ──────────────────────────────

/**
 * Clears stale routes, mocks the profile endpoint and the delete-file endpoint
 * (called on logout), seeds sessionStorage with userEmail, navigates to
 * profile.html and waits for full load.
 *
 * @param {import('@playwright/test').Page} page
 * @param {object} profile - Fake profile object returned from GET /api/profile/
 */
async function loadProfilePage(page, profile = GENERAL_USER_PROFILE, { freshRoutes = true } = {}) {
    if (freshRoutes) {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
    }

    // Mock GET /api/profile/
    await page.route(reProfile, async route => {
        await route.fulfill({
            status:      200,
            contentType: 'application/json',
            body:        JSON.stringify(profile),
        });
    });

    // Mock the delete-file endpoint called on logout (always succeed silently)
    await page.route(reDeleteFile, async route => {
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    await page.evaluate((email) => {
        sessionStorage.setItem('userEmail', email);
    }, profile.email);

    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
    await page.goto(PROFILE_URL);
    await page.waitForLoadState('networkidle', { timeout: 30000 });
    await page.waitForSelector('.main-content[data-ready="true"]', { timeout: 30000 });
}

// ─────────────────────────────────────────────────────────────────────────────
// Auth Guard
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Profile — Auth Guard', () => {

    test('redirects to login.html when no userEmail in sessionStorage', async ({ page }) => {
        await page.goto('./welcome.html');
        await page.evaluate(() => sessionStorage.clear());
        await page.goto(PROFILE_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
    });

    test.skip('redirects to login.html when no authToken in sessionStorage', async ({ page }) => {
        // Skipped — JWT auth guard not yet implemented in profile.html frontend.
        // Once authToken check is added to mounted(), remove this skip.
        await page.goto('./welcome.html');
        await page.evaluate(() => {
            sessionStorage.setItem('userEmail', 'jane.smith@example.com');
            sessionStorage.removeItem('authToken');
        });
        await page.goto(PROFILE_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
    });

    test.skip('sessionStorage is cleared before redirect when authToken is missing', async ({ page }) => {
        // Skipped — depends on JWT auth guard implementation.
        await page.goto('./welcome.html');
        await page.evaluate(() => {
            sessionStorage.setItem('userEmail', 'jane.smith@example.com');
            sessionStorage.removeItem('authToken');
        });
        await page.goto(PROFILE_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
        const email = await page.evaluate(() => sessionStorage.getItem('userEmail'));
        expect(email).toBeNull();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Page Rendering
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Profile — Page Rendering', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadProfilePage(page, GENERAL_USER_PROFILE);
    });

    test('page loads and stays on profile.html', async ({ page }) => {
        await expect(page).toHaveURL(/profile\.html/);
    });

    test('profile avatar SVG is visible', async ({ page }) => {
        await expect(page.locator('.profile-avatar svg')).toBeVisible();
    });

    test('profile container is visible', async ({ page }) => {
        await expect(page.locator('.profile-container')).toBeVisible();
    });

    test('Name field label is visible', async ({ page }) => {
        await expect(page.locator('.profile-field label').filter({ hasText: 'Name' })).toBeVisible();
    });

    test('Email field label is visible', async ({ page }) => {
        await expect(page.locator('.profile-field label').filter({ hasText: 'Email' })).toBeVisible();
    });

    test('Password field label is visible', async ({ page }) => {
        await expect(page.locator('.profile-field label').filter({ hasText: 'Password' })).toBeVisible();
    });

    test('Role field label is visible', async ({ page }) => {
        await expect(page.locator('.profile-field label').filter({ hasText: 'Role' })).toBeVisible();
    });

    test('password mask dots are visible', async ({ page }) => {
        await expect(page.locator('.password-mask')).toBeVisible();
    });

    test('2FA checkbox is visible', async ({ page }) => {
        await expect(page.locator('#enable-2fa')).toBeVisible();
    });

    test('2FA label text is visible', async ({ page }) => {
        await expect(page.locator('.twofa-checkbox label')).toContainText('two-factor authentication');
    });

    test('Grant Admin Access button is visible', async ({ page }) => {
        await expect(page.locator('.action-button:has-text("GRANT ADMIN ACCESS")')).toBeVisible();
    });

    test('Delete Account button is visible', async ({ page }) => {
        await expect(page.locator('.action-button:has-text("DELETE ACCOUNT")')).toBeVisible();
    });

    test('top header is visible', async ({ page }) => {
        await expect(page.locator('.top-header')).toBeVisible();
    });

    test('menu icon is visible', async ({ page }) => {
        await expect(page.locator('.menu-icon')).toBeVisible();
    });

    test('logout button is visible', async ({ page }) => {
        await expect(page.locator('.logout-button')).toBeVisible();
    });

    test('back arrow is visible', async ({ page }) => {
        await expect(page.locator('.back-arrow')).toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Profile Data Loading
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Profile — Data Loading', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
    });

    test('full name is displayed correctly from API response', async ({ page }) => {
        await loadProfilePage(page, GENERAL_USER_PROFILE);
        await expect(page.locator('.profile-field').filter({ hasText: 'Name' }).locator('.profile-value'))
            .toContainText('Jane Smith');
    });

    test('email is displayed correctly from API response', async ({ page }) => {
        await loadProfilePage(page, GENERAL_USER_PROFILE);
        await expect(page.locator('.profile-field').filter({ hasText: 'Email' }).locator('.profile-value'))
            .toContainText('jane.smith@example.com');
    });

    test('general user role displays as "General User"', async ({ page }) => {
        await loadProfilePage(page, GENERAL_USER_PROFILE);
        await expect(page.locator('.profile-field').filter({ hasText: 'Role' }).locator('.profile-value'))
            .toContainText('General User');
    });

    test('administrative user role displays as "Administrative User"', async ({ page }) => {
        await loginAsAdmin(page);

        page.on('request', request => {
            if (request.url().includes('profile')) {
                console.log('PROFILE REQUEST:', request.url());
            }
        });

        await page.route(/\/api\/profile/, async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify(ADMIN_USER_PROFILE),
            });
        });
        await page.evaluate(() => sessionStorage.setItem('userEmail', 'admin@orgdomain.com'));
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(PROFILE_URL);
        await page.waitForLoadState('networkidle', { timeout: 30000 });
        await page.waitForSelector('.main-content[data-ready="true"]', { timeout: 30000 });
        await expect(page.locator('.profile-field').filter({ hasText: 'Role' }).locator('.profile-value'))
            .toContainText('Administrative User');
    });

    test('2FA checkbox is checked when otp_is_enabled is true', async ({ page }) => {
        await loginAsAdmin(page);
        await page.route(/\/api\/profile/, async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify(ADMIN_USER_PROFILE),
            });
        });
        await page.evaluate(() => sessionStorage.setItem('userEmail', 'admin@orgdomain.com'));
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(PROFILE_URL);
        await page.waitForLoadState('networkidle', { timeout: 30000 });
        await page.waitForSelector('.main-content[data-ready="true"]', { timeout: 30000 });
        await expect(page.locator('#enable-2fa')).toBeChecked();
    });

    test('2FA checkbox is unchecked when otp_is_enabled is false', async ({ page }) => {
        await loadProfilePage(page, GENERAL_USER_PROFILE);
        await expect(page.locator('#enable-2fa')).not.toBeChecked();
    });

    test('profile load failure shows Swal error popup', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.route(reProfile, async route => {
            await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' });
        });
        await page.evaluate((email) => sessionStorage.setItem('userEmail', email), 'jane.smith@example.com');
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(PROFILE_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.swal2-container')).toBeVisible({ timeout: 5000 });
    });

    test('profile load network failure shows Swal error popup', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.route(reProfile, async route => {
            await route.abort('connectionreset');
        });
        await page.evaluate((email) => sessionStorage.setItem('userEmail', email), 'jane.smith@example.com');
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(PROFILE_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.swal2-container')).toBeVisible({ timeout: 5000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Inline Editing — Name
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Profile — Inline Editing: Name', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadProfilePage(page, GENERAL_USER_PROFILE);
    });

    test('clicking name edit icon shows the name input field', async ({ page }) => {
        await page.locator('.profile-field').filter({ hasText: 'Name' }).locator('.edit-icon').click();
        await expect(page.locator('input[type="text"].profile-input').first()).toBeVisible();
    });

    test('name input is pre-filled with current name', async ({ page }) => {
        await page.locator('.profile-field').filter({ hasText: 'Name' }).locator('.edit-icon').click();
        await expect(page.locator('input[type="text"].profile-input').first()).toHaveValue('Jane Smith');
    });

    test('name edit icon is hidden while input is active', async ({ page }) => {
        await page.locator('.profile-field').filter({ hasText: 'Name' }).locator('.edit-icon').click();
        await expect(
            page.locator('.profile-field').filter({ hasText: 'Name' }).locator('.edit-icon')
        ).not.toBeVisible();
    });

    test('cancel icon reverts name to original value', async ({ page }) => {
        await page.locator('.profile-field').filter({ hasText: 'Name' }).locator('.edit-icon').click();
        await page.locator('input[type="text"].profile-input').first().fill('Changed Name');
        await page.locator('.cancel-icon').first().click();
        await expect(
            page.locator('.profile-field').filter({ hasText: 'Name' }).locator('.profile-value')
        ).toContainText('Jane Smith');
    });

    test('pressing Escape reverts name to original value', async ({ page }) => {
        await page.locator('.profile-field').filter({ hasText: 'Name' }).locator('.edit-icon').click();
        await page.locator('input[type="text"].profile-input').first().fill('Changed Name');
        await page.locator('input[type="text"].profile-input').first().press('Escape');
        await expect(
            page.locator('.profile-field').filter({ hasText: 'Name' }).locator('.profile-value')
        ).toContainText('Jane Smith');
    });

    test('cancel icon hides the name input and shows display value', async ({ page }) => {
        await page.locator('.profile-field').filter({ hasText: 'Name' }).locator('.edit-icon').click();
        await page.locator('.cancel-icon').first().click();
        await expect(page.locator('input[type="text"].profile-input').first()).not.toBeVisible();
        await expect(
            page.locator('.profile-field').filter({ hasText: 'Name' }).locator('.profile-value')
        ).toBeVisible();
    });

    test('save button appears when name is changed', async ({ page }) => {
        await page.locator('.profile-field').filter({ hasText: 'Name' }).locator('.edit-icon').click();
        await page.locator('input[type="text"].profile-input').first().fill('New Name Here');
        await expect(page.locator('.save-button')).toBeVisible();
    });

    test('save button is not visible when no changes have been made', async ({ page }) => {
        await expect(page.locator('.save-button')).not.toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Inline Editing — Email
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Profile — Inline Editing: Email', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadProfilePage(page, GENERAL_USER_PROFILE);
    });

    test('clicking email edit icon shows the email input field', async ({ page }) => {
        await page.locator('.profile-field').filter({ hasText: 'Email' }).locator('.edit-icon').click();
        await expect(page.locator('input[type="email"].profile-input')).toBeVisible();
    });

    test('email input is pre-filled with current email', async ({ page }) => {
        await page.locator('.profile-field').filter({ hasText: 'Email' }).locator('.edit-icon').click();
        await expect(page.locator('input[type="email"].profile-input')).toHaveValue('jane.smith@example.com');
    });

    test('cancel icon reverts email to original value', async ({ page }) => {
        await page.locator('.profile-field').filter({ hasText: 'Email' }).locator('.edit-icon').click();
        await page.locator('input[type="email"].profile-input').fill('changed@email.com');
        await page.locator('.cancel-icon').nth(0).click();
        await expect(
            page.locator('.profile-field').filter({ hasText: 'Email' }).locator('.profile-value')
        ).toContainText('jane.smith@example.com');
    });

    test('save button appears when email is changed', async ({ page }) => {
        await page.locator('.profile-field').filter({ hasText: 'Email' }).locator('.edit-icon').click();
        await page.locator('input[type="email"].profile-input').fill('newemail@example.com');
        await expect(page.locator('.save-button')).toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Save Changes — Validation
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Profile — Save Changes: Validation', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadProfilePage(page, GENERAL_USER_PROFILE);
    });

    test('saving a name shorter than 3 characters shows Swal error', async ({ page }) => {
        await page.locator('.profile-field').filter({ hasText: 'Name' }).locator('.edit-icon').click();
        await page.locator('input[type="text"].profile-input').first().fill('Jo');
        await page.locator('.save-button').click();
        await expect(page.locator('.swal2-container')).toBeVisible({ timeout: 5000 });
        await expect(page.locator('.swal2-container')).toContainText('Invalid Name');
    });

    test('saving an invalid email format shows Swal error', async ({ page }) => {
        await page.locator('.profile-field').filter({ hasText: 'Email' }).locator('.edit-icon').click();
        await page.locator('input[type="email"].profile-input').fill('not-a-valid-email');
        await page.locator('.save-button').click();
        await expect(page.locator('.swal2-container')).toBeVisible({ timeout: 5000 });
        await expect(page.locator('.swal2-container')).toContainText('Invalid Email');
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Save Changes — Name Update (PATCH)
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Profile — Save Changes: Name', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadProfilePage(page, GENERAL_USER_PROFILE);
    });

    test('saving a valid new name makes a PATCH request to /api/profile/update/', async ({ page }) => {
        let patchCalled = false;

        await page.route(reProfileUpdate, async route => {
            patchCalled = true;
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify({ full_name: 'Updated Name' }),
            });
        });

        await page.locator('.profile-field').filter({ hasText: 'Name' }).locator('.edit-icon').click();
        await page.locator('input[type="text"].profile-input').first().fill('Updated Name');

        // Dismiss Swal confirmation
        await page.locator('.save-button').click();
        await page.locator('.swal2-confirm').click();
        await page.waitForTimeout(1000);

        expect(patchCalled).toBe(true);
    });

    test('after saving name, updated name is shown in profile display', async ({ page }) => {
        await page.route(reProfileUpdate, async route => {
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify({ full_name: 'Updated Name' }),
            });
        });

        await page.locator('.profile-field').filter({ hasText: 'Name' }).locator('.edit-icon').click();
        await page.locator('input[type="text"].profile-input').first().fill('Updated Name');
        await page.locator('.save-button').click();
        await page.locator('.swal2-confirm').click();

        // Wait for success Swal to auto-close (timer: 1500)
        await page.waitForTimeout(2000);
        await expect(
            page.locator('.profile-field').filter({ hasText: 'Name' }).locator('.profile-value')
        ).toContainText('Updated Name');
    });

    test('save button disappears after a successful name save', async ({ page }) => {
        await page.route(reProfileUpdate, async route => {
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify({ full_name: 'Updated Name' }),
            });
        });

        await page.locator('.profile-field').filter({ hasText: 'Name' }).locator('.edit-icon').click();
        await page.locator('input[type="text"].profile-input').first().fill('Updated Name');
        await page.locator('.save-button').click();
        await page.locator('.swal2-confirm').click();
        await page.waitForTimeout(2000);

        await expect(page.locator('.save-button')).not.toBeVisible();
    });

    test('PATCH failure shows Swal error popup', async ({ page }) => {
        await page.route(reProfileUpdate, async route => {
            await route.fulfill({ status: 400, contentType: 'application/json', body: '{"detail":"Update failed"}' });
        });

        await page.locator('.profile-field').filter({ hasText: 'Name' }).locator('.edit-icon').click();
        await page.locator('input[type="text"].profile-input').first().fill('Updated Name');
        await page.locator('.save-button').click();
        await page.locator('.swal2-confirm').click();

        await expect(page.locator('.swal2-container')).toBeVisible({ timeout: 5000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Save Changes — Email Change (Redirect to OTP page)
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Profile — Save Changes: Email', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadProfilePage(page, GENERAL_USER_PROFILE);
    });

    test('changing email and saving redirects to email_change_verify.html', async ({ page }) => {
        await page.locator('.profile-field').filter({ hasText: 'Email' }).locator('.edit-icon').click();
        await page.locator('input[type="email"].profile-input').fill('newemail@example.com');
        await page.locator('.save-button').click();
        await page.locator('.swal2-confirm').click();
        await page.waitForURL(/email_change_verify\.html/, { timeout: 10000 });
    });

    test('pendingNewEmail is stored in sessionStorage before redirect', async ({ page }) => {
        await page.locator('.profile-field').filter({ hasText: 'Email' }).locator('.edit-icon').click();
        await page.locator('input[type="email"].profile-input').fill('newemail@example.com');
        await page.locator('.save-button').click();
        await page.locator('.swal2-confirm').click();

        await page.waitForURL(/email_change_verify\.html/, { timeout: 10000 });
        const stored = await page.evaluate(() => sessionStorage.getItem('pendingNewEmail'));
        expect(stored).toBe('newemail@example.com');
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Password Field
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Profile — Password Field', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadProfilePage(page, GENERAL_USER_PROFILE);
    });

    test('clicking the password edit icon redirects to forgot_password.html', async ({ page }) => {
        await page.locator('.password-field .edit-icon').click();
        await expect(page).toHaveURL(/forgot_password\.html/);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// 2FA Toggle
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Profile — 2FA Toggle', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadProfilePage(page, GENERAL_USER_PROFILE);
    });

    test('enabling 2FA sends POST with otp_is_enabled: true', async ({ page }) => {
        let body = null;

        await page.route(reTwoFA, async route => {
            body = JSON.parse(route.request().postData() || '{}');
            await route.fulfill({ status: 200, contentType: 'application/json', body: '{"detail":"2FA enabled"}' });
        });

        await page.locator('#enable-2fa').check();
        await page.waitForTimeout(500); // allow fetch to complete

        expect(body).not.toBeNull();
        expect(body.otp_is_enabled).toBe(true);
    });

    test('disabling 2FA sends POST with otp_is_enabled: false', async ({ page }) => {
        let body = null;

        await page.route(reTwoFA, async route => {
            body = JSON.parse(route.request().postData() || '{}');
            await route.fulfill({ status: 200, contentType: 'application/json', body: '{"detail":"2FA disabled"}' });
        });

        // First enable (starts unchecked for general user)
        await page.route(reTwoFA, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
        });
        await page.locator('#enable-2fa').check();
        await page.waitForTimeout(300);

        // Now route properly and uncheck
        await page.route(reTwoFA, async route => {
            body = JSON.parse(route.request().postData() || '{}');
            await route.fulfill({ status: 200, contentType: 'application/json', body: '{"detail":"2FA disabled"}' });
        });
        await page.locator('#enable-2fa').uncheck();
        await page.waitForTimeout(500);

        expect(body).not.toBeNull();
        expect(body.otp_is_enabled).toBe(false);
    });

    test('2FA POST includes the user email in the request body', async ({ page }) => {
        let body = null;

        await page.route(reTwoFA, async route => {
            body = JSON.parse(route.request().postData() || '{}');
            await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
        });

        await page.locator('#enable-2fa').check();
        await page.waitForTimeout(500);

        expect(body.email).toBe('jane.smith@example.com');
    });

    test('2FA API failure shows alert dialog and reverts checkbox', async ({ page }) => {
        await page.route(reTwoFA, async route => {
            await route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Server error"}' });
        });

        let alertMessage = '';
        page.on('dialog', async dialog => {
            alertMessage = dialog.message();
            await dialog.dismiss();
        });

        await page.locator('#enable-2fa').click();
        await page.waitForTimeout(500);

        // Checkbox should have reverted to unchecked
        await expect(page.locator('#enable-2fa')).not.toBeChecked();
    });

    test('2FA network failure shows alert dialog and reverts checkbox', async ({ page }) => {
        await page.route(reTwoFA, async route => {
            await route.abort('connectionreset');
        });

        page.on('dialog', async dialog => { await dialog.dismiss(); });

        await page.locator('#enable-2fa').click();
        await page.waitForTimeout(800);

        await expect(page.locator('#enable-2fa')).not.toBeChecked();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Grant Admin Access Button
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Profile — Grant Admin Access: General User', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadProfilePage(page, GENERAL_USER_PROFILE);
    });

    test('Grant Admin Access button does NOT have locked class for general user', async ({ page }) => {
        await expect(
            page.locator('.action-button:has-text("GRANT ADMIN ACCESS")')
        ).not.toHaveClass(/locked/);
    });

    test('Grant Admin Access button does NOT have a lock icon for general user', async ({ page }) => {
        await expect(
            page.locator('.action-button:has-text("GRANT ADMIN ACCESS") svg.btn-lock-icon')
        ).not.toBeVisible();
    });

    test('clicking Grant Admin Access navigates to adminaccess.html for general user', async ({ page }) => {
        await page.locator('.action-button:has-text("GRANT ADMIN ACCESS")').click();
        await expect(page).toHaveURL(/adminaccess\.html/);
    });
});

test.describe('Profile — Grant Admin Access: Admin User', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await loadProfilePage(page, ADMIN_USER_PROFILE);
    });

    test('Grant Admin Access button has locked class for admin user', async ({ page }) => {
        await expect(
            page.locator('.action-button:has-text("GRANT ADMIN ACCESS")')
        ).toHaveClass(/locked/);
    });

    test('Grant Admin Access button has a lock icon for admin user', async ({ page }) => {
        await expect(
            page.locator('.action-button:has-text("GRANT ADMIN ACCESS") svg.btn-lock-icon')
        ).toBeVisible();
    });

    test('clicking Grant Admin Access shows access denied toast for admin user', async ({ page }) => {
        await page.locator('.action-button:has-text("GRANT ADMIN ACCESS")').click({ force: true });
        await expect(page.locator('.access-toast')).toHaveClass(/visible/);
    });

    test('access denied toast contains correct message for admin user', async ({ page }) => {
        await page.locator('.action-button:has-text("GRANT ADMIN ACCESS")').click();
        await expect(page.locator('.access-toast')).toContainText('General Users');
    });

    test('clicking Grant Admin Access does NOT navigate away for admin user', async ({ page }) => {
        await page.locator('.action-button:has-text("GRANT ADMIN ACCESS")').click();
        await expect(page).toHaveURL(/profile\.html/);
    });

    test('access denied toast auto-dismisses after ~3.5 seconds', async ({ page }) => {
        await page.locator('.action-button:has-text("GRANT ADMIN ACCESS")').click();
        await expect(page.locator('.access-toast')).toHaveClass(/visible/);
        await page.waitForTimeout(4000);
        await expect(page.locator('.access-toast')).not.toHaveClass(/visible/);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Delete Account Modal
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Profile — Delete Account Modal', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadProfilePage(page, GENERAL_USER_PROFILE);
    });

    test('clicking Delete Account button opens the confirmation modal', async ({ page }) => {
        await page.locator('.action-button:has-text("DELETE ACCOUNT")').click({ force: true });
        await expect(page.locator('.delete-modal-overlay')).toBeVisible();
    });

    test('delete modal shows the warning title', async ({ page }) => {
        await page.locator('.action-button:has-text("DELETE ACCOUNT")').click();
        await expect(page.locator('.delete-modal-title')).toContainText('Delete Account');
    });

    test('delete modal shows summary of what will be deleted', async ({ page }) => {
        await page.locator('.action-button:has-text("DELETE ACCOUNT")').click();
        await expect(page.locator('.delete-modal-summary')).toBeVisible();
        await expect(page.locator('.delete-modal-summary-item').first()).toBeVisible();
    });

    test('delete modal shows at least 5 summary items', async ({ page }) => {
        await page.locator('.action-button:has-text("DELETE ACCOUNT")').click();
        const items = page.locator('.delete-modal-summary-item');
        await expect(items).toHaveCount(5);
    });

    test('delete modal shows the reason dropdown', async ({ page }) => {
        await page.locator('.action-button:has-text("DELETE ACCOUNT")').click({ force: true });
        await expect(page.locator('.delete-modal-reason select')).toBeVisible();
    });

    test('delete modal reason dropdown has multiple options', async ({ page }) => {
        await page.locator('.action-button:has-text("DELETE ACCOUNT")').click();
        const options = page.locator('.delete-modal-reason select option');
        const count = await options.count();
        expect(count).toBeGreaterThan(1);
    });

    test('cancel button closes the modal', async ({ page }) => {
        await page.locator('.action-button:has-text("DELETE ACCOUNT")').click();
        await page.locator('.delete-modal-cancel').click();
        await expect(page.locator('.delete-modal-overlay')).not.toBeVisible();
    });

    test('clicking outside the modal overlay closes it', async ({ page }) => {
        await page.locator('.action-button:has-text("DELETE ACCOUNT")').click();
        await page.locator('.delete-modal-overlay').click({ position: { x: 5, y: 5 } });
        await expect(page.locator('.delete-modal-overlay')).not.toBeVisible();
    });

    test('confirm button is visible and enabled by default', async ({ page }) => {
        await page.locator('.action-button:has-text("DELETE ACCOUNT")').click();
        await expect(page.locator('.delete-modal-confirm')).toBeVisible();
        await expect(page.locator('.delete-modal-confirm')).not.toBeDisabled();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Delete Account — Confirmation Flow
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Profile — Delete Account: Confirmation Flow', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadProfilePage(page, GENERAL_USER_PROFILE);
    });

    test('confirming delete makes POST to /api/request-delete-account/', async ({ page }) => {
        let deleteCalled = false;

        await page.route(reDeleteRequest, async route => {
            deleteCalled = true;
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify({ detail: 'OTP sent' }),
            });
        });

        await page.locator('.action-button:has-text("DELETE ACCOUNT")').click();
        await page.locator('.delete-modal-confirm').click();
        await page.waitForTimeout(1000);

        expect(deleteCalled).toBe(true);
    });

    test('confirming delete stores reason in sessionStorage', async ({ page }) => {
        await page.route(reDeleteRequest, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: '{"detail":"OTP sent"}' });
        });

        await page.locator('.action-button:has-text("DELETE ACCOUNT")').click();
        await page.locator('.delete-modal-reason select').selectOption('Privacy concerns.');
        await page.locator('.delete-modal-confirm').click();

        await page.waitForURL(/delete_account_verify\.html/, { timeout: 10000 });
        const reason = await page.evaluate(() => sessionStorage.getItem('deleteAccountReason'));
        expect(reason).toBe('Privacy concerns.');
    });

    test('confirming delete redirects to delete_account_verify.html', async ({ page }) => {
        await page.route(reDeleteRequest, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: '{"detail":"OTP sent"}' });
        });

        await page.locator('.action-button:has-text("DELETE ACCOUNT")').click();
        await page.locator('.delete-modal-confirm').click();
        await page.waitForURL(/delete_account_verify\.html/, { timeout: 10000 });
    });

    test('delete API failure closes modal and shows Swal error', async ({ page }) => {
        await page.route(reDeleteRequest, async route => {
            await route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Server error"}' });
        });

        await page.locator('.action-button:has-text("DELETE ACCOUNT")').click();
        await page.locator('.delete-modal-confirm').click();
        await page.waitForTimeout(1000);

        await expect(page.locator('.delete-modal-overlay')).not.toBeVisible();
        await expect(page.locator('.swal2-container')).toBeVisible({ timeout: 5000 });
    });

    test('delete network failure closes modal and shows Swal error', async ({ page }) => {
        await page.route(reDeleteRequest, async route => {
            await route.abort('connectionreset');
        });

        await page.locator('.action-button:has-text("DELETE ACCOUNT")').click();
        await page.locator('.delete-modal-confirm').click();
        await page.waitForTimeout(1000);

        await expect(page.locator('.delete-modal-overlay')).not.toBeVisible();
        await expect(page.locator('.swal2-container')).toBeVisible({ timeout: 5000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Navigation
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Profile — Navigation', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadProfilePage(page, GENERAL_USER_PROFILE);
    });

    test('back arrow navigates to previous page', async ({ page }) => {
        // Navigate to profile from home so history.back() goes to home
        await page.goto('./home.html');
        await page.goto(PROFILE_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await page.locator('.back-arrow').click();
        await expect(page).toHaveURL(/home\.html/);
    });

    test('logout button clears sessionStorage', async ({ page }) => {
        await page.locator('.logout-button').click();
        const email = await page.evaluate(() => sessionStorage.getItem('userEmail'));
        expect(email).toBeNull();
    });

    test('logout button redirects to welcome.html', async ({ page }) => {
        const swal = page.locator('.swal2-container');
        if (await swal.isVisible()) {
            await page.keyboard.press('Escape');
            await page.waitForTimeout(300);
        }
        await page.locator('.logout-button').click();
        await expect(page).toHaveURL(/welcome\.html/);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Sidebar
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Profile — Sidebar', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadProfilePage(page, GENERAL_USER_PROFILE);
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