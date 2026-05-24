// tests/e2e/11_report_viewing.spec.js
// ─────────────────────────────────────────────────────────────────────────────
// Report Viewing page (report_viewing.html)
//
// Covers:
//   - Auth guard (no token → login)
//   - Page rendering: title, report container, 30-day notice
//   - Load existing report via ?report_id= (direct load flow)
//   - Load existing report via ?token= (shared report / generated flow)
//   - Generate flow via ?generate=true (calls analysis + generate endpoints)
//   - Report content display: company, file, department, score, risk level,
//     risk factors, top recommendation, compliance details
//   - Gap identification and risk assessment sections rendered
//   - Partial badge shown for partial items
//   - Risk badges rendered for compliance items
//   - Empty/placeholder state when no report selected
//   - Inline error message shown on failed load
//   - Sidebar: open by default, toggle shifts layout elements
//   - Navigation: back arrow (history.back), home button, user profile
//   - RBAC — Download button: visible & clickable for admin, locked for general
//   - RBAC — Share button: visible & clickable for admin, locked for general
//   - RBAC — Comparison section: visible for admin, hidden for general
//   - RBAC — Recommendations section: visible for admin, hidden for general
//   - RBAC — locked button tooltip shown on hover for general user
//   - User story task: report loads from reports endpoint; admin sees
//     comparison + recommendations sections; general user does not
// ─────────────────────────────────────────────────────────────────────────────

const { test, expect } = require('@playwright/test');
const {
    loginAsGeneral,
    loginAsAdmin,
} = require('./helpers/helper_login');

const REPORT_URL = './report_viewing.html';
const REPORT_ID  = 'aabbccdd-1234-4abc-89ab-aabbccddeeff';
const RESULT_ID  = 'aabbccdd-1234-4def-89ab-aabbccddeeff';
const FAKE_TOKEN = 'fake-view-token-abc123';

// ── Regex route helpers ───────────────────────────────────────────────────────
const reReport       = (id) => new RegExp(`/ai/api/reports/${id}/?$`);
const reResolveToken = new RegExp(`/ai/api/reports/resolve-token/`);
const reGenerate     = new RegExp(`/ai/api/reports/generate/?$`);
const reAnalysis     = (id) => new RegExp(`/ai/api/analysis/${id}/?$`);
const reDownload     = new RegExp(`/ai/api/download-report/?$`);
const reShare        = new RegExp(`/ai/api/share-report/?$`);

// ── Fake data ─────────────────────────────────────────────────────────────────
const FAKE_SNAPSHOT = {
    metadata: {
        file_analyzed: 'privacy_policy.pdf',
        company:       'Test Corp',
        department:    'IT Department'
    },
    compliance: {
        compliance_score: 62,
        details: [
            {
                requirement_id: 'SL-PDPA-S7-1',
                clause:         'Data minimisation',
                status:         'non_compliant',
                risk_level:     'critical',
                reasoning:      'No minimisation policy found.',
                confidence:     88
            },
            {
                requirement_id: 'SL-PDPA-S6-1',
                clause:         'Purpose limitation',
                status:         'non_compliant',
                risk_level:     'high',
                reasoning:      'Purpose not documented.',
                confidence:     75
            },
            {
                requirement_id: 'SL-PDPA-S10-1',
                clause:         'Security measures',
                status:         'partial',
                risk_level:     'medium',
                reasoning:      'Partial controls in place.',
                confidence:     70
            },
            {
                requirement_id: 'SL-PDPA-S12-1',
                clause:         'Subject rights',
                status:         'compliant',
                risk_level:     'low',
                reasoning:      'Fully addressed.',
                confidence:     95
            }
        ]
    },
    risks: {
        status:  'medium',
        factors: ['Inadequate data handling', 'Missing consent records']
    }
};

const FAKE_REPORT_RESPONSE = {
    report_id:       REPORT_ID,
    result_id:       RESULT_ID,
    report_snapshot: FAKE_SNAPSHOT
};

const FAKE_ANALYSIS = {
    result_id:         RESULT_ID,
    original_filename: 'privacy_policy.pdf',
    company_name:      'Test Corp',
    department:        'IT Department',
    raw_output:        FAKE_SNAPSHOT
};

const FAKE_GENERATE_RESPONSE = {
    report_id:  REPORT_ID,
    view_token: FAKE_TOKEN
};

