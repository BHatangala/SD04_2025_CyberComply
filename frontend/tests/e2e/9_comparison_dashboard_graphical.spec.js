// tests/e2e/9_comparison_dashboard_graphical.spec.js
// ─────────────────────────────────────────────────────────────────────────────
// Comparison Dashboard Graphical page (comparison_dashboard_graphical.html)
//
// Covers:
//   - Auth guard: no token → login.html, general user → comparison.html,
//     admin user → stays on page
//   - sessionStorage cleared before redirect on 401
//   - Page rendering with mocked org-comparison data
//   - Dashboard controls: risk filter, sort by, sort order, reset
//   - Ranking table: department rows, compliance %, risk pills
//   - Modal (drill-down): opens on row click, shows department details,
//     improvement list, recommended actions (from mocked clause_summaries.json)
//   - Modal closes on X button and backdrop click
//   - Navigation: back arrow → comparison.html, user profile → profile.html
//   - Error states: missing batchResultIds, 401 redirect + sessionStorage clear,
//     500 → loadError banner, network abort → "Could not reach the server"
//   - Sidebar: open by default, toggle, shifted class on back arrow and
//     main content
//
// MOCKING STRATEGY
//   page.unrouteAll() is called at the start of every loadPageWithResult call
//   so stale routes from previous tests never bleed into subsequent ones.
//   All route mocks use RegExp with /?$ to handle Django trailing-slash URLs.
//   clause_summaries.json is mocked as a static route so modal content is
//   fully predictable and the test is self-contained.
// ─────────────────────────────────────────────────────────────────────────────

const { test, expect } = require('@playwright/test');
const {
    loginAsAdmin,
    loginAsGeneral,
} = require('./helpers/helper_login');

const CDG_URL = './comparison_dashboard_graphical.html';

// Two fake UUIDs — used as batch result IDs
const RESULT_ID_1 = 'aaaaaaaa-1111-2222-3333-cccccccccccc';
const RESULT_ID_2 = 'bbbbbbbb-4444-5555-6666-dddddddddddd';

// ── Regex route helpers ───────────────────────────────────────────────────────

const reOrgComparison = new RegExp(`/ai/api/analysis/org-comparison/`);
const reClauseSummaries = /clause_summaries\.json/;

// ── Fake API responses ────────────────────────────────────────────────────────
//
// The org-comparison endpoint returns { org_name, departments[] }.
// Each department matches the backend field names that the frontend normalises
// in mounted() — dept_name, compliance_score, risk, improvements, top_gap,
// improvement_list, recommended_actions.
//
// top_gap and improvement_list are sent as objects { clause, requirement_id }
// since that is the real backend format — this exercises the normalization
// code in the frontend that handles both strings and objects.
//
// Two departments: one High risk (low compliance) and one Medium risk (higher
// compliance). This lets us test the risk filter (show only High, show only
// Medium) and sort order meaningfully.

const FAKE_ORG_RESPONSE = {
    org_name: 'Acme Corporation',
    departments: [
        {
            id:                 'dept-1',
            dept_name:          'Finance',
            compliance_score:   38,
            risk:               'High',
            improvements:       4,
            top_gap:            { clause: 'Data Retention Policy', requirement_id: 'SL-PDPA-S11-1' },
            improvement_list:   [
                { clause: 'Data Retention Policy',   requirement_id: 'SL-PDPA-S11-1' },
                { clause: 'Consent Documentation',   requirement_id: 'SL-PDPA-S6-1'  },
            ],
            recommended_actions: [],
        },
        {
            id:                 'dept-2',
            dept_name:          'HR',
            compliance_score:   71,
            risk:               'Medium',
            improvements:       2,
            top_gap:            { clause: 'Access Control Procedures', requirement_id: 'SL-PDPA-S9-1' },
            improvement_list:   [
                { clause: 'Access Control Procedures', requirement_id: 'SL-PDPA-S9-1' },
            ],
            recommended_actions: [],
        },
    ],
};

