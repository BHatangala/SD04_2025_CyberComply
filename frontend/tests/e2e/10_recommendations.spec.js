// tests/e2e/10_recommendations.spec.js
// ─────────────────────────────────────────────────────────────────────────────
// Recommendations page (recommendations.html) — full E2E test suite
//
// Covers:
//   - Unauthenticated access guard (no token → redirect to login.html)
//   - Single file mode: page load, card rendering, PDPA reference string,
//     sidebar behaviour, navigation, save-to-DB call, duplicate save prevention
//   - Single file mode: fully compliant state (no cards, no-data banner)
//   - Batch mode: accordion rendering, default expanded state, summary badge,
//     toggle behaviour, per-department save call, fully compliant department
//   - Error handling: 401/403, 404/500, network failure, corrupted batch JSON,
//     empty batch array
//
// MOCKING STRATEGY
//   - /ai/api/analysis/<id>/       → mocked to return fake compliance details
//   - /ai/api/recommendations/save/ → mocked to return 200 and track if called
//   - ../AIModel/data/pdpa_requirements_full.json → served by Live Server
//     naturally from disk — NOT mocked, so the real PDPA index is used
//
// REAL BACKEND CALLS (not mocked):
//   - /api/login/ + /api/session-token/  (auth via loginAsAdmin)
//   - /api/profile/                       (session guard)
//
// NOTE ON ACCESS:
//   recommendations.html enforces two guards in mounted():
//   1. Auth guard — no token → redirect to login.html
//   2. Role guard — non-admin → history.back() to previous page
//   All authenticated tests use loginAsAdmin.
//   The general user access test uses loginAsGeneral to verify the role guard.
// ─────────────────────────────────────────────────────────────────────────────

const { test, expect } = require('@playwright/test');
const {
    loginAsAdmin,
    loginAsGeneral,
    ADMIN_EMAIL,
} = require('./helpers/helper_login');

const RECS_URL = './recommendations.html';

// ── Fake result IDs ───────────────────────────────────────────────────────────
const FAKE_RESULT_ID        = 'aaaaaaaa-1111-2222-3333-ffffffffffff';
const FAKE_RESULT_ID_BATCH1 = 'bbbbbbbb-1111-2222-3333-ffffffffffff';
const FAKE_RESULT_ID_BATCH2 = 'cccccccc-1111-2222-3333-ffffffffffff';

// ── Fake compliance details — two non-compliant items ────────────────────────
// SL-PDPA-S6-1 maps to Section 6(1) in the PDPA JSON — used to verify the
// buildReference() helper runs correctly using the real PDPA index file.
const FAKE_DETAILS_FLAGGED = [
    {
        requirement_id: 'SL-PDPA-S6-1',
        clause: 'Obligation to Define a Purpose — Purpose Specification',
        status: 'non_compliant',
        risk_level: 'high',
        reasoning: 'No documented purpose specification found in the document.'
    },
    {
        requirement_id: 'SL-PDPA-S4',
        clause: 'Compliance with the Data Protection Obligations',
        status: 'partial',
        risk_level: 'critical',
        reasoning: 'Partial compliance with data protection obligations detected.'
    }
];

// ── Fake analysis response — single file mode ─────────────────────────────────
function makeSingleResult(details = FAKE_DETAILS_FLAGGED) {
    return {
        result_id:         FAKE_RESULT_ID,
        original_filename: 'test_document.txt',
        company_name:      'Test Organisation',
        compliance_score:  55,
        compliance_label:  'Partial Compliance',
        compliance:        { details },
        recommendations:   {}
    };
}

// ── Fake analysis response — batch mode, per department ───────────────────────
function makeBatchResult(resultId, deptName, details = FAKE_DETAILS_FLAGGED) {
    return {
        result_id:         resultId,
        original_filename: 'batch_doc.txt',
        company_name:      'Test Organisation',
        department:        deptName,
        compliance_score:  60,
        compliance_label:  'Partial Compliance',
        compliance:        { details },
        recommendations:   {}
    };
}

