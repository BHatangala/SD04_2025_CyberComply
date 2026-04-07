// tests/e2e/7_compliance.spec.js
// ─────────────────────────────────────────────────────────────────────────────
// Compliance Score page (compliance.html)
//
// Covers:
//   - Auth guard (no token → login, 401/403 → login, sessionStorage cleared)
//   - Page rendering: title, sidebar, navigation elements
//   - Loading banner while fetch is in flight
//   - Error / no-data banner on failed fetch
//   - Summary chips: counts, filter activation, inactive chip dimming
//   - Active filter label and clear filter behaviour
//   - Gap Identification section: items, count, severity order, empty state
//   - Risk Assessment section: items, partial badge, severity order, empty state
//   - Risk mapping enrichment: risk title, consequence, business impact pills
//   - Fallback to AI reasoning when no mapping entry exists
//   - Fallback to /api/analysis/latest/ when no latestResultId in sessionStorage
//   - Error states: non-ok response → no-data banner, network abort → server banner
//   - Sidebar: open by default, toggle, shifted class on back arrow and main content
//   - Navigation: back arrow (history.back), home button, user profile
//
// MOCKING STRATEGY
//   All route mocks use RegExp with /?$ to match URLs with or without trailing
//   slash — same pattern as 6_document_analysis.spec.js.
//   page.unrouteAll() is called at the start of loadPageWithData only when
//   freshRoutes: true (default for standalone tests). When called after
//   loginAsGeneral/loginAsAdmin, pass freshRoutes: false to preserve the
//   auth session set up by the login helper.
//   risk_mapping.json is also mocked so tests are deterministic regardless
//   of whether the AIModel folder is present on the machine running the tests.
// ─────────────────────────────────────────────────────────────────────────────

const { test, expect } = require('@playwright/test');
const {
    loginAsGeneral,
    loginAsAdmin,
} = require('./helpers/helper_login');

const COMP_URL  = './compliance.html';
const RESULT_ID = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';

// ── Regex route helpers ───────────────────────────────────────────────────────
const reResult  = (id) => new RegExp(`/ai/api/analysis/${id}/?$`);
const reLatest  = new RegExp(`/ai/api/analysis/latest/?$`);
const reMapping = new RegExp(`risk_mapping\\.json`);

// ── Fake compliance details ───────────────────────────────────────────────────

const MIXED_DETAILS = [
    { requirement_id: 'SL-PDPA-S7-1',  clause: 'Data minimisation',  status: 'non_compliant', risk_level: 'critical', reasoning: 'No minimisation policy found.' },
    { requirement_id: 'SL-PDPA-S6-1',  clause: 'Purpose limitation', status: 'non_compliant', risk_level: 'high',     reasoning: 'Purpose not documented.' },
    { requirement_id: 'SL-PDPA-S10-1', clause: 'Security measures',  status: 'partial',       risk_level: 'medium',   reasoning: 'Partial controls in place.' },
    { requirement_id: 'SL-PDPA-S12-1', clause: 'Subject rights',     status: 'compliant',     risk_level: 'low',      reasoning: 'Fully addressed.' },
    { requirement_id: 'SL-PDPA-S15-1', clause: 'Data breach notice', status: 'non_compliant', risk_level: 'low',      reasoning: 'No breach notification process.' },
];

const EMPTY_DETAILS = [];

// ── Fake risk mapping (subset — only what tests need) ─────────────────────────
const FAKE_MAPPING = {
    'SL-PDPA-S6-1': {
        risk_title:      'Purpose Creep and Mission Drift',
        consequence:     'Without documented processing purposes the organisation cannot demonstrate proportionate use.',
        business_impact: ['Regulatory challenge on data use', 'Loss of customer trust'],
    },
    'SL-PDPA-S10-1': {
        risk_title:      'Data Breach and Security Incident Exposure',
        consequence:     'Failure to implement security measures is the most direct path to a breach.',
        business_impact: ['Maximum regulatory fines', 'Mandatory public disclosure'],
    },
};

// ── Fake API result wrapper ───────────────────────────────────────────────────
function makeResult(details) {
    return {
        result_id:        RESULT_ID,
        company_name:     'Test Corp',
        compliance_score: 60,
        compliance_label: 'Medium Compliance Level',
        compliance:       { details },
    };
}

const MIXED_RESULT = makeResult(MIXED_DETAILS);
const EMPTY_RESULT = makeResult(EMPTY_DETAILS);

