// tests/e2e/8_comparison.spec.js
// ─────────────────────────────────────────────────────────────────────────────
// Comparison Dashboard page (comparison.html)
//
// Covers:
//   - Auth guard (no token → login, 401/403 → login, sessionStorage cleared)
//   - Page rendering: title, sidebar, navigation elements
//   - Loading banner while fetch is in flight
//   - Error / no-data banner on failed fetch and network abort
//   - Company name displayed from DB response
//   - Department dropdown shows department name from DB response
//   - Compliance score displayed
//   - Risk level derived from score (Low / Medium / High thresholds)
//   - Graphical View button gated behind isAdmin && hasMultipleDepartments
//   - Departmental recommendations rendered from non_compliant + partial details
//   - buildReferenceFromId() produces correct PDPA reference string
//   - Compliant-only result shows "fully compliant" empty state
//   - Fallback to /api/analysis/latest/ when no latestResultId in sessionStorage
//   - Sidebar: open by default, toggle, shifted class on back/home/content
//   - Navigation: back arrow → document_analysis.html, home → home.html, profile → profile.html
//
// MOCKING STRATEGY
//   All route mocks use RegExp with /?$ to match URLs with or without trailing
//   slash — same pattern as 7_compliance.spec.js.
//   page.unrouteAll() is called inside loadPageWithData when freshRoutes: true
//   (the default). Pass freshRoutes: false after loginAsGeneral/loginAsAdmin to
//   preserve the auth session set up by the login helper.
// ─────────────────────────────────────────────────────────────────────────────

const { test, expect } = require('@playwright/test');
const {
    loginAsGeneral,
    loginAsAdmin,
} = require('./helpers/helper_login');

// ── URLs & route patterns ─────────────────────────────────────────────────────
const COMP_URL  = './comparison.html';
const RESULT_ID = '42';

const reResult = (id) => new RegExp(`/ai/api/analysis/${id}/?$`);
const reLatest  = /\/ai\/api\/analysis\/latest\/?$/;

// ── Shared fake data ──────────────────────────────────────────────────────────

// Mixed details: non_compliant, partial, and compliant entries
const MIXED_DETAILS = [
    {
        requirement_id: 'SL-PDPA-S6-1',
        clause:         'Lawful basis for processing personal data',
        status:         'non_compliant',
        risk_level:     'critical',
        reasoning:      'No evidence of a lawful basis documented.',
    },
    {
        requirement_id: 'SL-PDPA-S23-1',
        clause:         'Data subject access rights',
        status:         'partial',
        risk_level:     'high',
        reasoning:      'Access rights process exists but is incomplete.',
    },
    {
        requirement_id: 'SL-PDPA-S10-1',
        clause:         'Security of personal data',
        status:         'compliant',
        risk_level:     'low',
        reasoning:      'Security controls are in place and documented.',
    },
];

// All compliant — for empty-state test
const COMPLIANT_DETAILS = [
    {
        requirement_id: 'SL-PDPA-S10-1',
        clause:         'Security of personal data',
        status:         'compliant',
        risk_level:     'low',
        reasoning:      'Security controls are in place.',
    },
];

// ── Factory helpers ───────────────────────────────────────────────────────────
function makeResult(details, overrides = {}) {
    return {
        result_id:        RESULT_ID,
        company_name:     'Test Corp',
        department:       'IT',
        compliance_score: 60,
        compliance:       { details },
        ...overrides,
    };
}

const MIXED_RESULT     = makeResult(MIXED_DETAILS);
const COMPLIANT_RESULT = makeResult(COMPLIANT_DETAILS, { compliance_score: 100 });
const HIGH_SCORE       = makeResult(MIXED_DETAILS,     { compliance_score: 80 });
const LOW_SCORE        = makeResult(MIXED_DETAILS,     { compliance_score: 30 });

// ── Shared page loader ────────────────────────────────────────────────────────
/**
 * Mocks backend endpoints and loads comparison.html.
 *
 * @param {import('@playwright/test').Page} page
 * @param {object} result         - Fake API result to serve
 * @param {object} options
 * @param {boolean} options.freshRoutes - Pass false after loginAs* helpers to
 *   avoid clearing the auth session.
 */
async function loadPageWithData(page, result = MIXED_RESULT, { freshRoutes = true } = {}) {
    if (freshRoutes) {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
    }

    await page.route(reResult(RESULT_ID), async route => {
        await route.fulfill({
            status:      200,
            contentType: 'application/json',
            body:        JSON.stringify(result),
        });
    });

    await page.route(reLatest, async route => {
        await route.fulfill({
            status:      200,
            contentType: 'application/json',
            body:        JSON.stringify(result),
        });
    });

    await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
    await page.goto(COMP_URL);
    await page.waitForLoadState('networkidle', { timeout: 15000 });
}

