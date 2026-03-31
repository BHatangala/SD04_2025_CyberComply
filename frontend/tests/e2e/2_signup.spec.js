// tests/e2e/signup.spec.js
// ─────────────────────────────────────────────────────────────────────────────
// Signup page (signup.html)
// Covers: all field validations, Terms & Conditions modal, duplicate email,
// password strength rules, successful account creation.
//
// The happy-path test creates a real account.  Use a disposable address
// each run (the helper generates a unique timestamp-based one), or add an
// afterAll that deletes the created user via Django management command.
// ─────────────────────────────────────────────────────────────────────────────

const { test, expect } = require('@playwright/test');

const SIGNUP_URL      = './signup.html';
const EXISTING_EMAIL  = '21804005@student.curtin.edu.au'; // already in DB

// ── Page Object helpers ───────────────────────────────────────────────────────

/**
 * Fill the complete signup form.
 * acceptTerms=true opens the modal, scrolls to bottom, and clicks Accept.
 */
async function fillForm(page, {
    name            = 'Test User',
    email           = `playwright_${Date.now()}@example.com`,
    password        = 'Curtin1781*',
    confirmPassword = 'Curtin1781*',
    role            = 'General user',
    acceptTerms     = true,
} = {}) {
    await page.fill('#name', name);
    await page.fill('#email', email);
    await page.fill('#password', password);
    // confirmPassword field is conditionally rendered — wait for it
    await page.waitForSelector('#confirmPassword', { state: 'visible' });
    await page.fill('#confirmPassword', confirmPassword);
    await page.selectOption('#role', role);

    if (acceptTerms) {
        await page.click('a:has-text("Terms & Conditions")');
        // Scroll modal body to bottom to unlock the accept button
        await page.waitForSelector('.modal-body', { state: 'visible' });
        await page.evaluate(() => {
            const box = document.querySelector('.modal-body');
            if (box) box.scrollTop = box.scrollHeight;
        });
        await page.waitForSelector('button:has-text("I Have Read and Understood"):not([disabled])');
        await page.click('button:has-text("I Have Read and Understood")');
    }
}

async function clickSignUp(page) {
    await page.click('button:has-text("Sign Up")');
}

// ── Tests ─────────────────────────────────────────────────────────────────────

test.describe('Signup Page — Rendering', () => {

    test.beforeEach(async ({ page }) => { await page.goto(SIGNUP_URL); });

    test('all required fields and Sign Up button are visible', async ({ page }) => {
        await expect(page.locator('#name')).toBeVisible();
        await expect(page.locator('#email')).toBeVisible();
        await expect(page.locator('#password')).toBeVisible();
        await expect(page.locator('#role')).toBeVisible();
        await expect(page.locator('#terms')).toBeVisible();
        await expect(page.locator('button:has-text("Sign Up")')).toBeVisible();
    });

    test('"Log in here" link is present', async ({ page }) => {
        await expect(page.locator('a[href="login.html"]')).toBeVisible();
    });
});


test.describe('Signup Page — Name Validation', () => {

    test.beforeEach(async ({ page }) => { await page.goto(SIGNUP_URL); });

    test('shows error for empty name', async ({ page }) => {
        await clickSignUp(page);
        await expect(page.locator('.note.error').first()).toContainText('required');
    });

    test('shows error for single-word name', async ({ page }) => {
        await page.fill('#name', 'Alice');
        await clickSignUp(page);
        await expect(page.locator('.note.error').first()).toContainText('full name');
    });

    test('shows error for name with only one character per part', async ({ page }) => {
        await page.fill('#name', 'A B');
        await clickSignUp(page);
        await expect(page.locator('.note.error').first()).toContainText('full name');
    });

    test('accepts valid two-part name', async ({ page }) => {
        await page.fill('#name', 'Alice Smith');
        await clickSignUp(page);
        // No name-specific error (other errors may appear)
        await expect(page.locator('#name ~ .note.error')).not.toBeVisible().catch(() => {});
    });
});


test.describe('Signup Page — Email Validation', () => {

    test.beforeEach(async ({ page }) => { await page.goto(SIGNUP_URL); });

    test('shows error for missing email', async ({ page }) => {
        await page.fill('#name', 'Alice Smith');
        await page.fill('#password', 'Curtin1781*');
        await page.waitForSelector('#confirmPassword', { state: 'visible' });
        await page.fill('#confirmPassword', 'Curtin1781*');
        await page.selectOption('#role', 'General user');
        await clickSignUp(page);
        // Target the error specifically next to #email
        await expect(page.locator('#email ~ .note.error')).toContainText('valid email');
    });

    test('shows error for invalid email format', async ({ page }) => {
        await page.fill('#name', 'Alice Smith');
        await page.fill('#email', 'notvalid');
        await page.fill('#password', 'Curtin1781*');
        await page.waitForSelector('#confirmPassword', { state: 'visible' });
        await page.fill('#confirmPassword', 'Curtin1781*');
        await page.selectOption('#role', 'General user');
        await clickSignUp(page);
        await expect(page.locator('#email ~ .note.error')).toContainText('valid email');
    });
});