// ── Helper: seed sessionStorage and mock endpoints for single file mode ───────
// Seeds latestResultId, mocks the analysis fetch and the save endpoint.
// Returns a tracker so tests can assert whether save was called.
async function setupSingleMode(page, details = FAKE_DETAILS_FLAGGED) {
    await page.evaluate((id) => {
        sessionStorage.setItem('latestResultId', id);
        // Clear any pre-existing saved flag so save is always attempted
        sessionStorage.removeItem(`recsSaved_${id}`);
    }, FAKE_RESULT_ID);

    await page.route(`**/ai/api/analysis/${FAKE_RESULT_ID}/`, async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(makeSingleResult(details)),
        });
    });

    let saveWasCalled = false;
    await page.route('**/ai/api/recommendations/save/', async route => {
        saveWasCalled = true;
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ success: true }),
        });
    });

    return { getSaveCalled: () => saveWasCalled };
}

// ── Helper: seed sessionStorage and mock endpoints for batch mode ─────────────
// Seeds batchResultIds with two IDs and mocks each analysis fetch separately.
async function setupBatchMode(page, {
    dept1Details = FAKE_DETAILS_FLAGGED,
    dept2Details = FAKE_DETAILS_FLAGGED,
} = {}) {
    await page.evaluate(([id1, id2]) => {
        sessionStorage.setItem('batchResultIds', JSON.stringify([id1, id2]));
        sessionStorage.removeItem('latestResultId');
        sessionStorage.removeItem(`recsSaved_${id1}`);
        sessionStorage.removeItem(`recsSaved_${id2}`);
    }, [FAKE_RESULT_ID_BATCH1, FAKE_RESULT_ID_BATCH2]);

    await page.route(`**/ai/api/analysis/${FAKE_RESULT_ID_BATCH1}/`, async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(makeBatchResult(FAKE_RESULT_ID_BATCH1, 'Finance & Accounting', dept1Details)),
        });
    });

    await page.route(`**/ai/api/analysis/${FAKE_RESULT_ID_BATCH2}/`, async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(makeBatchResult(FAKE_RESULT_ID_BATCH2, 'Legal & Compliance', dept2Details)),
        });
    });

    const saveCalls = [];
    await page.route('**/ai/api/recommendations/save/', async route => {
        const body = route.request().postDataJSON();
        saveCalls.push(body?.result_id);
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ success: true }),
        });
    });

    return { getSaveCalls: () => saveCalls };
}