const FAKE_TOKEN_RESPONSE = {
    report_id:       REPORT_ID,
    result_id:       RESULT_ID,
    report_snapshot: FAKE_SNAPSHOT
};

// ── Shared page loaders ───────────────────────────────────────────────────────

// Primary loader — uses ?token= (main flow in updated HTML)
async function loadReportPage(page, snapshot = FAKE_SNAPSHOT, { freshRoutes = true } = {}) {
    if (freshRoutes) {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
    }

    const response = { ...FAKE_TOKEN_RESPONSE, report_snapshot: snapshot };

    await page.route(reResolveToken, async route => {
        await route.fulfill({
            status:      200,
            contentType: 'application/json',
            body:        JSON.stringify(response)
        });
    });

    await page.route(reAnalysis(RESULT_ID), async route => {
        await route.fulfill({
            status:      200,
            contentType: 'application/json',
            body:        JSON.stringify(FAKE_ANALYSIS)
        });
    });

    await page.goto(`${REPORT_URL}?token=${FAKE_TOKEN}`);
    await page.waitForLoadState('networkidle', { timeout: 15000 });
    // Wait for Vue to render content — .report-section only appears once
    // currentSnapshot is set and Vue has committed the DOM update
    await page.waitForSelector('.report-section', { state: 'attached', timeout: 10000 });
}

// Secondary loader — uses ?report_id= (for tests that specifically test that flow)
async function loadReportPageById(page, snapshot = FAKE_SNAPSHOT, { freshRoutes = true } = {}) {
    if (freshRoutes) {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
    }

    const response = { ...FAKE_REPORT_RESPONSE, report_snapshot: snapshot };

    await page.route(reReport(REPORT_ID), async route => {
        await route.fulfill({
            status:      200,
            contentType: 'application/json',
            body:        JSON.stringify(response)
        });
    });

    await page.route(reAnalysis(RESULT_ID), async route => {
        await route.fulfill({
            status:      200,
            contentType: 'application/json',
            body:        JSON.stringify(FAKE_ANALYSIS)
        });
    });

    await page.goto(`${REPORT_URL}?report_id=${REPORT_ID}`);
    await page.waitForLoadState('networkidle', { timeout: 15000 });
    await page.waitForSelector('.report-section', { state: 'attached', timeout: 10000 });
}

// ─────────────────────────────────────────────────────────────────────────────
// Auth Guard
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Report Viewing — Auth Guard', () => {

    test('redirects to login.html when no authToken in sessionStorage', async ({ page }) => {
        await page.goto('./welcome.html');
        await page.evaluate(() => sessionStorage.clear());
        await page.goto(`${REPORT_URL}?report_id=${REPORT_ID}`);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
    });

});

// ─────────────────────────────────────────────────────────────────────────────
// Page Rendering
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Report Viewing — Page Rendering', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadReportPage(page, FAKE_SNAPSHOT, { freshRoutes: false });
    });

    test('top header is visible', async ({ page }) => {
        await expect(page.locator('.top-header')).toBeVisible({ timeout: 8000 });
    });

    test('pdf container is visible', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toBeVisible({ timeout: 8000 });
    });

    test('30-day notice is visible', async ({ page }) => {
        await expect(page.locator('.report-notice')).toBeVisible({ timeout: 8000 });
        await expect(page.locator('.report-notice')).toContainText('30 days');
    });

    test('report title shows company and filename', async ({ page }) => {
        await expect(page.locator('h2.report-title')).toBeVisible({ timeout: 8000 });
        await expect(page.locator('h2.report-title')).toContainText('Test Corp');
        await expect(page.locator('h2.report-title')).toContainText('privacy_policy.pdf');
    });

    test('report title includes department when present', async ({ page }) => {
        await expect(page.locator('h2.report-title')).toContainText('IT Department', { timeout: 8000 });
    });

    test('sidebar is open by default', async ({ page }) => {
        await expect(page.locator('.back-arrow')).toHaveClass(/shifted/, { timeout: 8000 });
    });

});