// ── Shared page loader ────────────────────────────────────────────────────────
/**
 * Mocks backend endpoints and loads compliance.html.
 *
 * @param {import('@playwright/test').Page} page
 * @param {object} result - Fake result object to return from the API
 * @param {object} options
 * @param {boolean} options.freshRoutes - Whether to call unrouteAll first.
 *   Pass false when calling immediately after loginAsGeneral/loginAsAdmin
 *   to avoid clearing the auth session set up by the login helper.
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

    await page.route(reMapping, async route => {
        await route.fulfill({
            status:      200,
            contentType: 'application/json',
            body:        JSON.stringify(FAKE_MAPPING),
        });
    });

    await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
    await page.goto(COMP_URL);
    await page.waitForLoadState('networkidle', { timeout: 15000 });
}

// ─────────────────────────────────────────────────────────────────────────────
// Auth Guard
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Compliance — Auth Guard', () => {

    test('redirects to login.html when no authToken in sessionStorage', async ({ page }) => {
        await page.goto('./welcome.html');
        await page.evaluate(() => sessionStorage.clear());
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
        await page.route(reMapping, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(FAKE_MAPPING) });
        });
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
        await page.route(reMapping, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(FAKE_MAPPING) });
        });
        await page.goto(COMP_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
    });

    test('sessionStorage is cleared before redirect on 401', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 401, contentType: 'application/json', body: '{}' });
        });
        await page.route(reMapping, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(FAKE_MAPPING) });
        });
        await page.goto(COMP_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
        const token = await page.evaluate(() => sessionStorage.getItem('authToken'));
        expect(token).toBeNull();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Page Rendering
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Compliance — Page Rendering', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
    });

    test('page stays on compliance.html after load', async ({ page }) => {
        await expect(page).toHaveURL(/compliance\.html/);
    });

    test('COMPLIANCE SCORE heading is visible', async ({ page }) => {
        await expect(page.locator('.page-title')).toContainText('COMPLIANCE SCORE');
    });

    test('top header is visible', async ({ page }) => {
        await expect(page.locator('.top-header')).toBeAttached();
    });

    test('menu icon is visible', async ({ page }) => {
        await expect(page.locator('.menu-icon')).toBeVisible();
    });

    test('user profile icon is visible', async ({ page }) => {
        await expect(page.locator('.user-profile')).toBeVisible();
    });

    test('back arrow is visible', async ({ page }) => {
        await expect(page.locator('.back-arrow')).toBeVisible();
    });

    test('home button is visible', async ({ page }) => {
        await expect(page.locator('.home-button')).toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Loading and Error States
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Compliance — Loading and Error States', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
    });

    test('no-data banner shown when API returns 404', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
        });
        await page.route(reMapping, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(FAKE_MAPPING) });
        });
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.no-data-banner')).toBeVisible({ timeout: 5000 });
    });

    test('no-data banner shown when API returns 500', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' });
        });
        await page.route(reMapping, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(FAKE_MAPPING) });
        });
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.no-data-banner')).toBeVisible({ timeout: 5000 });
    });

    test('no-data banner shown when fetch throws (network abort)', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.abort('connectionreset');
        });
        await page.route(reMapping, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(FAKE_MAPPING) });
        });
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.no-data-banner')).toBeVisible({ timeout: 5000 });
    });

    test('no-data banner contains server error message on network abort', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.abort('connectionreset');
        });
        await page.route(reMapping, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(FAKE_MAPPING) });
        });
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.no-data-banner')).toContainText('Could not reach the server', { timeout: 5000 });
    });

    test('no-data banner not shown when data loads successfully', async ({ page }) => {
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
        await expect(page.locator('.no-data-banner')).not.toBeVisible();
    });

    test('falls back to /api/analysis/latest/ when no latestResultId in sessionStorage', async ({ page }) => {
        let fetchedLatest = false;
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.route(reLatest, async route => {
            fetchedLatest = true;
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MIXED_RESULT) });
        });
        await page.route(reMapping, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(FAKE_MAPPING) });
        });
        await page.evaluate(() => sessionStorage.removeItem('latestResultId'));
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        expect(fetchedLatest).toBe(true);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Summary Chips
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Compliance — Summary Chips', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
    });

    test('summary chips are visible when data is loaded', async ({ page }) => {
        await expect(page.locator('.summary-bar')).toBeVisible();
    });

    test('critical chip shows correct count', async ({ page }) => {
        await expect(page.locator('.summary-chip.chip-critical')).toContainText('1');
    });

    test('high chip shows correct count', async ({ page }) => {
        await expect(page.locator('.summary-chip.chip-high')).toContainText('1');
    });

    test('medium chip shows correct count', async ({ page }) => {
        await expect(page.locator('.summary-chip.chip-medium')).toContainText('1');
    });

    test('low chip shows correct count', async ({ page }) => {
        await expect(page.locator('.summary-chip.chip-low')).toContainText('1');
    });

    test('clicking critical chip activates it', async ({ page }) => {
        await page.locator('.summary-chip.chip-critical').click();
        await expect(page.locator('.summary-chip.chip-critical')).toHaveClass(/chip-active/);
    });

    test('clicking active chip again deactivates it (toggle off)', async ({ page }) => {
        await page.locator('.summary-chip.chip-critical').click();
        await expect(page.locator('.summary-chip.chip-critical')).toHaveClass(/chip-active/);
        await page.locator('.summary-chip.chip-critical').click();
        await expect(page.locator('.summary-chip.chip-critical')).not.toHaveClass(/chip-active/);
    });

    test('inactive chips are dimmed when a filter is active', async ({ page }) => {
        await page.locator('.summary-chip.chip-critical').click();
        await expect(page.locator('.summary-bar')).toHaveClass(/has-filter/);
    });

    test('summary chips are hidden when no data is loaded', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(EMPTY_RESULT) });
        });
        await page.route(reMapping, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(FAKE_MAPPING) });
        });
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.summary-bar')).not.toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Active Filter Label
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Compliance — Filter Label', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
    });

    test('filter label is hidden when no filter is active', async ({ page }) => {
        await expect(page.locator('.filter-label')).not.toBeVisible();
    });

    test('filter label appears when a chip is clicked', async ({ page }) => {
        await page.locator('.summary-chip.chip-critical').click();
        await expect(page.locator('.filter-label')).toBeVisible();
    });

    test('filter label shows the active severity name', async ({ page }) => {
        await page.locator('.summary-chip.chip-high').click();
        await expect(page.locator('.filter-label')).toContainText('high');
    });

    test('clicking Clear filter removes the active filter', async ({ page }) => {
        await page.locator('.summary-chip.chip-critical').click();
        await expect(page.locator('.filter-label')).toBeVisible();
        await page.locator('.filter-clear').click();
        await expect(page.locator('.filter-label')).not.toBeVisible();
    });

    test('clearing filter deactivates the chip', async ({ page }) => {
        await page.locator('.summary-chip.chip-critical').click();
        await page.locator('.filter-clear').click();
        await expect(page.locator('.summary-chip.chip-critical')).not.toHaveClass(/chip-active/);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Gap Identification Section
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Compliance — Gap Identification', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
    });

    test('Gap Identification section header is visible', async ({ page }) => {
        await expect(page.locator('.section-header').first()).toContainText('Gap Identification');
    });

    test('section meta shows correct gap count', async ({ page }) => {
        await expect(
            page.locator('.info-section').nth(0).locator('.section-meta')
        ).toContainText('3 gaps', { timeout: 8000 });
    });

    test('gap items are rendered', async ({ page }) => {
        await expect(page.locator('.info-section').nth(0).locator('.gap-item').first()).toBeVisible({ timeout: 8000 });
    });

    test('first gap item is critical severity (sorted first)', async ({ page }) => {
        const firstBadge = page.locator('.info-section').nth(0).locator('.risk-badge').first();
        await expect(firstBadge).toContainText('critical');
    });

    test('gap items show clause text', async ({ page }) => {
        const firstGap = page.locator('.info-section').nth(0).locator('.gap-item').first();
        await expect(firstGap.locator('.gap-clause')).toContainText('Data minimisation');
    });

    test('gap items show reasoning text', async ({ page }) => {
        const firstGap = page.locator('.info-section').nth(0).locator('.gap-item').first();
        await expect(firstGap.locator('.gap-reasoning')).toContainText('No minimisation policy found');
    });

    test('gap items have numbered index', async ({ page }) => {
        await expect(page.locator('.info-section').nth(0).locator('.gap-id').first()).toContainText('1');
    });

    test('risk badges have correct colour class', async ({ page }) => {
        const firstBadge = page.locator('.info-section').nth(0).locator('.risk-badge').first();
        await expect(firstBadge).toHaveClass(/risk-critical/);
    });

    test('empty state shown when all items are compliant', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(EMPTY_RESULT) });
        });
        await page.route(reMapping, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(FAKE_MAPPING) });
        });
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.no-data-banner')).toBeVisible();
    });

    test('filtering by high shows only high severity gaps', async ({ page }) => {
        await page.locator('.summary-chip.chip-high').click();
        const gaps = page.locator('.info-section').nth(0).locator('.gap-item');
        await expect(gaps).toHaveCount(1);
        await expect(gaps.first().locator('.risk-badge')).toContainText('high');
    });

    test('filtering by medium shows empty gap state (no medium gaps)', async ({ page }) => {
        await page.locator('.summary-chip.chip-medium').click();
        await expect(
            page.locator('.info-section').nth(0).locator('.empty-state')
        ).toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Risk Assessment Section
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Compliance — Risk Assessment', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
    });

    test('Risk Assessment section header is visible', async ({ page }) => {
        await expect(page.locator('.info-section').nth(1).locator('.section-header')).toContainText('Risk Assessment');
    });

    test('section meta shows correct risk count', async ({ page }) => {
        await expect(
            page.locator('.info-section').nth(1).locator('.section-meta')
        ).toContainText('4 items', { timeout: 8000 });
    });

    test('risk items are rendered', async ({ page }) => {
        await expect(page.locator('.info-section').nth(1).locator('.gap-item').first()).toBeVisible();
    });

    test('first risk item is critical severity (sorted first)', async ({ page }) => {
        const firstBadge = page.locator('.info-section').nth(1).locator('.risk-badge').first();
        await expect(firstBadge).toContainText('critical', { timeout: 8000 });
    });

    test('partial items show Partially Implemented badge', async ({ page }) => {
        await expect(
            page.locator('.info-section').nth(1).locator('.status-partial')
        ).toBeVisible();
    });

    test('partial item shows correct clause text', async ({ page }) => {
        await expect(
            page.locator('.info-section').nth(1).locator('.status-partial')
        ).toContainText('Partially Implemented');
    });

    test('filtering by medium shows only medium severity risks', async ({ page }) => {
        await page.locator('.summary-chip.chip-medium').click();
        const risks = page.locator('.info-section').nth(1).locator('.gap-item');
        await expect(risks).toHaveCount(1);
        await expect(risks.first().locator('.risk-badge')).toContainText('medium');
    });

    test('empty state shown when no risks match active filter', async ({ page }) => {
        await page.locator('.summary-chip.chip-medium').click();
        await expect(
            page.locator('.info-section').nth(0).locator('.empty-state')
        ).toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Risk Mapping Enrichment
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Compliance — Risk Mapping', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
    });

    test('risk title from mapping is shown for mapped requirement', async ({ page }) => {
        await expect(
            page.locator('.info-section').nth(1)
        ).toContainText('Purpose Creep and Mission Drift');
    });

    test('consequence text from mapping is shown for mapped requirement', async ({ page }) => {
        await expect(
            page.locator('.info-section').nth(1)
        ).toContainText('Without documented processing purposes');
    });

    test('business impact pills are shown for mapped requirement', async ({ page }) => {
        await expect(
            page.locator('.impact-pill').first()
        ).toBeVisible();
    });

    test('impact pill shows correct label', async ({ page }) => {
        await expect(
            page.locator('.impact-pill').first()
        ).toContainText('Regulatory challenge on data use');
    });

    test('falls back to AI reasoning when requirement is not in mapping', async ({ page }) => {
        await expect(
            page.locator('.info-section').nth(1)
        ).toContainText('No minimisation policy found');
    });

    test('no impact pills shown for unmapped requirement', async ({ page }) => {
        await page.locator('.summary-chip.chip-critical').click();
        await expect(
            page.locator('.impact-pill')
        ).toHaveCount(0);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Sidebar
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Compliance — Sidebar', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
    });

    test('sidebar is open by default — back arrow has shifted class', async ({ page }) => {
        await expect(page.locator('.back-arrow')).toHaveClass(/shifted/);
    });

    test('sidebar is open by default — home button has shifted class', async ({ page }) => {
        await expect(page.locator('.home-button')).toHaveClass(/shifted/);
    });

    test('sidebar is open by default — main content has shifted class', async ({ page }) => {
        await expect(page.locator('.main-content')).toHaveClass(/shifted/);
    });

    test('clicking menu icon closes sidebar — back arrow loses shifted class', async ({ page }) => {
        await page.locator('.menu-icon').click();
        await expect(page.locator('.back-arrow')).not.toHaveClass(/shifted/);
    });

    test('clicking menu icon closes sidebar — main content loses shifted class', async ({ page }) => {
        await page.locator('.menu-icon').click();
        await expect(page.locator('.main-content')).not.toHaveClass(/shifted/);
    });

    test('clicking menu icon again re-opens sidebar', async ({ page }) => {
        await page.locator('.menu-icon').click();
        await page.locator('.menu-icon').click();
        await expect(page.locator('.back-arrow')).toHaveClass(/shifted/);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Navigation
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Compliance — Navigation', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithData(page, MIXED_RESULT, { freshRoutes: false });
    });

    test('user profile icon navigates to profile.html', async ({ page }) => {
        await page.locator('.user-profile').click();
        await expect(page).toHaveURL(/profile\.html/);
    });

    test('home button navigates to home.html', async ({ page }) => {
        await page.locator('.home-button').click();
        await expect(page).toHaveURL(/home\.html/);
    });

    test('back arrow calls history.back — navigates to previous page', async ({ page }) => {
        await page.goto('./document_analysis.html');
        await page.goto(COMP_URL);
        await page.locator('.back-arrow').click();
        await expect(page).toHaveURL(/document_analysis\.html/);
    });
});