// ─────────────────────────────────────────────────────────────────────────────
// Auth Guard
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Comparison — Auth Guard', () => {

    test('redirects to login.html when no authToken in sessionStorage', async ({ page }) => {
        await page.goto('./welcome.html');
        await page.evaluate(() => sessionStorage.clear());
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
    });

    test('redirects to login.html when API returns 401', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Unauthorized"}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
    });

    test('redirects to login.html when API returns 403', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 403, contentType: 'application/json', body: '{"detail":"Forbidden"}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
    });

    test('clears sessionStorage before redirecting on 401', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Unauthorized"}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
        const token = await page.evaluate(() => sessionStorage.getItem('authToken'));
        expect(token).toBeNull();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Page Rendering
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Comparison — Page Rendering', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
    });

    test('stays on comparison.html after successful load', async ({ page }) => {
        expect(page.url()).toMatch(/comparison\.html/);
    });

    test('page title COMPARISON DASHBOARD is visible', async ({ page }) => {
        await expect(page.locator('.page-title')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('.page-title')).toContainText('COMPARISON DASHBOARD');
    });

    test('top header is visible', async ({ page }) => {
        await expect(page.locator('.top-header')).toBeVisible();
    });

    test('menu icon is visible', async ({ page }) => {
        await expect(page.locator('.menu-icon')).toBeVisible();
    });

    test('user profile button is visible', async ({ page }) => {
        await expect(page.locator('.user-profile')).toBeVisible();
    });

    test('back arrow is visible', async ({ page }) => {
        await expect(page.locator('.back-arrow')).toBeVisible();
    });

    test('home button is visible', async ({ page }) => {
        await expect(page.locator('.home-button')).toBeVisible({ timeout: 10000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Loading and Error States
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Comparison — Loading and Error States', () => {

    test('shows no-data banner when API returns 404', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Not found"}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.no-data-banner')).toBeVisible();
    });

    test('shows no-data banner when API returns 500', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Server error"}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.no-data-banner')).toBeVisible();
    });

    test('shows server error banner when network request aborts', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.abort();
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.no-data-banner')).toBeVisible();
    });

    test('aborted request banner contains server connection message', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.abort();
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.no-data-banner')).toContainText('Could not reach the server');
    });

    test('no error banner shown when data loads successfully', async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
        await expect(page.locator('.no-data-banner')).not.toBeVisible();
    });

    test('falls back to /api/analysis/latest/ when latestResultId not in sessionStorage', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(() => sessionStorage.removeItem('latestResultId'));

        let latestCalled = false;
        await page.route(reLatest, async route => {
            latestCalled = true;
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify(MIXED_RESULT),
            });
        });

        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        expect(latestCalled).toBe(true);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Company and Department Display
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Comparison — Company and Department Display', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
    });

    test('company name is displayed from API response', async ({ page }) => {
        await expect(page.locator('.company-name')).toContainText('Test Corp');
    });

    test('company name label prefix is shown', async ({ page }) => {
        await expect(page.locator('.company-name')).toContainText('Company Name');
    });

    test('department dropdown is visible', async ({ page }) => {
        await expect(page.locator('.custom-select')).toBeVisible();
    });

    test('department dropdown shows department name from API', async ({ page }) => {
        await expect(page.locator('.custom-select')).toContainText('IT Department');
    });

    test('company name hidden when no data loaded', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.company-name')).not.toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Score and Risk Level
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Comparison — Score and Risk Level', () => {

    test('compliance score is displayed', async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
        await expect(page.locator('.stat-box')).toContainText('Score : 60%');
    });

    test('risk level shows Medium when score is 60', async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
        await expect(page.locator('.stat-box')).toContainText('Risk Level : Medium');
    });

    test('risk level shows Low when score is 80 (>= 75)', async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, HIGH_SCORE, { freshRoutes: false });
        await expect(page.locator('.stat-box')).toContainText('Risk Level : Low');
    });

    test('risk level shows High when score is 30 (< 40)', async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, LOW_SCORE, { freshRoutes: false });
        await expect(page.locator('.stat-box')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('.stat-box')).toContainText('Risk Level : High');
    });

    test('stat box is visible when data is loaded', async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
        await expect(page.locator('.stat-box')).toBeVisible({ timeout: 10000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Graphical View Button (RBAC gate)
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Comparison — Graphical View Button', () => {

    test('Graphical View button is NOT shown to general user', async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
        await expect(page.locator('.metric-box', { hasText: 'Graphical View' })).not.toBeVisible();
    });

    test('Graphical View button is NOT shown to admin when only one department analysed', async ({ page }) => {
        await loginAsAdmin(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
        await expect(page.locator('.metric-box', { hasText: 'Graphical View' })).not.toBeVisible();
    });

    // Skipped: hasMultipleDepartments is always false until the multi-department
    // API endpoint is implemented in a future sprint. When that lands, populate
    // this.departments from the API in mounted() and remove the skip.
    test.skip('Graphical View button IS shown to admin when multiple departments analysed', async ({ page }) => {
        await loginAsAdmin(page);
        await page.evaluate(() => {
            // Simulate Vue data having multiple departments once the API populates it
            window.__vueDepartments__ = ['IT', 'HR'];
        });
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
        await expect(page.locator('.metric-box', { hasText: 'Graphical View' })).toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Departmental Recommendations
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Comparison — Departmental Recommendations', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
    });

    test('recommendations section is visible', async ({ page }) => {
        await expect(page.locator('.recommendations-section')).toBeVisible();
    });

    test('recommendations section title contains department name', async ({ page }) => {
        await expect(page.locator('.rec-title')).toContainText('IT');
    });

    test('recommendations section title contains DEPARTMENTAL RECOMMENDATIONS', async ({ page }) => {
        await expect(page.locator('.rec-title')).toContainText('DEPARTMENTAL RECOMMENDATIONS');
    });

    test('non_compliant item is shown in recommendations list', async ({ page }) => {
        const items = page.locator('.rec-list > li');
        await expect(items.first()).toContainText('Lawful basis for processing personal data');
    });

    test('partial item is also shown in recommendations list', async ({ page }) => {
        const items = page.locator('.rec-list > li');
        await expect(items).toHaveCount(2); // non_compliant + partial; compliant excluded
    });

    test('compliant item is NOT shown in recommendations list', async ({ page }) => {
        const text = await page.locator('.rec-list').innerText();
        expect(text).not.toContain('Security of personal data');
    });

    test('sub-list shows PDPA reference for non_compliant item', async ({ page }) => {
        const subItems = page.locator('.sub-rec-list li');
        await expect(subItems.first()).toContainText('Section 6(1) of the Personal Data Protection Act No. 9 of 2022 (Sri Lanka)');
    });

    test('sub-list shows PDPA reference for partial item', async ({ page }) => {
        const subItems = page.locator('.sub-rec-list li');
        await expect(subItems.nth(1)).toContainText('Section 23(1) of the Personal Data Protection Act No. 9 of 2022 (Sri Lanka)');
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// buildReferenceFromId — PDPA reference string construction
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Comparison — buildReferenceFromId', () => {

    test('converts SL-PDPA-S6-1 to correct section reference', async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
        const refs = page.locator('.sub-rec-list li');
        await expect(refs.first()).toContainText('Section 6(1)');
    });

    test('converts SL-PDPA-S23-1 to correct section reference', async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
        const refs = page.locator('.sub-rec-list li');
        await expect(refs.nth(1)).toContainText('Section 23(1)');
    });

    test('reference string includes Act name and year', async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
        const refs = page.locator('.sub-rec-list li');
        await expect(refs.first()).toContainText('Personal Data Protection Act No. 9 of 2022 (Sri Lanka)');
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Fully Compliant Empty State
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Comparison — Fully Compliant Empty State', () => {

    test('shows fully compliant message when all details are compliant', async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, COMPLIANT_RESULT, { freshRoutes: false });
        await expect(page.locator('.rec-list')).toContainText('No recommendations');
    });

    test('no recommendation list items rendered when all compliant', async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, COMPLIANT_RESULT, { freshRoutes: false });
        // Only the empty-state <li> should be present, not real recommendation items
        const items = page.locator('.rec-list > li');
        await expect(items).toHaveCount(1);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Sidebar
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Comparison — Sidebar', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
    });

    test('sidebar is open by default — back arrow has shifted class', async ({ page }) => {
        await expect(page.locator('.back-arrow')).toHaveClass(/shifted/);
    });

    test('sidebar is open by default — home button has shifted class', async ({ page }) => {
        await expect(page.locator('.home-button')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('.home-button')).toHaveClass(/shifted/);
    });

    test('sidebar is open by default — main content has shifted class', async ({ page }) => {
        await expect(page.locator('.main-content')).toHaveClass(/shifted/);
    });

    test('closing sidebar removes shifted class from back arrow', async ({ page }) => {
        await page.locator('.menu-icon').click();
        await expect(page.locator('.back-arrow')).not.toHaveClass(/shifted/);
    });

    test('closing sidebar removes shifted class from main content', async ({ page }) => {
        await page.locator('.menu-icon').click();
        await expect(page.locator('.main-content')).not.toHaveClass(/shifted/);
    });

    test('re-opening sidebar restores shifted class on main content', async ({ page }) => {
        await page.locator('.menu-icon').click();
        await page.locator('.menu-icon').click();
        await expect(page.locator('.main-content')).toHaveClass(/shifted/);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Navigation
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Comparison — Navigation', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
    });

    test('user profile button navigates to profile.html', async ({ page }) => {
        await page.locator('.user-profile').click();
        await page.waitForURL(/profile\.html/, { timeout: 10000 });
    });

    test('home button navigates to home.html', async ({ page }) => {
        await page.locator('.home-button').click();
        await page.waitForURL(/home\.html/, { timeout: 10000 });
    });

    test('back arrow navigates to document_analysis.html', async ({ page }) => {
        await page.locator('.back-arrow').click();
        await page.waitForURL(/document_analysis\.html/, { timeout: 10000 });
    });
});