// ─────────────────────────────────────────────────────────────────────────────
// Report Content Display
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Report Viewing — Report Content', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadReportPage(page, FAKE_SNAPSHOT, { freshRoutes: false });
    });

    test('displays company name from snapshot metadata', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('Test Corp', { timeout: 8000 });
    });

    test('displays filename from snapshot metadata', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('privacy_policy.pdf', { timeout: 8000 });
    });

    test('displays department from snapshot metadata', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('IT Department', { timeout: 8000 });
    });

    test('displays compliance score', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('62%', { timeout: 8000 });
    });

    test('displays overall risk level derived from score', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('Medium', { timeout: 8000 });
    });

    test('displays risk factors', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('Inadequate data handling', { timeout: 8000 });
        await expect(page.locator('.pdf-container')).toContainText('Missing consent records', { timeout: 8000 });
    });

    test('top recommendation is the highest-risk non-compliant clause', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('Data minimisation', { timeout: 8000 });
    });

    test('compliance details are rendered', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('Data minimisation', { timeout: 8000 });
        await expect(page.locator('.pdf-container')).toContainText('Purpose limitation', { timeout: 8000 });
    });

    test('non-compliant details appear before compliant ones', async ({ page }) => {
        const content = await page.locator('.pdf-container').innerText({ timeout: 8000 });
        const criticalPos = content.indexOf('Data minimisation');
        const partialPos  = content.indexOf('Security measures');
        expect(criticalPos).toBeGreaterThan(-1);
        expect(partialPos).toBeGreaterThan(-1);
        expect(criticalPos).toBeLessThan(partialPos);
    });

    test('gap identification section is rendered', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('Gap Identification', { timeout: 8000 });
    });

    test('risk assessment section is rendered', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('Risk Assessment', { timeout: 8000 });
    });

    test('partial badge shown for partial items', async ({ page }) => {
        await expect(page.locator('.badge-partial').first()).toBeVisible({ timeout: 8000 });
    });

    test('risk badges are rendered for compliance items', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('critical', { timeout: 8000 });
        await expect(page.locator('.pdf-container')).toContainText('medium', { timeout: 8000 });
    });

    test('placeholder shown when no report is selected', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.goto(REPORT_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.pdf-container')).toContainText('Please select a report', { timeout: 8000 });
    });

    test('inline error message shown when report fails to load', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.route(reReport(REPORT_ID), async route => {
            await route.fulfill({
                status:      404,
                contentType: 'application/json',
                body:        '{"detail":"Not found"}'
            });
        });
        await page.goto(`${REPORT_URL}?report_id=${REPORT_ID}`);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.status-message.error')).toBeVisible({ timeout: 8000 });
    });

});

// ─────────────────────────────────────────────────────────────────────────────
// Token Flow (?token=)
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Report Viewing — Token Flow', () => {

    test('loads and displays report when ?token= is in URL', async ({ page }) => {
        await loginAsGeneral(page);
        await loadReportPage(page, FAKE_SNAPSHOT, { freshRoutes: false });
        await expect(page.locator('.pdf-container')).toContainText('Test Corp', { timeout: 8000 });
        await expect(page.locator('.pdf-container')).toContainText('privacy_policy.pdf', { timeout: 8000 });
    });

    test('shows error message when token is invalid', async ({ page }) => {
        await loginAsGeneral(page);
        await page.route(reResolveToken, async route => {
            await route.fulfill({
                status:      400,
                contentType: 'application/json',
                body:        '{"detail":"Invalid token"}'
            });
        });
        await page.goto(`${REPORT_URL}?token=invalid-token`);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.status-message.error')).toBeVisible({ timeout: 8000 });
    });

});

// ─────────────────────────────────────────────────────────────────────────────
// Generate Flow (?generate=true)
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Report Viewing — Generate Flow', () => {

    test('generates a new report and displays it when ?generate=true', async ({ page }) => {
        await loginAsGeneral(page);

        await page.route(reAnalysis(RESULT_ID), async route => {
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify(FAKE_ANALYSIS)
            });
        });

        await page.route(reGenerate, async route => {
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify(FAKE_GENERATE_RESPONSE)
            });
        });

        await page.route(reResolveToken, async route => {
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify(FAKE_TOKEN_RESPONSE)
            });
        });

        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.goto(`${REPORT_URL}?generate=true`);
        await page.waitForLoadState('networkidle', { timeout: 20000 });
        await page.waitForSelector('.report-section', { timeout: 10000 });

        await expect(page.locator('.pdf-container')).toContainText('Test Corp', { timeout: 10000 });
        await expect(page).toHaveURL(/token=/, { timeout: 5000 });
    });

});