// Clause summaries map — mocked as clause_summaries.json.
// Maps requirement_id → short plain-English action sentence.
// We define entries for the IDs used in FAKE_ORG_RESPONSE so the modal's
// recommended actions are fully predictable in tests.
const FAKE_CLAUSE_SUMMARIES = {
    'SL-PDPA-S11-1': 'Establish and document a clear data retention schedule.',
    'SL-PDPA-S6-1':  'Obtain and record explicit consent from all data subjects.',
    'SL-PDPA-S9-1':  'Implement role-based access controls and audit logs.',
};

// ── Shared helper: load the page with mocked data ─────────────────────────────
//
// Clears stale routes, mocks the org-comparison endpoint and the static
// clause_summaries.json file, seeds batchResultIds into sessionStorage,
// then navigates to the page and waits for full load.
//
// @param {import('@playwright/test').Page} page
// @param {object} orgResponse    - Fake org-comparison response to fulfill
// @param {object} options
// @param {boolean} options.seedBatchIds - Whether to write batchResultIds to sessionStorage
// @param {object|null} options.clauseSummaries - Clause summaries to mock (null = let it 404)

async function loadPageWithResult(
    page,
    orgResponse = FAKE_ORG_RESPONSE,
    { seedBatchIds = true, clauseSummaries = FAKE_CLAUSE_SUMMARIES } = {}
) {
    await page.unrouteAll({ behavior: 'ignoreErrors' });

    // Mock: org-comparison endpoint
    await page.route(reOrgComparison, async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(orgResponse),
        });
    });

    // Mock: clause_summaries.json static file
    // This makes modal recommended-action content deterministic.
    if (clauseSummaries) {
        await page.route(reClauseSummaries, async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify(clauseSummaries),
            });
        });
    } else {
        // Simulate missing file — the page should warn and continue
        await page.route(reClauseSummaries, async route => {
            await route.fulfill({ status: 404 });
        });
    }

    if (seedBatchIds) {
        await page.evaluate(
            ([id1, id2]) => sessionStorage.setItem('batchResultIds', JSON.stringify([id1, id2])),
            [RESULT_ID_1, RESULT_ID_2]
        );
    }

    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
    await page.goto(CDG_URL);
    await page.waitForLoadState('networkidle', { timeout: 15000 });
}

// ─────────────────────────────────────────────────────────────────────────────
// Auth Guard
// ─────────────────────────────────────────────────────────────────────────────
//
// This page has a two-step auth guard in mounted():
//   1. No authToken in sessionStorage → redirect to login.html
//   2. Role is not ADMINISTRATIVE_USER → redirect to comparison.html
//
// Admin users pass both checks and stay on the page.