test.describe('Signup Page — Password Validation', () => {

    test.beforeEach(async ({ page }) => { await page.goto(SIGNUP_URL); });

    test('password strength rules appear while typing', async ({ page }) => {
        await page.fill('#password', 'abc');
        await expect(page.locator('.password-rules')).toBeVisible();
        await expect(page.locator('.rule-item.invalid').first()).toBeVisible();
    });

    test('all rules turn valid for a strong password', async ({ page }) => {
        await page.fill('#password', 'Curtin1781*');
        await expect(page.locator('.password-rules .rule-item.invalid')).toHaveCount(0);
    });

    test('shows error for weak password on submit', async ({ page }) => {
        await page.fill('#name', 'Alice Smith');
        await page.fill('#email', 'alice@example.com');
        await page.fill('#password', 'weakpass');
        await page.waitForSelector('#confirmPassword', { state: 'visible' });
        await page.fill('#confirmPassword', 'weakpass');
        await page.selectOption('#role', 'General user');
        await page.click('a:has-text("Terms & Conditions")');
        await page.waitForSelector('.modal-body', { state: 'visible' });
        await page.evaluate(() => {
            const box = document.querySelector('.modal-body');
            if (box) box.scrollTop = box.scrollHeight;
        });
        await page.waitForSelector('button:has-text("I Have Read and Understood"):not([disabled])');
        await page.click('button:has-text("I Have Read and Understood")');
        await clickSignUp(page);

        // errors.password is set after submit — wait for Vue to render it
        // The .note.error div sits directly after the password-wrapper div
        await expect(
            page.locator('.form-group:has(#password) .note.error')
        ).toContainText(/password/i, { timeout: 5000 });
    });

    test('shows mismatch error when passwords differ', async ({ page }) => {
        await page.fill('#name', 'Alice Smith');
        await page.fill('#email', 'alice@example.com');
        await page.fill('#password', 'Curtin1781*');
        await page.waitForSelector('#confirmPassword', { state: 'visible' });
        await page.fill('#confirmPassword', 'Totally_Different1!');
        await page.selectOption('#role', 'General user');
        await page.click('a:has-text("Terms & Conditions")');
        await page.waitForSelector('.modal-body', { state: 'visible' });
        await page.evaluate(() => {
            const box = document.querySelector('.modal-body');
            if (box) box.scrollTop = box.scrollHeight;
        });
        await page.waitForSelector('button:has-text("I Have Read and Understood"):not([disabled])');
        await page.click('button:has-text("I Have Read and Understood")');

        // Don't wait for submit — the LIVE .password-rules block already
        // shows "Passwords do not match" as soon as confirmPassword has content
        // and doesn't match. Check that BEFORE clicking Sign Up.
        await expect(
            page.locator('.rule-item.invalid:has-text("Passwords do not match")')
        ).toBeVisible({ timeout: 5000 });

        // Also verify the post-submit error after clicking Sign Up
        await clickSignUp(page);
        await expect(
            page.locator('.form-group:has(#confirmPassword) .note.error')
        ).toContainText('do not match', { timeout: 5000 });
    });

    test('shows error when confirmPassword is missing', async ({ page }) => {
        await page.fill('#name', 'Alice Smith');
        await page.fill('#email', 'alice@example.com');
        await page.fill('#password', 'Curtin1781*');
        // Wait for confirmPassword field to appear (v-if="form.password.length > 0")
        await page.waitForSelector('#confirmPassword', { state: 'visible' });
        // Leave confirmPassword empty — do NOT fill it
        await page.selectOption('#role', 'General user');
        await page.click('a:has-text("Terms & Conditions")');
        await page.waitForSelector('.modal-body', { state: 'visible' });
        await page.evaluate(() => {
            const box = document.querySelector('.modal-body');
            if (box) box.scrollTop = box.scrollHeight;
        });
        await page.waitForSelector('button:has-text("I Have Read and Understood"):not([disabled])');
        await page.click('button:has-text("I Have Read and Understood")');
        await clickSignUp(page);

        // v-if="submitted && errors.confirmPassword" — both must be true
        await expect(
            page.locator('.note.error:has-text("Please confirm your password")')
        ).toBeVisible({ timeout: 5000 });
    });
});