// ─────────────────────────────────────────────────────────────────────────────
// Sidebar
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Report Viewing — Sidebar', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadReportPage(page, FAKE_SNAPSHOT, { freshRoutes: false });
    });

    test('sidebar open by default — back arrow has shifted class', async ({ page }) => {
        await expect(page.locator('.back-arrow')).toHaveClass(/shifted/, { timeout: 8000 });
    });

    test('sidebar open by default — home button has shifted class', async ({ page }) => {
        await expect(page.locator('.home-button')).toHaveClass(/shifted/, { timeout: 8000 });
    });

    test('clicking menu icon closes sidebar — back arrow loses shifted class', async ({ page }) => {
        await page.locator('.menu-icon').click({ force: true });
        await expect(page.locator('.back-arrow')).not.toHaveClass(/shifted/);
    });

    test('clicking menu icon closes sidebar — home button loses shifted class', async ({ page }) => {
        await page.locator('.menu-icon').click({ force: true });
        await expect(page.locator('.home-button')).not.toHaveClass(/shifted/);
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

test.describe('Report Viewing — Navigation', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadReportPage(page, FAKE_SNAPSHOT, { freshRoutes: false });
    });

    test('user profile icon navigates to profile.html', async ({ page }) => {
        await page.locator('.user-profile').click({ force: true });
        await expect(page).toHaveURL(/profile\.html/);
    });

    test('home button navigates to home.html', async ({ page }) => {
        await page.locator('.home-button').click();
        await expect(page).toHaveURL(/home\.html/);
    });

    test('back arrow calls history.back — navigates to previous page', async ({ page }) => {
        await page.goto('./document_analysis.html');
        await page.route(reResolveToken, async route => {
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify(FAKE_TOKEN_RESPONSE)
            });
        });
        await page.route(reAnalysis(RESULT_ID), async route => {
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify(FAKE_ANALYSIS)
            });
        });
        await page.goto(`${REPORT_URL}?token=${FAKE_TOKEN}`);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await page.waitForSelector('.report-section', { timeout: 10000 });
        await page.locator('.back-arrow').click();
        await expect(page).toHaveURL(/document_analysis\.html/);
    });

});

// ─────────────────────────────────────────────────────────────────────────────
// RBAC — Download & Share (Admin only)
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Report Viewing — RBAC (General User)', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadReportPage(page, FAKE_SNAPSHOT, { freshRoutes: false });
    });

    test('download button is visible but locked for general user', async ({ page }) => {
        const downloadBtn = page.locator('.download-btn');
        await expect(downloadBtn).toBeVisible({ timeout: 8000 });
        await expect(downloadBtn).toHaveClass(/locked/);
    });

    test('share button is visible but locked for general user', async ({ page }) => {
        const shareBtn = page.locator('.share-btn');
        await expect(shareBtn).toBeVisible({ timeout: 8000 });
        await expect(shareBtn).toHaveClass(/locked/);
    });

    test('download lock tooltip is shown on hover for general user', async ({ page }) => {
        const wrapper = page.locator('.action-btn-wrapper').filter({ has: page.locator('.download-btn') });
        await page.evaluate(() => {
            const el = document.querySelector('.action-btn-wrapper:has(.download-btn)');
            if (el) el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
        });
        await expect(wrapper.locator('.lock-tooltip')).toBeVisible({ timeout: 5000 });
        await expect(wrapper.locator('.lock-tooltip')).toContainText('administrative users');
    });

    test('share lock tooltip is shown on hover for general user', async ({ page }) => {
        const wrapper = page.locator('.action-btn-wrapper').filter({ has: page.locator('.share-btn') });
        await page.evaluate(() => {
            const el = document.querySelector('.action-btn-wrapper:has(.share-btn)');
            if (el) el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
        });
        await expect(wrapper.locator('.lock-tooltip')).toBeVisible({ timeout: 5000 });
        await expect(wrapper.locator('.lock-tooltip')).toContainText('administrative users');
    });

    test('comparison section is not visible for general user', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('Document Analysis', { timeout: 8000 });
        await expect(page.locator('.pdf-container')).not.toContainText('Department View');
    });

    test('recommendations section is not visible for general user', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('Document Analysis', { timeout: 8000 });
        await expect(page.locator('.pdf-container')).not.toContainText('Action Plan');
    });

});

