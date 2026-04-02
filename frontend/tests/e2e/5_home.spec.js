// tests/e2e/home.spec.js
// ─────────────────────────────────────────────────────────────────────────────
// Home page (home.html)
// Covers: unauthenticated access guard (redirects to login/welcome),
// authenticated access as general user, authenticated access as admin,
// and sessionStorage state after login.
//
// We do NOT test the full home page UI here (document upload, analysis, etc.)
// — those belong in separate feature specs once auth is solid.
// ─────────────────────────────────────────────────────────────────────────────

const { test, expect } = require('@playwright/test');
const {
    loginAsGeneral,
    loginAsAdmin,
    GENERAL_EMAIL,
    ADMIN_EMAIL,
} = require('./helpers/helper_login');

const HOME_URL = './home.html';

// ─────────────────────────────────────────────────────────────────────────────
// Access Guard — unauthenticated
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Home Page — Access Guard (Unauthenticated)', () => {

    test('navigating directly to home.html without login redirects away from home', async ({ page }) => {
        // Clear any leftover session data
        await page.goto('./welcome.html');
        await page.evaluate(() => {
            sessionStorage.clear();
            localStorage.clear();
        });

        await page.goto(HOME_URL);

        // The page should redirect to login or welcome — NOT stay on home.html
        await page.waitForURL(url =>
            url.href.includes('login.html') || url.href.includes('welcome.html'),
            { timeout: 10000 }
        );
    });

    test('home.html without authToken in sessionStorage does not show protected content', async ({ page }) => {
        await page.goto('./welcome.html');
        await page.evaluate(() => {
            sessionStorage.clear();
            localStorage.clear();
        });

        await page.goto(HOME_URL);
        // After the guard fires the user should not see a "Log Out" or main dashboard element
        // (they've been redirected). Confirm we're off home.html.
        await expect(page).not.toHaveURL(/home\.html/);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Authenticated — General User
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Home Page — General User', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
    });

    test('lands on home.html after login', async ({ page }) => {
        await expect(page).toHaveURL(/home\.html/);
    });

    test('sessionStorage contains authToken after login', async ({ page }) => {
        // Wait for all network requests to finish — including the session-token fetch
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        const token = await page.evaluate(() => sessionStorage.getItem('authToken'));
        expect(token).toBeTruthy();
        expect(token.length).toBeGreaterThan(10);
    });

    test('sessionStorage contains correct userEmail after login', async ({ page }) => {
        const email = await page.evaluate(() => sessionStorage.getItem('userEmail'));
        expect(email).toBe(GENERAL_EMAIL);
    });

    test('sessionStorage contains userRole after login', async ({ page }) => {
        const role = await page.evaluate(() => sessionStorage.getItem('userRole'));
        expect(role).toBeTruthy(); // GENERAL_USER or ADMINISTRATIVE_USER
    });

    test('sessionStorage contains userFullName after login', async ({ page }) => {
        const name = await page.evaluate(() => sessionStorage.getItem('userFullName'));
        expect(name).toBeTruthy();
    });

    test('home.html is rendered (page does not immediately redirect away)', async ({ page }) => {
        // Wait for the profile API call to complete — give it enough time
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page).toHaveURL(/home\.html/);
    });

    test('home page body is visible and not blank', async ({ page }) => {
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        const app = page.locator('#app');
        await expect(app).toBeVisible();
        const content = await app.innerText();
        expect(content.trim().length).toBeGreaterThan(0);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Authenticated — Admin User
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Home Page — Admin User', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
    });

    test('admin lands on home.html after login', async ({ page }) => {
        await expect(page).toHaveURL(/home\.html/);
    });

    test('sessionStorage userRole is ADMINISTRATIVE_USER for admin', async ({ page }) => {
        const role = await page.evaluate(() => sessionStorage.getItem('userRole'));
        expect(role).toBe('ADMINISTRATIVE_USER');
    });

    test('sessionStorage userEmail is correct for admin', async ({ page }) => {
        // Admin beforeEach uses loginAsAdmin — wait for home to fully mount
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        const email = await page.evaluate(() => sessionStorage.getItem('userEmail'));
        expect(email).toBe(ADMIN_EMAIL);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Session Token Integrity
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Home Page — Session Token Integrity', () => {

    test('authToken is a non-empty string after general login', async ({ page }) => {
        await loginAsGeneral(page);
        const token = await page.evaluate(() => sessionStorage.getItem('authToken'));
        expect(typeof token).toBe('string');
        expect(token.length).toBeGreaterThan(0);
    });

    test('home.html redirects if authToken is manually cleared and page is refreshed', async ({ page }) => {
        await loginAsGeneral(page);
        // Clear the token to simulate an expired / logged-out session
        await page.evaluate(() => sessionStorage.removeItem('authToken'));
        await page.reload();

        // The page guard should detect missing token and redirect
        await page.waitForURL(url =>
            url.href.includes('login.html') || url.href.includes('welcome.html'),
            { timeout: 10000 }
        );
    });
});