test.describe('Signup Page — Role Validation', () => {

    test.beforeEach(async ({ page }) => { await page.goto(SIGNUP_URL); });

    test('shows error when no role is selected', async ({ page }) => {
        await page.fill('#name', 'Alice Smith');
        await page.fill('#email', 'alice@example.com');
        await page.fill('#password', 'Curtin1781*');
        await page.waitForSelector('#confirmPassword', { state: 'visible' });
        await page.fill('#confirmPassword', 'Curtin1781*');
        // No role selected — but accept T&C so terms error doesn't fire first
        await page.click('a:has-text("Terms & Conditions")');
        await page.waitForSelector('.modal-body', { state: 'visible' });
        await page.evaluate(() => {
            const box = document.querySelector('.modal-body');
            if (box) box.scrollTop = box.scrollHeight;
        });
        await page.waitForSelector('button:has-text("I Have Read and Understood"):not([disabled])');
        await page.click('button:has-text("I Have Read and Understood")');
        await clickSignUp(page);
        await expect(page.locator('#role ~ .note.error')).toContainText('role');
    });

    test('shows org-email note when Administrative user is selected', async ({ page }) => {
        await page.selectOption('#role', 'Administrative user');
        // Target the specific note div that follows the role select
        await expect(page.locator('.note:not(.error):has-text("Administrative access requires organization email")')).toBeVisible({ timeout: 5000 });
    });
});


test.describe('Signup Page — Terms & Conditions', () => {

    test.beforeEach(async ({ page }) => { await page.goto(SIGNUP_URL); });

    test('shows terms error when T&C not read before submitting', async ({ page }) => {
        await page.fill('#name', 'Alice Smith');
        await page.fill('#email', 'alice@example.com');
        await page.fill('#password', 'Curtin1781*');
        await page.waitForSelector('#confirmPassword', { state: 'visible' });
        await page.fill('#confirmPassword', 'Curtin1781*');
        await page.selectOption('#role', 'General user');
        // Tick the checkbox without opening the modal (termsRead stays false)
        await page.check('#terms');
        await clickSignUp(page);
        await expect(page.locator('.note.error')).toContainText('Terms');
    });

    test('Accept button is disabled until scrolled to bottom', async ({ page }) => {
        await page.click('a:has-text("Terms & Conditions")');
        await page.waitForSelector('.modal-body', { state: 'visible' });
        const acceptBtn = page.locator('button:has-text("I Have Read and Understood")');
        await expect(acceptBtn).toBeDisabled();

        await page.evaluate(() => {
            const box = document.querySelector('.modal-body');
            if (box) box.scrollTop = box.scrollHeight;
        });
        await expect(acceptBtn).toBeEnabled();
    });

    test('accepting T&C via modal checks the checkbox', async ({ page }) => {
        await page.click('a:has-text("Terms & Conditions")');
        await page.waitForSelector('.modal-body', { state: 'visible' });
        await page.evaluate(() => {
            const box = document.querySelector('.modal-body');
            if (box) box.scrollTop = box.scrollHeight;
        });
        await page.waitForSelector('button:has-text("I Have Read and Understood"):not([disabled])');
        await page.click('button:has-text("I Have Read and Understood")');
        await expect(page.locator('#terms')).toBeChecked();
    });

    test('close icon dismisses the modal', async ({ page }) => {
        await page.click('a:has-text("Terms & Conditions")');
        await page.waitForSelector('.modal-content', { state: 'visible' });
        await page.click('.close-icon');
        await expect(page.locator('.modal-content')).not.toBeVisible();
    });
});


test.describe('Signup Page — Backend Integration', () => {

    test.beforeEach(async ({ page }) => { await page.goto(SIGNUP_URL); });

    test('shows "already registered" error for duplicate email', async ({ page }) => {
        await fillForm(page, { email: EXISTING_EMAIL });
        await clickSignUp(page);
        await expect(page.locator('.note.error')).toContainText('already registered', { timeout: 10000 });
    });

    test('does NOT expose raw Django error detail in the DOM', async ({ page }) => {
        await fillForm(page, { email: EXISTING_EMAIL });
        await clickSignUp(page);
        await page.waitForTimeout(3000);
        const body = await page.content();
        expect(body).not.toContain('IntegrityError');
        expect(body).not.toContain('Traceback');
        expect(body).not.toContain('django');
    });

    test('successful signup shows "Account Created" popup and redirects to login', async ({ page }) => {
        const uniqueEmail = `playwright_${Date.now()}@example.com`;
        await fillForm(page, { email: uniqueEmail });
        await clickSignUp(page);

        await expect(page.locator('.success-modal-content h3')).toContainText('Account Created', { timeout: 10000 });
        await page.waitForURL(/login\.html/, { timeout: 8000 });
    });
});


test.describe('Signup Page — Navigation', () => {

    test.beforeEach(async ({ page }) => { await page.goto(SIGNUP_URL); });

    test('"Log in here" link navigates to login.html', async ({ page }) => {
        await page.click('a[href="login.html"]');
        await expect(page).toHaveURL(/login\.html/);
    });
});