test.describe('Report Viewing — RBAC (Admin User)', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await loadReportPage(page, FAKE_SNAPSHOT, { freshRoutes: false });
    });

    test('download button is visible and not locked for admin', async ({ page }) => {
        const downloadBtn = page.locator('.download-btn');
        await expect(downloadBtn).toBeVisible({ timeout: 8000 });
        await expect(downloadBtn).not.toHaveClass(/locked/);
    });

    test('share button is visible and not locked for admin', async ({ page }) => {
        const shareBtn = page.locator('.share-btn');
        await expect(shareBtn).toBeVisible({ timeout: 8000 });
        await expect(shareBtn).not.toHaveClass(/locked/);
    });

    test('comparison section is visible for admin', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('Department View', { timeout: 8000 });
        await expect(page.locator('.pdf-container')).toContainText('Comparison', { timeout: 8000 });
    });

    test('recommendations section is visible for admin', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('Action Plan', { timeout: 8000 });
        await expect(page.locator('.pdf-container')).toContainText('Recommendations', { timeout: 8000 });
    });

    test('download button triggers download-report API call', async ({ page }) => {
        let downloadCalled = false;
        await page.route(reDownload, async route => {
            downloadCalled = true;
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify({ success: true })
            });
        });
        await page.evaluate(() => {
            document.querySelector('.download-btn').click();
        });
        await page.waitForTimeout(2000);
        expect(downloadCalled).toBe(true);
    });

    test('share button triggers share-report API call', async ({ page }) => {
        let shareCalled = false;
        await page.route(reShare, async route => {
            shareCalled = true;
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify({ share_url: 'https://example.com/share/abc' })
            });
        });
        await page.evaluate(() => {
            document.querySelector('.share-btn').click();
        });
        await page.waitForTimeout(2000);
        expect(shareCalled).toBe(true);
    });

});

// ─────────────────────────────────────────────────────────────────────────────
// User Story Task — Multi-interface report enrichment
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Report Viewing — Multi-interface Enrichment (User Story Task 1)', () => {

    test('report data is loaded from the reports endpoint', async ({ page }) => {
        await loginAsGeneral(page);

        let reportEndpointCalled = false;
        await page.route(reReport(REPORT_ID), async route => {
            reportEndpointCalled = true;
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify(FAKE_REPORT_RESPONSE)
            });
        });
        await page.route(reAnalysis(RESULT_ID), async route => {
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify(FAKE_ANALYSIS)
            });
        });

        await page.goto(`${REPORT_URL}?report_id=${REPORT_ID}`);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await page.waitForSelector('.report-section', { timeout: 10000 });

        expect(reportEndpointCalled).toBe(true);
        await expect(page.locator('.pdf-container')).toContainText('Test Corp', { timeout: 8000 });
    });

    test('admin report shows recommendations section derived from compliance details', async ({ page }) => {
        await loginAsAdmin(page);
        await loadReportPage(page, FAKE_SNAPSHOT, { freshRoutes: false });

        await expect(page.locator('.pdf-container')).toContainText('Action Plan', { timeout: 8000 });
        await expect(page.locator('.pdf-container')).toContainText('Recommendations', { timeout: 8000 });
        await expect(page.locator('.pdf-container')).toContainText('Data minimisation', { timeout: 8000 });
    });

    test('admin report shows comparison section derived from compliance details', async ({ page }) => {
        await loginAsAdmin(page);
        await loadReportPage(page, FAKE_SNAPSHOT, { freshRoutes: false });

        await expect(page.locator('.pdf-container')).toContainText('Department View', { timeout: 8000 });
        await expect(page.locator('.pdf-container')).toContainText('Comparison', { timeout: 8000 });
        await expect(page.locator('.pdf-container')).toContainText('IT Department', { timeout: 8000 });
    });

    test('general user report does not show recommendations or comparison sections', async ({ page }) => {
        await loginAsGeneral(page);
        await loadReportPage(page, FAKE_SNAPSHOT, { freshRoutes: false });

        await expect(page.locator('.pdf-container')).toContainText('Document Analysis', { timeout: 8000 });
        await expect(page.locator('.pdf-container')).not.toContainText('Action Plan');
        await expect(page.locator('.pdf-container')).not.toContainText('Department View');
    });

});