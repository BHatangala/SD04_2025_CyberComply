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
//   - Department dropdown (single and multi-dept)
//   - Compliance score displayed in metrics card
//   - Risk level pill derived from score (Low / Medium / High)
//   - Risk pill CSS class changes with risk level
//   - Graphical View button gated behind isAdmin && hasMultipleDepartments
//   - Departmental recommendations rendered from all_recommendations
//   - buildReferenceFromId() produces correct PDPA reference string
//   - Compliant-only result shows "fully compliant" empty state
//   - Single file path (latestResultId in sessionStorage)
//   - Batch path (batchResultIds in sessionStorage)
//   - Corrupted / empty batchResultIds shows error banner
//   - Sidebar: open by default, toggle, shifted class on back/home/content
//   - Navigation: back arrow → document_analysis.html, home → home.html, profile → profile.html
//
// MOCKING STRATEGY
//   All route mocks use RegExp with /?$ to match URLs with or without trailing
//   slash. page.unrouteAll() is called inside loadPageWithData when
//   freshRoutes: true (the default). Pass freshRoutes: false after
//   loginAsGeneral/loginAsAdmin to preserve the auth session.
// ─────────────────────────────────────────────────────────────────────────────

const { test, expect } = require('@playwright/test');
const {
    loginAsGeneral,
    loginAsAdmin,
} = require('./helpers/helper_login');

// ── URLs & route patterns ─────────────────────────────────────────────────────
const COMP_URL  = './comparison.html';
const RESULT_ID = '42';

const reResult  = (id) => new RegExp(`/ai/api/analysis/${id}/?$`);
const reOrgComp = /\/ai\/api\/analysis\/org-comparison\//;

// ── Shared fake data — SINGLE FILE PATH ──────────────────────────────────────
// Shape matches what the new mounted() single-file branch reads from the API.
// The page builds a synthetic dept object from this response.

