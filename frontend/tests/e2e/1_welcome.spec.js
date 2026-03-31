// tests/e2e/welcome.spec.js
// ─────────────────────────────────────────────────────────────────────────────
// Welcome / landing page (welcome.html)
// Covers: rendering, navigation to Login and Signup, page title.
// ─────────────────────────────────────────────────────────────────────────────

const { test, expect } = require('@playwright/test');

test.describe('Welcome Page', () => {

    test.beforeEach(async ({ page }) => {
        await page.goto('./welcome.html');
    });

    // ── Rendering ─────────────────────────────────────────────────────────────

    test('renders brand name CYBERCOMPLY', async ({ page }) => {
        await expect(page.locator('.brand-name')).toContainText('CYBERCOMPLY');
    });

    test('renders "WELCOME TO" tag line', async ({ page }) => {
        await expect(page.locator('.welcome-text')).toContainText('WELCOME TO');
    });

    test('renders Sign Up prompt and button', async ({ page }) => {
        await expect(page.locator('.account-text')).toContainText("DON'T HAVE AN ACCOUNT?");
        await expect(page.locator('.signup-btn')).toBeVisible();
    });

    test('renders LOGIN button', async ({ page }) => {
        await expect(page.locator('.login-btn')).toBeVisible();
    });

    test('has correct page title containing CyberComply', async ({ page }) => {
        await expect(page).toHaveTitle(/CyberComply/i);
    });

    // ── Navigation ────────────────────────────────────────────────────────────

    test('LOGIN button navigates to login.html', async ({ page }) => {
        await page.click('.login-btn');
        await expect(page).toHaveURL(/login\.html/);
    });

    test('Sign Up button navigates to signup.html', async ({ page }) => {
        await page.click('.signup-btn');
        await expect(page).toHaveURL(/signup\.html/);
    });
});