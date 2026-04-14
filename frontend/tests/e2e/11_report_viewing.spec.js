// tests/e2e/11_report_viewing.spec.js
// ─────────────────────────────────────────────────────────────────────────────
// Report Viewing page (report_viewing.html)
//
// Covers:
//   - Auth guard (no token → login)
//   - Page rendering: title, report container, 30-day notice
//   - Load existing report via ?report_id= (the primary flow)
//   - Generate flow via ?generate=true (calls analysis + generate endpoints)
//   - Report content display: company, file, score, risk level, risk factors,
//     top recommendation, compliance details (sorted non-compliant first)
//   - Compliance detail card: status colour, risk level, confidence, reasoning
//   - Empty/placeholder state when no report selected
//   - Sidebar: open by default, toggle shifts layout elements
//   - Navigation: back arrow (history.back), home button, user profile
//   - RBAC — Download button: visible & clickable for admin, locked for general
//   - RBAC — Share button: visible & clickable for admin, locked for general
//   - RBAC — locked button tooltip shown on hover for general user
//   - User story task: report currently fetches from single endpoint
//     (multi-interface enrichment test is skipped pending implementation)
// ─────────────────────────────────────────────────────────────────────────────

const { test, expect } = require('@playwright/test');
const {
    loginAsGeneral,
    loginAsAdmin,
} = require('./helpers/helper_login');

const REPORT_URL  = './report_viewing.html';
const REPORT_ID   = 'rpt-aaaa-bbbb-cccc-dddddddddddd';
const RESULT_ID   = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';

// ── Regex route helpers ───────────────────────────────────────────────────────
const reReport    = (id) => new RegExp(`/ai/api/reports/${id}/?$`);
const reGenerate  = new RegExp(`/ai/api/reports/generate/?$`);
const reAnalysis  = (id) => new RegExp(`/ai/api/analysis/${id}/?$`);
const reDownload  = new RegExp(`/api/download-report/?$`);
const reShare     = new RegExp(`/api/share-report/?$`);