test.describe('Comparison Dashboard Graphical — Auth Guard', () => {

    test('redirects to login.html when no authToken in sessionStorage', async ({ page }) => {
        await page.goto('./welcome.html');
        await page.evaluate(() => sessionStorage.clear());
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(CDG_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
    });

    test('redirects to comparison.html when user is a general user', async ({ page }) => {
        // General users have authToken but role !== ADMINISTRATIVE_USER.
        // The page should send them back to the single-result comparison view.
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(
            ([id1, id2]) => sessionStorage.setItem('batchResultIds', JSON.stringify([id1, id2])),
            [RESULT_ID_1, RESULT_ID_2]
        );
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(CDG_URL);
        await page.waitForURL(/comparison\.html/, { timeout: 10000 });
    });

    test('admin user stays on comparison_dashboard_graphical.html', async ({ page }) => {
        await loginAsAdmin(page);
        await loadPageWithResult(page);
        await expect(page).toHaveURL(/comparison_dashboard_graphical\.html/);
    });

    test('redirects to login.html when API returns 401', async ({ page }) => {
        await loginAsAdmin(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(
            ([id1, id2]) => sessionStorage.setItem('batchResultIds', JSON.stringify([id1, id2])),
            [RESULT_ID_1, RESULT_ID_2]
        );
        await page.route(reOrgComparison, async route => {
            await route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Unauthorized"}' });
        });
        await page.route(reClauseSummaries, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(CDG_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
    });

    test('sessionStorage is cleared before redirect on 401', async ({ page }) => {
        await loginAsAdmin(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(
            ([id1, id2]) => sessionStorage.setItem('batchResultIds', JSON.stringify([id1, id2])),
            [RESULT_ID_1, RESULT_ID_2]
        );
        await page.route(reOrgComparison, async route => {
            await route.fulfill({ status: 401, contentType: 'application/json', body: '{}' });
        });
        await page.route(reClauseSummaries, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(CDG_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });

        const token = await page.evaluate(() => sessionStorage.getItem('authToken'));
        expect(token).toBeNull();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Page Rendering
// ─────────────────────────────────────────────────────────────────────────────
//
// With valid mocked data, the dashboard should render its main structural
// elements: title, controls, chart card, and ranking table card.

test.describe('Comparison Dashboard Graphical — Page Rendering', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await loadPageWithResult(page);
    });

    test('page loads and stays on comparison_dashboard_graphical.html', async ({ page }) => {
        await expect(page).toHaveURL(/comparison_dashboard_graphical\.html/);
    });

    test('COMPARISON DASHBOARD heading is visible', async ({ page }) => {
        await expect(page.locator('.dashboard-title-main')).toContainText('COMPARISON DASHBOARD');
    });

    test('Graphical view subtitle is visible', async ({ page }) => {
        await expect(page.locator('.dashboard-title-sub')).toContainText('Graphical view');
    });

    test('company label shows org name from API', async ({ page }) => {
        await expect(page.locator('.company-label')).toContainText('Acme Corporation');
    });

    test('controls bar is visible', async ({ page }) => {
        await expect(page.locator('.controls-wrap')).toBeVisible();
    });

    test('department comparison chart card is visible', async ({ page }) => {
        await expect(page.locator('.card').first()).toBeVisible();
    });

    test('ranking table card is visible', async ({ page }) => {
        await expect(page.locator('.table')).toBeVisible();
    });

    test('top header with menu icon and user profile are visible', async ({ page }) => {
        await expect(page.locator('.top-header')).toBeVisible();
        await expect(page.locator('.menu-icon')).toBeVisible();
        await expect(page.locator('.user-profile')).toBeVisible();
    });

    test('back arrow is visible', async ({ page }) => {
        await expect(page.locator('.back-arrow')).toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Ranking Table
// ─────────────────────────────────────────────────────────────────────────────
//
// The ranking table lists all displayed departments with their compliance %,
// risk pill, and top gap. It is populated from the displayedDepartments
// computed property which derives from the mocked departments array.

test.describe('Comparison Dashboard Graphical — Ranking Table', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await loadPageWithResult(page);
    });

    test('ranking table shows both departments', async ({ page }) => {
        const rows = page.locator('.table tbody tr.row-click');
        await expect(rows).toHaveCount(2);
    });

    test('Finance department row is visible', async ({ page }) => {
        await expect(page.locator('.table tbody')).toContainText('Finance');
    });

    test('HR department row is visible', async ({ page }) => {
        await expect(page.locator('.table tbody')).toContainText('HR');
    });

    test('compliance percentages are displayed in the table', async ({ page }) => {
        await expect(page.locator('.table tbody')).toContainText('38%');
        await expect(page.locator('.table tbody')).toContainText('71%');
    });

    test('risk pills are displayed in the table', async ({ page }) => {
        await expect(page.locator('.table tbody')).toContainText('High');
        await expect(page.locator('.table tbody')).toContainText('Medium');
    });

    test('Finance row top gap text is visible in the table', async ({ page }) => {
        await expect(page.locator('.table tbody')).toContainText('Data Retention Policy');
    });

    test('each row has a View button', async ({ page }) => {
        const viewButtons = page.locator('.table tbody .mini-btn');
        await expect(viewButtons).toHaveCount(2);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Dashboard Controls — Filter & Sort
// ─────────────────────────────────────────────────────────────────────────────
//
// The controls bar has three dropdowns: Risk Filter, Sort By, Sort Order.
// Changing the risk filter narrows which departments appear in the table.
// The reset button restores all three selects to their default values.
//
// We test by interacting with the selects and observing which rows remain
// in the table — this exercises the displayedDepartments computed property.

test.describe('Comparison Dashboard Graphical — Controls', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await loadPageWithResult(page);
    });

    test('risk filter dropdown is visible', async ({ page }) => {
        await expect(page.locator('select.select').first()).toBeVisible();
    });

    test('filtering by High risk shows only Finance department', async ({ page }) => {
        await page.locator('select.select').first().selectOption('High');
        const rows = page.locator('.table tbody tr.row-click');
        await expect(rows).toHaveCount(1);
        await expect(page.locator('.table tbody')).toContainText('Finance');
        await expect(page.locator('.table tbody')).not.toContainText('HR');
    });

    test('filtering by Medium risk shows only HR department', async ({ page }) => {
        await page.locator('select.select').first().selectOption('Medium');
        const rows = page.locator('.table tbody tr.row-click');
        await expect(rows).toHaveCount(1);
        await expect(page.locator('.table tbody')).toContainText('HR');
        await expect(page.locator('.table tbody')).not.toContainText('Finance');
    });

    test('filtering by Low risk shows empty state message', async ({ page }) => {
        await page.locator('select.select').first().selectOption('Low');
        await expect(
            page.locator('.table tbody td:has-text("No departments match")')
        ).toBeVisible();
    });

    test('reset button restores All filter and shows both departments', async ({ page }) => {
        await page.locator('select.select').first().selectOption('High');
        await expect(page.locator('.table tbody tr.row-click')).toHaveCount(1);

        await page.locator('.btn:has-text("Reset")').click();

        await expect(page.locator('.table tbody tr.row-click')).toHaveCount(2);
        await expect(page.locator('select.select').first()).toHaveValue('All');
    });

    test('reset button restores Sort By to compliance', async ({ page }) => {
        const selects = page.locator('select.select');
        await selects.nth(1).selectOption('risk');
        await page.locator('.btn:has-text("Reset")').click();
        await expect(selects.nth(1)).toHaveValue('compliance');
    });

    test('reset button restores Sort Order to desc', async ({ page }) => {
        const selects = page.locator('select.select');
        await selects.nth(2).selectOption('asc');
        await page.locator('.btn:has-text("Reset")').click();
        await expect(selects.nth(2)).toHaveValue('desc');
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Modal — Drill-Down Detail
// ─────────────────────────────────────────────────────────────────────────────
//
// Clicking a table row calls openDept(), which:
//   1. Looks up the department from this.departments
//   2. Resolves recommended actions from clauseSummaries (the mocked JSON)
//   3. Normalises improvementList to plain strings
//   4. Opens the modal with selectedDept populated
//
// We test that the modal opens, shows correct content, and closes correctly.
// Because clause_summaries.json is mocked with known values, the recommended
// actions shown in the modal are fully deterministic.

test.describe('Comparison Dashboard Graphical — Modal', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await loadPageWithResult(page);
    });

    test('clicking a table row opens the modal', async ({ page }) => {
        await page.locator('.table tbody tr.row-click').first().click();
        await expect(page.locator('.modal-backdrop')).toBeVisible();
    });

    test('modal shows the correct department name', async ({ page }) => {
        // Default sort is compliance desc — HR (71%) appears first, Finance (38%) second
        await page.locator('.table tbody tr.row-click').first().click();
        await expect(page.locator('.modal-title')).toContainText('HR');
    });

    test('modal shows the compliance score for the department', async ({ page }) => {
        await page.locator('.table tbody tr.row-click').first().click();
        await expect(page.locator('.modal-body')).toContainText('71%');
    });

    test('modal shows the risk level for the department', async ({ page }) => {
        await page.locator('.table tbody tr.row-click').first().click();
        await expect(page.locator('.modal-body')).toContainText('Medium');
    });

    test('modal shows the top gap for the department', async ({ page }) => {
        await page.locator('.table tbody tr.row-click').first().click();
        await expect(page.locator('.modal-body')).toContainText('Access Control Procedures');
    });

    test('modal shows improvement list items', async ({ page }) => {
        await page.locator('.table tbody tr.row-click').first().click();
        await expect(page.locator('.modal-body .bullets').first()).toContainText('Access Control Procedures');
    });

    test('modal shows recommended actions derived from clause summaries', async ({ page }) => {
        // HR department has SL-PDPA-S9-1 — mapped in FAKE_CLAUSE_SUMMARIES
        await page.locator('.table tbody tr.row-click').first().click();
        await expect(page.locator('.modal-body')).toContainText('Implement role-based access controls and audit logs.');
    });

    test('clicking the View button on a row also opens the modal', async ({ page }) => {
        await page.locator('.table tbody .mini-btn').first().click();
        await expect(page.locator('.modal-backdrop')).toBeVisible();
    });

    test('modal closes when X button is clicked', async ({ page }) => {
        await page.locator('.table tbody tr.row-click').first().click();
        await expect(page.locator('.modal-backdrop')).toBeVisible();
        await page.locator('.xbtn').click();
        await expect(page.locator('.modal-backdrop')).not.toBeVisible();
    });

    test('modal closes when backdrop is clicked outside the modal', async ({ page }) => {
        await page.locator('.table tbody tr.row-click').first().click();
        await expect(page.locator('.modal-backdrop')).toBeVisible();
        // Click the backdrop element itself (not the inner modal box)
        await page.locator('.modal-backdrop').click({ position: { x: 10, y: 10 } });
        await expect(page.locator('.modal-backdrop')).not.toBeVisible();
    });

    test('Finance department modal shows its improvement list items', async ({ page }) => {
        // Finance is second row in default desc sort — click its View button directly
        await page.locator('.table tbody .mini-btn').nth(1).click();
        await expect(page.locator('.modal-body')).toContainText('Data Retention Policy');
        await expect(page.locator('.modal-body')).toContainText('Consent Documentation');
    });

    test('Finance department modal recommended actions use clause summaries', async ({ page }) => {
        await page.locator('.table tbody .mini-btn').nth(1).click();
        await expect(page.locator('.modal-body')).toContainText('Establish and document a clear data retention schedule.');
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Navigation
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Comparison Dashboard Graphical — Navigation', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await loadPageWithResult(page);
    });

    test('back arrow navigates to comparison.html', async ({ page }) => {
        await page.locator('.back-arrow').click();
        await expect(page).toHaveURL(/comparison\.html/);
    });

    test('user profile icon navigates to profile.html', async ({ page }) => {
        await page.locator('.user-profile').click();
        await expect(page).toHaveURL(/profile\.html/);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Error States
// ─────────────────────────────────────────────────────────────────────────────
//
// The mounted() hook handles several failure modes before the API is even
// called (missing/malformed batchResultIds), and several after the call
// (non-ok status, network failure). Each shows a loadError banner instead
// of the dashboard content.

test.describe('Comparison Dashboard Graphical — Error States', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
    });

    test('shows error message when batchResultIds is missing from sessionStorage', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        // Remove any existing batchResultIds — no API call will be made at all
        await page.evaluate(() => sessionStorage.removeItem('batchResultIds'));
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(CDG_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(page.locator('text=No batch results found')).toBeVisible({ timeout: 5000 });
    });

    test('shows error message when batchResultIds is malformed JSON', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(() => sessionStorage.setItem('batchResultIds', 'not-valid-json{{'));
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(CDG_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(page.locator('text=corrupted')).toBeVisible({ timeout: 5000 });
    });

    test('shows loadError banner when API returns 500', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(
            ([id1, id2]) => sessionStorage.setItem('batchResultIds', JSON.stringify([id1, id2])),
            [RESULT_ID_1, RESULT_ID_2]
        );
        await page.route(reOrgComparison, async route => {
            await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' });
        });
        await page.route(reClauseSummaries, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(CDG_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(
            page.locator('text=Could not load comparison data')
        ).toBeVisible({ timeout: 5000 });
    });

    test('shows "Could not reach the server" when fetch throws a network error', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(
            ([id1, id2]) => sessionStorage.setItem('batchResultIds', JSON.stringify([id1, id2])),
            [RESULT_ID_1, RESULT_ID_2]
        );
        await page.route(reOrgComparison, async route => {
            await route.abort('connectionreset');
        });
        await page.route(reClauseSummaries, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(CDG_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(
            page.locator('text=Could not reach the server')
        ).toBeVisible({ timeout: 5000 });
    });

    test('dashboard content is NOT shown when there is a loadError', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate(
            ([id1, id2]) => sessionStorage.setItem('batchResultIds', JSON.stringify([id1, id2])),
            [RESULT_ID_1, RESULT_ID_2]
        );
        await page.route(reOrgComparison, async route => {
            await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' });
        });
        await page.route(reClauseSummaries, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(CDG_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(page.locator('.dashboard-shell')).not.toBeVisible();
    });

    test('clause_summaries.json 404 does not crash the page — dashboard still renders', async ({ page }) => {
        // This tests the graceful fallback — if clause_summaries.json is missing,
        // the frontend warns and continues. The dashboard should load normally,
        // and the modal's recommended actions fall back to "Address compliance gap: ..."
        await loadPageWithResult(page, FAKE_ORG_RESPONSE, { clauseSummaries: null });
        await expect(page).toHaveURL(/comparison_dashboard_graphical\.html/);
        await expect(page.locator('.dashboard-shell')).toBeVisible();
    });

    test('modal recommended actions fall back to clause title when clause_summaries.json is missing', async ({ page }) => {
        await loadPageWithResult(page, FAKE_ORG_RESPONSE, { clauseSummaries: null });
        await page.locator('.table tbody tr.row-click').first().click();
        await expect(page.locator('.modal-body')).toContainText('Address compliance gap:');
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Sidebar
// ─────────────────────────────────────────────────────────────────────────────
//
// sidebarOpen starts true in data() — back arrow and main content both carry
// the "shifted" class. The menu icon toggles the sidebar open and closed.

test.describe('Comparison Dashboard Graphical — Sidebar', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await loadPageWithResult(page);
    });

    test('sidebar is open by default — back arrow has shifted class', async ({ page }) => {
        await expect(page.locator('.back-arrow')).toHaveClass(/shifted/);
    });

    test('main content has shifted class when sidebar is open', async ({ page }) => {
        await expect(page.locator('div.main-content')).toHaveClass(/shifted/);
    });

    test('clicking menu icon closes sidebar — back arrow loses shifted class', async ({ page }) => {
        await page.locator('.menu-icon').click();
        await expect(page.locator('.back-arrow')).not.toHaveClass(/shifted/);
    });

    test('main content loses shifted class when sidebar is closed', async ({ page }) => {
        await page.locator('.menu-icon').click();
        await expect(page.locator('div.main-content')).not.toHaveClass(/shifted/);
    });

    test('clicking menu icon again re-opens sidebar', async ({ page }) => {
        await page.locator('.menu-icon').click();
        await page.locator('.menu-icon').click();
        await expect(page.locator('.back-arrow')).toHaveClass(/shifted/);
    });
});