const SINGLE_DETAILS_MIXED = [
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

const SINGLE_DETAILS_COMPLIANT = [
    {
        requirement_id: 'SL-PDPA-S10-1',
        clause:         'Security of personal data',
        status:         'compliant',
        risk_level:     'low',
        reasoning:      'Security controls are in place.',
    },
];

function makeSingleResult(details, overrides = {}) {
    return {
        result_id:        RESULT_ID,
        company_name:     'Test Corp',
        department:       'IT',
        compliance_score: 60,
        compliance:       { details },
        ...overrides,
    };
}

const SINGLE_MIXED     = makeSingleResult(SINGLE_DETAILS_MIXED);
const SINGLE_COMPLIANT = makeSingleResult(SINGLE_DETAILS_COMPLIANT, { compliance_score: 100 });
const SINGLE_HIGH      = makeSingleResult(SINGLE_DETAILS_MIXED, { compliance_score: 80 });
const SINGLE_LOW       = makeSingleResult(SINGLE_DETAILS_MIXED, { compliance_score: 30 });

// ── Shared fake data — BATCH PATH ─────────────────────────────────────────────
// Shape matches what the new mounted() batch branch reads from org-comparison API.

const BATCH_RESULT_IDS = ['42', '43'];

const BATCH_DEPT_IT = {
    id:               '42',
    dept_name:        'IT',
    compliance_score: 60,
    risk:             'Medium',
    improvements:     2,
    top_gap:          'Lawful basis for processing personal data',
    improvement_list: [
        'Lawful basis for processing personal data',
        'Data subject access rights',
    ],
    recommended_actions: [
        'Section 6(1) of the Personal Data Protection Act No. 9 of 2022 (Sri Lanka)',
        'Section 23(1) of the Personal Data Protection Act No. 9 of 2022 (Sri Lanka)',
    ],
    all_recommendations: [
        {
            clause:     'Lawful basis for processing personal data',
            reference:  'Section 6(1) of the Personal Data Protection Act No. 9 of 2022 (Sri Lanka)',
            status:     'non_compliant',
            risk_level: 'critical',
            reasoning:  'No evidence of a lawful basis documented.',
        },
        {
            clause:     'Data subject access rights',
            reference:  'Section 23(1) of the Personal Data Protection Act No. 9 of 2022 (Sri Lanka)',
            status:     'partial',
            risk_level: 'high',
            reasoning:  'Access rights process exists but is incomplete.',
        },
    ],
};

const BATCH_DEPT_HR = {
    id:               '43',
    dept_name:        'HR',
    compliance_score: 80,
    risk:             'Low',
    improvements:     0,
    top_gap:          'None identified',
    improvement_list: [],
    recommended_actions: [],
    all_recommendations: [],
};

const BATCH_RESPONSE_MULTI = {
    org_name:    'Test Corp',
    departments: [BATCH_DEPT_IT, BATCH_DEPT_HR],
};

const BATCH_RESPONSE_SINGLE = {
    org_name:    'Test Corp',
    departments: [BATCH_DEPT_IT],
};

// ── Shared page loader — SINGLE FILE PATH ────────────────────────────────────
async function loadSinglePath(page, result = SINGLE_MIXED, { freshRoutes = true } = {}) {
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
    await page.evaluate(() => sessionStorage.removeItem('batchResultIds'));
    await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
    await page.goto(COMP_URL);
    await page.waitForLoadState('networkidle', { timeout: 15000 });
}

// ── Shared page loader — BATCH PATH ──────────────────────────────────────────
async function loadBatchPath(page, batchResponse = BATCH_RESPONSE_MULTI, { freshRoutes = true } = {}) {
    if (freshRoutes) {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
    }
    await page.route(reOrgComp, async route => {
        await route.fulfill({
            status:      200,
            contentType: 'application/json',
            body:        JSON.stringify(batchResponse),
        });
    });
    await page.evaluate((ids) => sessionStorage.setItem('batchResultIds', JSON.stringify(ids)), BATCH_RESULT_IDS);
    await page.evaluate(() => sessionStorage.removeItem('latestResultId'));
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

    test('redirects to login.html when single-file API returns 401', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(() => sessionStorage.removeItem('batchResultIds'));
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Unauthorized"}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
    });

    test('redirects to login.html when single-file API returns 403', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(() => sessionStorage.removeItem('batchResultIds'));
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 403, contentType: 'application/json', body: '{"detail":"Forbidden"}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
    });

    test('redirects to login.html when batch API returns 401', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((ids) => sessionStorage.setItem('batchResultIds', JSON.stringify(ids)), BATCH_RESULT_IDS);
        await page.route(reOrgComp, async route => {
            await route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Unauthorized"}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
    });

    test('clears sessionStorage before redirecting on 401', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(() => sessionStorage.removeItem('batchResultIds'));
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
        await loadSinglePath(page, SINGLE_MIXED, { freshRoutes: false });
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

    test('shows no-data banner when single-file API returns 404', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(() => sessionStorage.removeItem('batchResultIds'));
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Not found"}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.no-data-banner')).toBeVisible();
    });

    test('shows no-data banner when single-file API returns 500', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(() => sessionStorage.removeItem('batchResultIds'));
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Server error"}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.no-data-banner')).toBeVisible();
    });

    test('shows no-data banner when batch API returns 404', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((ids) => sessionStorage.setItem('batchResultIds', JSON.stringify(ids)), BATCH_RESULT_IDS);
        await page.route(reOrgComp, async route => {
            await route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Not found"}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.no-data-banner')).toBeVisible();
    });

    test('shows error banner when network request aborts', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(() => sessionStorage.removeItem('batchResultIds'));
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
        await page.evaluate(() => sessionStorage.removeItem('batchResultIds'));
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.route(reResult(RESULT_ID), async route => {
            await route.abort();
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.no-data-banner')).toContainText('Could not reach the server');
    });

    test('shows error banner when batchResultIds is corrupted JSON', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(() => sessionStorage.setItem('batchResultIds', 'not-valid-json'));
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.no-data-banner')).toBeVisible();
    });

    test('corrupted batchResultIds banner mentions re-run', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(() => sessionStorage.setItem('batchResultIds', 'not-valid-json'));
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.no-data-banner')).toContainText('corrupted');
    });

    test('shows error banner when batchResultIds is empty array', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(() => sessionStorage.setItem('batchResultIds', JSON.stringify([])));
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.no-data-banner')).toBeVisible();
    });

    test('shows error banner when neither batchResultIds nor latestResultId exists', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(() => {
            sessionStorage.removeItem('batchResultIds');
            sessionStorage.removeItem('latestResultId');
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(COMP_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.no-data-banner')).toBeVisible();
    });

    test('no error banner shown when single-file data loads successfully', async ({ page }) => {
        await loginAsGeneral(page);
        await loadSinglePath(page, SINGLE_MIXED, { freshRoutes: false });
        await expect(page.locator('.no-data-banner')).not.toBeVisible();
    });

    test('no error banner shown when batch data loads successfully', async ({ page }) => {
        await loginAsGeneral(page);
        await loadBatchPath(page, BATCH_RESPONSE_MULTI, { freshRoutes: false });
        await expect(page.locator('.no-data-banner')).not.toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Company Name
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Comparison — Company Name', () => {

    test('company name is displayed from single-file API response', async ({ page }) => {
        await loginAsGeneral(page);
        await loadSinglePath(page, SINGLE_MIXED, { freshRoutes: false });
        await expect(page.locator('.company-name')).toContainText('Test Corp');
    });

    test('company name is displayed from batch API response', async ({ page }) => {
        await loginAsGeneral(page);
        await loadBatchPath(page, BATCH_RESPONSE_MULTI, { freshRoutes: false });
        await expect(page.locator('.company-name')).toContainText('Test Corp');
    });

    test('company name label prefix is shown', async ({ page }) => {
        await loginAsGeneral(page);
        await loadSinglePath(page, SINGLE_MIXED, { freshRoutes: false });
        await expect(page.locator('.company-name')).toContainText('Company Name');
    });

    test('company name hidden when no data loaded', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(() => sessionStorage.removeItem('batchResultIds'));
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
// Department Dropdown
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Comparison — Department Dropdown', () => {

    test('department dropdown is visible in single-file mode', async ({ page }) => {
        await loginAsGeneral(page);
        await loadSinglePath(page, SINGLE_MIXED, { freshRoutes: false });
        await expect(page.locator('.dept-select')).toBeVisible({ timeout: 10000 });
    });

    test('department dropdown shows department name in single-file mode', async ({ page }) => {
        await loginAsGeneral(page);
        await loadSinglePath(page, SINGLE_MIXED, { freshRoutes: false });
        await expect(page.locator('.dept-select')).toContainText('IT Department');
    });

    test('department dropdown is visible in batch mode', async ({ page }) => {
        await loginAsGeneral(page);
        await loadBatchPath(page, BATCH_RESPONSE_MULTI, { freshRoutes: false });
        await expect(page.locator('.dept-select')).toBeVisible({ timeout: 10000 });
    });

    test('department dropdown shows all departments in batch mode', async ({ page }) => {
        await loginAsGeneral(page);
        await loadBatchPath(page, BATCH_RESPONSE_MULTI, { freshRoutes: false });
        await expect(page.locator('.dept-select')).toContainText('IT Department');
        await expect(page.locator('.dept-select')).toContainText('HR Department');
    });

    test('first department is auto-selected on batch load', async ({ page }) => {
        await loginAsGeneral(page);
        await loadBatchPath(page, BATCH_RESPONSE_MULTI, { freshRoutes: false });
        const value = await page.locator('.dept-select').inputValue();
        expect(value).toBe('IT');
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Score and Risk Level
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Comparison — Score and Risk Level', () => {

    test('compliance score is displayed in metrics card (single-file)', async ({ page }) => {
        await loginAsGeneral(page);
        await loadSinglePath(page, SINGLE_MIXED, { freshRoutes: false });
        await expect(page.locator('.metrics-score-value')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('.metrics-score-value')).toContainText('60%');
    });

    test('compliance score is displayed in metrics card (batch)', async ({ page }) => {
        await loginAsGeneral(page);
        await loadBatchPath(page, BATCH_RESPONSE_MULTI, { freshRoutes: false });
        await expect(page.locator('.metrics-score-value')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('.metrics-score-value')).toContainText('60%');
    });

    test('risk pill shows MEDIUM when score is 60', async ({ page }) => {
        await loginAsGeneral(page);
        await loadSinglePath(page, SINGLE_MIXED, { freshRoutes: false });
        await expect(page.locator('.risk-pill')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('.risk-pill')).toContainText('MEDIUM');
    });

    test('risk pill shows LOW when score is 80 (>= 75)', async ({ page }) => {
        await loginAsGeneral(page);
        await loadSinglePath(page, SINGLE_HIGH, { freshRoutes: false });
        await expect(page.locator('.risk-pill')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('.risk-pill')).toContainText('LOW');
    });

    test('risk pill shows HIGH when score is 30 (< 40)', async ({ page }) => {
        await loginAsGeneral(page);
        await loadSinglePath(page, SINGLE_LOW, { freshRoutes: false });
        await expect(page.locator('.risk-pill')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('.risk-pill')).toContainText('HIGH');
    });

    test('risk pill has medium CSS class when score is 60', async ({ page }) => {
        await loginAsGeneral(page);
        await loadSinglePath(page, SINGLE_MIXED, { freshRoutes: false });
        await expect(page.locator('.risk-pill')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('.risk-pill')).toHaveClass(/medium/);
    });

    test('risk pill has low CSS class when score is 80', async ({ page }) => {
        await loginAsGeneral(page);
        await loadSinglePath(page, SINGLE_HIGH, { freshRoutes: false });
        await expect(page.locator('.risk-pill')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('.risk-pill')).toHaveClass(/low/);
    });

    test('risk pill has high CSS class when score is 30', async ({ page }) => {
        await loginAsGeneral(page);
        await loadSinglePath(page, SINGLE_LOW, { freshRoutes: false });
        await expect(page.locator('.risk-pill')).toBeVisible({ timeout: 10000 });
        await expect(page.locator('.risk-pill')).toHaveClass(/high/);
    });

    test('metrics card is visible when data is loaded', async ({ page }) => {
        await loginAsGeneral(page);
        await loadSinglePath(page, SINGLE_MIXED, { freshRoutes: false });
        await expect(page.locator('.metrics-card')).toBeVisible({ timeout: 10000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Graphical View Button (RBAC gate)
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Comparison — Graphical View Button', () => {

    test('Graphical View button is NOT shown to general user even with multiple departments', async ({ page }) => {
        await loginAsGeneral(page);
        await loadBatchPath(page, BATCH_RESPONSE_MULTI, { freshRoutes: false });
        await expect(page.locator('.graphical-view-btn')).not.toBeVisible();
    });

    test('Graphical View button is NOT shown to admin when only one department', async ({ page }) => {
        await loginAsAdmin(page);
        await loadBatchPath(page, BATCH_RESPONSE_SINGLE, { freshRoutes: false });
        await expect(page.locator('.graphical-view-btn')).not.toBeVisible();
    });

    test('Graphical View button IS shown to admin when multiple departments analysed', async ({ page }) => {
        await loginAsAdmin(page);
        await loadBatchPath(page, BATCH_RESPONSE_MULTI, { freshRoutes: false });
        await expect(page.locator('.graphical-view-btn')).toBeVisible({ timeout: 10000 });
    });

    test('Graphical View button navigates to comparison_dashboard_graphical.html', async ({ page }) => {
        await loginAsAdmin(page);
        await loadBatchPath(page, BATCH_RESPONSE_MULTI, { freshRoutes: false });
        await expect(page.locator('.graphical-view-btn')).toBeVisible({ timeout: 10000 });
        await page.locator('.graphical-view-btn').click();
        await page.waitForURL(/comparison_dashboard_graphical\.html/, { timeout: 10000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Departmental Recommendations
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Comparison — Departmental Recommendations', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadSinglePath(page, SINGLE_MIXED, { freshRoutes: false });
    });

    test('recommendations section is visible', async ({ page }) => {
        await expect(page.locator('.recommendations-section')).toBeVisible();
    });

    test('recommendations section title shows correct heading', async ({ page }) => {
        await expect(page.locator('.rec-title')).toContainText('Department Specific Recommendation Summary');
    });

    test('non_compliant item is shown in recommendations list', async ({ page }) => {
        const items = page.locator('.rec-list > li');
        await expect(items.first()).toContainText('Lawful basis for processing personal data');
    });

    test('partial item is also shown in recommendations list', async ({ page }) => {
        const items = page.locator('.rec-list > li');
        await expect(items).toHaveCount(2);
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

    test('recommendations update when department is switched in batch mode', async ({ page }) => {
        await loginAsGeneral(page);
        await loadBatchPath(page, BATCH_RESPONSE_MULTI, { freshRoutes: false });
        // IT dept has 2 recommendations, HR has 0
        await expect(page.locator('.rec-list > li')).toHaveCount(2);
        await page.locator('.dept-select').selectOption('HR');
        await expect(page.locator('.rec-list > li')).toHaveCount(1); // empty state li
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// buildReferenceFromId — PDPA reference string construction
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Comparison — buildReferenceFromId', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadSinglePath(page, SINGLE_MIXED, { freshRoutes: false });
    });

    test('converts SL-PDPA-S6-1 to correct section reference', async ({ page }) => {
        const refs = page.locator('.sub-rec-list li');
        await expect(refs.first()).toContainText('Section 6(1)');
    });

    test('converts SL-PDPA-S23-1 to correct section reference', async ({ page }) => {
        const refs = page.locator('.sub-rec-list li');
        await expect(refs.nth(1)).toContainText('Section 23(1)');
    });

    test('reference string includes Act name and year', async ({ page }) => {
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
        await loadSinglePath(page, SINGLE_COMPLIANT, { freshRoutes: false });
        await expect(page.locator('.rec-list')).toContainText('No recommendations');
    });

    test('only the empty-state list item is present when all compliant', async ({ page }) => {
        await loginAsGeneral(page);
        await loadSinglePath(page, SINGLE_COMPLIANT, { freshRoutes: false });
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
        await loadSinglePath(page, SINGLE_MIXED, { freshRoutes: false });
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
        await expect(page.locator('.menu-icon')).toBeVisible({ timeout: 10000 });
        await page.locator('.menu-icon').click();
        await expect(page.locator('.main-content')).not.toHaveClass(/shifted/);
    });

    test('re-opening sidebar restores shifted class on main content', async ({ page }) => {
        await expect(page.locator('.menu-icon')).toBeVisible({ timeout: 10000 });
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
        await loadSinglePath(page, SINGLE_MIXED, { freshRoutes: false });
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