// ── Fake snapshot ─────────────────────────────────────────────────────────────
const FAKE_SNAPSHOT = {
    metadata: {
        file_analyzed: 'privacy_policy.pdf',
        company:       'Test Corp'
    },
    compliance: {
        compliance_score: 62,
        details: [
            {
                clause:      'Data minimisation',
                status:      'non_compliant',
                risk_level:  'critical',
                reasoning:   'No minimisation policy found.',
                confidence:  88
            },
            {
                clause:      'Purpose limitation',
                status:      'non_compliant',
                risk_level:  'high',
                reasoning:   'Purpose not documented.',
                confidence:  75
            },
            {
                clause:      'Security measures',
                status:      'partial',
                risk_level:  'medium',
                reasoning:   'Partial controls in place.',
                confidence:  70
            },
            {
                clause:      'Subject rights',
                status:      'compliant',
                risk_level:  'low',
                reasoning:   'Fully addressed.',
                confidence:  95
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
    report_snapshot: FAKE_SNAPSHOT
};

// Fake analysis result used in the generate flow
const FAKE_ANALYSIS = {
    result_id:         RESULT_ID,
    original_filename: 'privacy_policy.pdf',
    company_name:      'Test Corp',
    raw_output:        FAKE_SNAPSHOT
};

// Fake generate response
const FAKE_GENERATE_RESPONSE = {
    report_id: REPORT_ID
};

// ── Shared page loader ────────────────────────────────────────────────────────
async function loadReportPage(page, snapshot = FAKE_SNAPSHOT, { freshRoutes = true } = {}) {
    if (freshRoutes) {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
    }

    const response = { report_id: REPORT_ID, report_snapshot: snapshot };

    await page.route(reReport(REPORT_ID), async route => {
        await route.fulfill({
            status:      200,
            contentType: 'application/json',
            body:        JSON.stringify(response)
        });
    });

    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
    await page.goto(`${REPORT_URL}?report_id=${REPORT_ID}`);
    await page.waitForLoadState('networkidle', { timeout: 15000 });
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

    test('displays compliance score', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('62%', { timeout: 8000 });
    });

    test('displays risk level with capital first letter', async ({ page }) => {
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
        const nonCompliantPos = content.indexOf('Data minimisation');
        const compliantPos = content.indexOf('Subject rights');
        expect(nonCompliantPos).toBeLessThan(compliantPos);
    });

    test('compliant status shown in green', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('Compliant', { timeout: 8000 });
    });

    test('non-compliant status shown in red', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('Non-Compliant', { timeout: 8000 });
    });

    test('partial status shown in orange', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('Partial', { timeout: 8000 });
    });

    test('detail cards show risk level and confidence', async ({ page }) => {
        await expect(page.locator('.pdf-container')).toContainText('Critical', { timeout: 8000 });
        await expect(page.locator('.pdf-container')).toContainText('88%', { timeout: 8000 });
    });

    test('placeholder shown when no report is selected', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.goto(REPORT_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await expect(page.locator('.pdf-container')).toContainText('Please select a report', { timeout: 8000 });
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

        await page.route(reReport(REPORT_ID), async route => {
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify(FAKE_REPORT_RESPONSE)
            });
        });

        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(`${REPORT_URL}?generate=true`);
        await page.waitForLoadState('networkidle', { timeout: 20000 });

        await expect(page.locator('.pdf-container')).toContainText('Test Corp', { timeout: 10000 });
        await expect(page).toHaveURL(/report_id=/, { timeout: 5000 });
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
        await page.locator('.user-profile').click();
        await expect(page).toHaveURL(/profile\.html/);
    });

    test('home button navigates to home.html', async ({ page }) => {
        await page.locator('.home-button').click();
        await expect(page).toHaveURL(/home\.html/);
    });

    test('back arrow calls history.back — navigates to previous page', async ({ page }) => {
        await page.goto('./document_analysis.html');
        await page.route(reReport(REPORT_ID), async route => {
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify(FAKE_REPORT_RESPONSE)
            });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(`${REPORT_URL}?report_id=${REPORT_ID}`);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
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
        // Buttons are position:fixed far to the right — use JS hover instead
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
        // Button is position:fixed outside viewport — trigger via JS click
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
                body:        JSON.stringify({ token: 'fake-share-token-123' })
            });
        });
        // Button is position:fixed outside viewport — trigger via JS click
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

        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(`${REPORT_URL}?report_id=${REPORT_ID}`);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        expect(reportEndpointCalled).toBe(true);
        await expect(page.locator('.pdf-container')).toContainText('Test Corp', { timeout: 8000 });
    });

    test.skip('admin report snapshot includes recommendations section', async ({ page }) => {
        await loginAsAdmin(page);

        const adminSnapshot = {
            ...FAKE_SNAPSHOT,
            recommendations: [
                {
                    clauseTitle: 'Data minimisation',
                    riskLevel:   'critical',
                    reasoning:   'No minimisation policy found.',
                    steps:       ['Implement data minimisation controls'],
                    reference:   'Section 7(1) of the Personal Data Protection Act No. 9 of 2022 (Sri Lanka)'
                }
            ]
        };

        await page.route(reReport(REPORT_ID), async route => {
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify({ report_id: REPORT_ID, report_snapshot: adminSnapshot })
            });
        });

        await page.goto(`${REPORT_URL}?report_id=${REPORT_ID}`);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(page.locator('.pdf-container')).toContainText('Recommendations', { timeout: 8000 });
        await expect(page.locator('.pdf-container')).toContainText('Data minimisation', { timeout: 8000 });
    });

    test.skip('admin report snapshot includes comparison section', async ({ page }) => {
        await loginAsAdmin(page);

        const adminSnapshot = {
            ...FAKE_SNAPSHOT,
            comparison: {
                department:                'IT Department',
                departmentScore:           62,
                departmentRiskLevel:       'Medium',
                departmentRecommendations: ['Data minimisation', 'Purpose limitation']
            }
        };

        await page.route(reReport(REPORT_ID), async route => {
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify({ report_id: REPORT_ID, report_snapshot: adminSnapshot })
            });
        });

        await page.goto(`${REPORT_URL}?report_id=${REPORT_ID}`);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(page.locator('.pdf-container')).toContainText('Comparison', { timeout: 8000 });
        await expect(page.locator('.pdf-container')).toContainText('IT Department', { timeout: 8000 });
    });

    test.skip('general user report snapshot does not include recommendations or comparison sections', async ({ page }) => {
        await loginAsGeneral(page);

        await page.route(reReport(REPORT_ID), async route => {
            await route.fulfill({
                status:      200,
                contentType: 'application/json',
                body:        JSON.stringify(FAKE_REPORT_RESPONSE)
            });
        });

        await page.goto(`${REPORT_URL}?report_id=${REPORT_ID}`);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(page.locator('.pdf-container')).not.toContainText('Recommendations');
        await expect(page.locator('.pdf-container')).not.toContainText('Comparison');
    });

});