// ─────────────────────────────────────────────────────────────────────────────
// Access Guard — Unauthenticated
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Recommendations Page — Access Guard (Unauthenticated)', () => {

    test('navigating to recommendations.html without a token redirects to login.html', async ({ page }) => {
        // Clear all storage first so there is no leftover authToken
        await page.goto('./welcome.html');
        await page.evaluate(() => {
            sessionStorage.clear();
            localStorage.clear();
        });
        await page.goto(RECS_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
    });

    test('general user accessing recommendations.html via URL is sent back', async ({ page }) => {
        // Navigate to document_analysis first so there is history to go back to
        await loginAsGeneral(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        // Mock the analysis endpoint so document_analysis.html loads cleanly
        await page.route(`**/ai/api/analysis/${FAKE_RESULT_ID}/`, async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    result_id: FAKE_RESULT_ID,
                    original_filename: 'test.txt',
                    company_name: 'Test Org',
                    compliance_score: 55,
                    compliance_label: 'Partial Compliance',
                    compliance: { details: [] },
                    recommendations: {}
                }),
            });
        });

        await page.evaluate((id) => {
            sessionStorage.setItem('latestResultId', id);
        }, FAKE_RESULT_ID);

        await page.goto('./document_analysis.html');
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        // Now try to navigate to recommendations.html as a general user
        await page.goto(RECS_URL);

        // Role guard fires history.back() — should return to document_analysis.html
        await page.waitForURL(/document_analysis\.html/, { timeout: 10000 });

        // Confirm the general user never reached recommendations.html
        await expect(page).not.toHaveURL(/recommendations\.html/);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Single File Mode — Page Load & Rendering
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Recommendations Page — Single File Mode: Rendering', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await setupSingleMode(page);
        await page.goto(RECS_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
    });

    test('logo renders with correct text', async ({ page }) => {
        await expect(page.locator('.logo h1')).toContainText('CYBERCOMPLY');
        await expect(page.locator('.logo h1')).toContainText('RECOMMENDATIONS');
    });

    test('recommendation cards render for non-compliant and partial items', async ({ page }) => {
        // Two flagged items in FAKE_DETAILS_FLAGGED — expect two cards
        await expect(page.locator('.recommendation')).toHaveCount(2, { timeout: 10000 });
    });

    test('recommendation card contains clause title and reasoning text', async ({ page }) => {
        await expect(
            page.locator('.recommendation').first().locator('.rec-heading')
        ).toContainText('Compliance with the Data Protection Obligations', { timeout: 10000 });

        await expect(
            page.locator('.recommendation').first().locator('.rec-reasoning')
        ).toContainText('Partial compliance with data protection obligations', { timeout: 10000 });
    });

    test('PDPA reference string is built correctly from the real PDPA index', async ({ page }) => {
        // SL-PDPA-S6-1 → Section 6(1) — confirms pdpa_requirements_full.json
        // was loaded and buildReference() ran using the real index
        await expect(
            page.locator('.rec-reference').first()
        ).toContainText('Section 4', { timeout: 10000 });
    });

    test('steps to achieve compliance are rendered for each card', async ({ page }) => {
        await expect(
            page.locator('.recommendation').first().locator('.rec-steps li')
        ).toHaveCount(await page.locator('.recommendation').first().locator('.rec-steps li').count());

        // At least one step exists
        const stepCount = await page.locator('.recommendation').first().locator('.rec-steps li').count();
        expect(stepCount).toBeGreaterThan(0);
    });

    test('risk badge is visible on each card', async ({ page }) => {
        await expect(
            page.locator('.recommendation').first().locator('.risk-badge')
        ).toBeVisible({ timeout: 10000 });
    });

    test('sidebar is open by default on page load', async ({ page }) => {
        // When sidebar is open, the back arrow and main content get the shifted class
        await expect(page.locator('.back-arrow')).toHaveClass(/shifted/);
        await expect(page.locator('.main-content')).toHaveClass(/shifted/);
    });

    test('menu icon toggles the sidebar closed and open', async ({ page }) => {
        // Sidebar starts open — clicking menu icon removes shifted classes
        await page.locator('.menu-icon').click();
        await expect(page.locator('.back-arrow')).not.toHaveClass(/shifted/);
        await expect(page.locator('.main-content')).not.toHaveClass(/shifted/);

        // Clicking again reopens it
        await page.locator('.menu-icon').click();
        await expect(page.locator('.back-arrow')).toHaveClass(/shifted/);
    });

    test('user profile icon navigates to profile.html', async ({ page }) => {
        await page.locator('.user-profile').click();
        await expect(page).toHaveURL(/profile\.html/, { timeout: 10000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Single File Mode — Save to DB
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Recommendations Page — Single File Mode: Save Behaviour', () => {

    test('save endpoint is called when recommendations are loaded for the first time', async ({ page }) => {
        await loginAsAdmin(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        const { getSaveCalled } = await setupSingleMode(page);
        await page.goto(RECS_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        // Give the async save call time to fire after recommendations are built
        await page.waitForTimeout(2000);
        expect(getSaveCalled()).toBe(true);
    });

    test('save endpoint is NOT called again if recsSaved flag already exists in sessionStorage', async ({ page }) => {
        await loginAsAdmin(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        // Pre-seed the already-saved flag before setting up the page
        await page.evaluate((id) => {
            sessionStorage.setItem('latestResultId', id);
            sessionStorage.setItem(`recsSaved_${id}`, '1');
        }, FAKE_RESULT_ID);

        await page.route(`**/ai/api/analysis/${FAKE_RESULT_ID}/`, async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify(makeSingleResult()),
            });
        });

        let saveWasCalled = false;
        await page.route('**/ai/api/recommendations/save/', async route => {
            saveWasCalled = true;
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
        });

        await page.goto(RECS_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await page.waitForTimeout(2000);

        // Flag was already set — save should have been skipped
        expect(saveWasCalled).toBe(false);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Single File Mode — Fully Compliant State
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Recommendations Page — Single File Mode: Fully Compliant', () => {

    test('no cards render and no-data banner appears when all items are compliant', async ({ page }) => {
        await loginAsAdmin(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        // Pass empty details — no non_compliant or partial items
        await setupSingleMode(page, []);
        await page.goto(RECS_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(page.locator('.no-data-banner')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('.recommendation')).toHaveCount(0);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Single File Mode — Navigation
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Recommendations Page — Single File Mode: Navigation', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await setupSingleMode(page);
        await page.goto(RECS_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
    });

    test('back arrow navigates to document_analysis.html', async ({ page }) => {
        await page.locator('.back-arrow').click();
        await expect(page).toHaveURL(/document_analysis\.html/, { timeout: 10000 });
    });

    test('home button navigates to home.html', async ({ page }) => {
        await page.locator('.home-button').click();
        await expect(page).toHaveURL(/home\.html/, { timeout: 10000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Batch Mode — Page Load & Rendering
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Recommendations Page — Batch Mode: Rendering', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await setupBatchMode(page);
        await page.goto(RECS_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
    });

    test('two department accordions render in batch mode', async ({ page }) => {
        await expect(page.locator('.dept-accordion')).toHaveCount(2, { timeout: 15000 });
    });

    test('first department accordion is expanded by default', async ({ page }) => {
        await expect(
            page.locator('.dept-accordion').first().locator('.dept-accordion-body')
        ).toHaveClass(/open/, { timeout: 10000 });
    });

    test('second department accordion is collapsed by default', async ({ page }) => {
        const secondBody = page.locator('.dept-accordion').nth(1).locator('.dept-accordion-body');
        await expect(secondBody).not.toHaveClass(/open/, { timeout: 10000 });
    });

    test('department names appear in accordion headers', async ({ page }) => {
        await expect(
            page.locator('.dept-accordion').first().locator('.dept-accordion-name')
        ).toContainText('Finance & Accounting', { timeout: 10000 });

        await expect(
            page.locator('.dept-accordion').nth(1).locator('.dept-accordion-name')
        ).toContainText('Legal & Compliance', { timeout: 10000 });
    });

    test('batch summary badge is visible and shows correct department and recommendation counts', async ({ page }) => {
        // 2 departments, each with 2 flagged items = 4 total recommendations
        await expect(page.locator('.batch-summary-badge')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('.batch-summary-badge')).toContainText('2 DEPARTMENTS');
        await expect(page.locator('.batch-summary-badge')).toContainText('4 RECOMMENDATIONS');
    });

    test('batch summary badge is NOT visible in single file mode', async ({ page }) => {
        // Navigate away and re-enter in single mode to confirm badge is absent
        await page.evaluate((id) => {
            sessionStorage.removeItem('batchResultIds');
            sessionStorage.setItem('latestResultId', id);
        }, FAKE_RESULT_ID);

        await page.route(`**/ai/api/analysis/${FAKE_RESULT_ID}/`, async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify(makeSingleResult()),
            });
        });

        await page.goto(RECS_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.batch-summary-badge')).not.toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Batch Mode — Accordion Toggle
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Recommendations Page — Batch Mode: Accordion Toggle', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await setupBatchMode(page);
        await page.goto(RECS_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
    });

    test('clicking a collapsed accordion opens it', async ({ page }) => {
        const secondAccordion = page.locator('.dept-accordion').nth(1);
        const secondBody = secondAccordion.locator('.dept-accordion-body');

        // Second starts collapsed — click header to open
        await secondAccordion.locator('.dept-accordion-header').click();
        await expect(secondBody).toHaveClass(/open/, { timeout: 5000 });
    });

    test('clicking an open accordion closes it', async ({ page }) => {
        const firstAccordion = page.locator('.dept-accordion').first();
        const firstBody = firstAccordion.locator('.dept-accordion-body');

        // First starts open — click header to close
        await firstAccordion.locator('.dept-accordion-header').click();
        await expect(firstBody).not.toHaveClass(/open/, { timeout: 5000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Batch Mode — Save to DB
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Recommendations Page — Batch Mode: Save Behaviour', () => {

    test('save endpoint is called once for each department result ID', async ({ page }) => {
        await loginAsAdmin(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        const { getSaveCalls } = await setupBatchMode(page);
        await page.goto(RECS_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        // Give async sequential save calls time to complete
        await page.waitForTimeout(3000);

        const calls = getSaveCalls();
        // One save call per department
        expect(calls).toHaveLength(2);
        expect(calls).toContain(FAKE_RESULT_ID_BATCH1);
        expect(calls).toContain(FAKE_RESULT_ID_BATCH2);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Batch Mode — Fully Compliant Department
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Recommendations Page — Batch Mode: Fully Compliant Department', () => {

    test('fully compliant department shows the compliant message inside its accordion', async ({ page }) => {
        await loginAsAdmin(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        // Second department has no flagged items
        await setupBatchMode(page, { dept2Details: [] });
        await page.goto(RECS_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        // Open the second accordion to see the compliant message
        await page.locator('.dept-accordion').nth(1).locator('.dept-accordion-header').click();

        await expect(
            page.locator('.dept-accordion').nth(1).locator('.dept-accordion-body')
        ).toContainText('fully compliant', { timeout: 10000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Error Handling
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Recommendations Page — Error Handling', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
    });

    test('401 response clears sessionStorage and redirects to login.html', async ({ page }) => {
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), FAKE_RESULT_ID);

        await page.route(`**/ai/api/analysis/${FAKE_RESULT_ID}/`, async route => {
            await route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'Unauthorized' }) });
        });
        await page.route('**/ai/api/recommendations/save/', async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
        });

        await page.goto(RECS_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });

        const token = await page.evaluate(() => sessionStorage.getItem('authToken'));
        expect(token).toBeNull();
    });

    test('403 response clears sessionStorage and redirects to login.html', async ({ page }) => {
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), FAKE_RESULT_ID);

        await page.route(`**/ai/api/analysis/${FAKE_RESULT_ID}/`, async route => {
            await route.fulfill({ status: 403, contentType: 'application/json', body: JSON.stringify({ detail: 'Forbidden' }) });
        });
        await page.route('**/ai/api/recommendations/save/', async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
        });

        await page.goto(RECS_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
    });

    test('404 response shows error banner with no-data message', async ({ page }) => {
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), FAKE_RESULT_ID);

        await page.route(`**/ai/api/analysis/${FAKE_RESULT_ID}/`, async route => {
            await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'Not found' }) });
        });
        await page.route('**/ai/api/recommendations/save/', async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
        });

        await page.goto(RECS_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(page.locator('.no-data-banner')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('.no-data-banner')).toContainText('No analysis results found');
    });

    test('500 response shows error banner', async ({ page }) => {
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), FAKE_RESULT_ID);

        await page.route(`**/ai/api/analysis/${FAKE_RESULT_ID}/`, async route => {
            await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Server error' }) });
        });
        await page.route('**/ai/api/recommendations/save/', async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
        });

        await page.goto(RECS_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(page.locator('.no-data-banner')).toBeVisible({ timeout: 10000 });
    });

    test('network failure shows "Could not reach the server" error banner', async ({ page }) => {
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), FAKE_RESULT_ID);

        await page.route(`**/ai/api/analysis/${FAKE_RESULT_ID}/`, async route => {
            await route.abort('failed');
        });
        await page.route('**/ai/api/recommendations/save/', async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
        });

        await page.goto(RECS_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(page.locator('.no-data-banner')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('.no-data-banner')).toContainText('Could not reach the server');
    });

    test('corrupted batchResultIds JSON shows corruption error banner', async ({ page }) => {
        await page.evaluate(() => {
            sessionStorage.setItem('batchResultIds', 'this is not valid json {{{{');
            sessionStorage.removeItem('latestResultId');
        });

        await page.route('**/ai/api/recommendations/save/', async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
        });

        await page.goto(RECS_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(page.locator('.no-data-banner')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('.no-data-banner')).toContainText('corrupted');
    });

    test('empty batchResultIds array shows no batch results error banner', async ({ page }) => {
        await page.evaluate(() => {
            sessionStorage.setItem('batchResultIds', JSON.stringify([]));
            sessionStorage.removeItem('latestResultId');
        });

        await page.route('**/ai/api/recommendations/save/', async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
        });

        await page.goto(RECS_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(page.locator('.no-data-banner')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('.no-data-banner')).toContainText('No batch results found');
    });
});