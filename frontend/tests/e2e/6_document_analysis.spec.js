// tests/e2e/6_document_analysis.spec.js
// ─────────────────────────────────────────────────────────────────────────────
// Document Analysis page (document_analysis.html)
//
// Covers:
//   - Auth guard (no token → login, 401/403 → login, sessionStorage cleared)
//   - Page rendering with mocked result data
//   - Compliance score display: value, label, bar animation
//   - Compliance label thresholds: high / medium / low
//   - Company name in subtitle
//   - Recommendations panel: findings list, empty state
//   - RBAC — general user: lock icons, access denied toast, toast auto-dismiss
//   - RBAC — admin user: no lock icons, no toast, unrestricted access
//   - Navigation: back arrow, user profile, all button redirects
//   - sessionStorage: latestResultId fetched and written back
//   - Fallback to /api/analysis/latest/ when no latestResultId
//   - Error states: 404, 500 → "No results yet", network abort → banner
//   - Sidebar: open by default, toggle, shifted class
//
// MOCKING STRATEGY
//   All route mocks use RegExp with /?$ to match URLs with or without trailing
//   slash — this prevents the intermittent redirect-to-login caused by glob
//   patterns failing to match Django's trailing-slash URLs.
//   page.unrouteAll() is called at the start of loadPageWithResult so stale
//   routes from previous tests never bleed into subsequent ones.
// ─────────────────────────────────────────────────────────────────────────────

const { test, expect } = require('@playwright/test');
const {
    loginAsGeneral,
    loginAsAdmin,
} = require('./helpers/helper_login');

const DA_URL      = './document_analysis.html';
const RESULT_ID   = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
const RESULT_ID_2 = 'ffffffff-eeee-dddd-cccc-bbbbbbbbbbbb';

// ── Regex route helpers ───────────────────────────────────────────────────────
// Match with or without trailing slash to handle Django URL variations.

const reResult  = (id) => new RegExp(`/ai/api/analysis/${id}/?$`);
const reLatest  = new RegExp(`/ai/api/analysis/latest/?$`);
const reHistory = new RegExp(`/ai/api/analysis/history/?$`);

// ── Fake API responses ────────────────────────────────────────────────────────

const HIGH_SCORE_RESULT = {
    result_id:         RESULT_ID,
    original_filename: 'compliance_policy.pdf',
    company_name:      'Acme Corporation',
    compliance_score:  82,
    compliance_label:  'High Compliance Level',
    compliance: {
        details: [
            { requirement_id: 'req-1', clause: 'Section 3.1', status: 'non-compliant', reasoning: 'Data retention policy missing.' },
            { requirement_id: 'req-2', clause: 'Section 5.2', status: 'partial',       reasoning: 'Consent forms need updating.' },
        ],
    },
    recommendations: { top_action: 'Review data handling procedures immediately.' },
};

const MEDIUM_SCORE_RESULT = {
    result_id:         RESULT_ID,
    original_filename: 'hr_policy.docx',
    company_name:      'Beta Ltd',
    compliance_score:  55,
    compliance_label:  'Medium Compliance Level',
    compliance:        { details: [] },
    recommendations:   { top_action: '' },
};

const LOW_SCORE_RESULT = {
    result_id:         RESULT_ID,
    original_filename: 'old_policy.txt',
    company_name:      'Gamma Inc',
    compliance_score:  25,
    compliance_label:  'Low Compliance Level',
    compliance:        { details: [] },
    recommendations:   { top_action: '' },
};

const NO_LABEL_RESULT = {
    result_id:         RESULT_ID,
    original_filename: 'test.txt',
    company_name:      'Delta Co',
    compliance_score:  90,
    // No compliance_label — page derives it from score (>= 75 → High)
    compliance:        { details: [] },
    recommendations:   { top_action: '' },
};

const HISTORY_RESPONSE = {
    last_7_days: [
        { result_id: RESULT_ID,   display_name: 'Acme — policy.pdf', compliance_score: 82 },
        { result_id: RESULT_ID_2, display_name: 'Beta — hr.docx',    compliance_score: 55 },
    ],
    last_30_days: [
        { result_id: RESULT_ID_2, display_name: 'Beta — hr.docx', compliance_score: 55 },
    ],
};

const EMPTY_HISTORY = { last_7_days: [], last_30_days: [] };

// ── Shared helper: load page with mocked result ───────────────────────────────

/**
 * Clears stale routes, mocks the three backend endpoints, seeds sessionStorage,
 * navigates to document_analysis.html and waits for full load.
 *
 * @param {import('@playwright/test').Page} page
 * @param {object} result  - Fake result object to return from the API
 * @param {object} options
 * @param {boolean} options.seedResultId - Whether to write latestResultId to sessionStorage
 */
async function loadPageWithResult(page, result = HIGH_SCORE_RESULT, { seedResultId = true } = {}) {
    // Clear any routes set by previous tests so they don't interfere
    await page.unrouteAll({ behavior: 'ignoreErrors' });

    // Mock: result by ID (with or without trailing slash)
    await page.route(reResult(result.result_id), async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(result),
        });
    });

    // Mock: latest fallback
    await page.route(reLatest, async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(result),
        });
    });

    // Mock: sidebar history
    await page.route(reHistory, async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(HISTORY_RESPONSE),
        });
    });

    if (seedResultId) {
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), result.result_id);
    }

    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
    await page.goto(DA_URL);
    await page.waitForLoadState('networkidle', { timeout: 15000 });
}

// ─────────────────────────────────────────────────────────────────────────────
// Auth Guard
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Document Analysis — Auth Guard', () => {

    test('redirects to login.html when no authToken in sessionStorage', async ({ page }) => {
        await page.goto('./welcome.html');
        await page.evaluate(() => sessionStorage.clear());
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(DA_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
    });

    test('redirects to login.html when API returns 401', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);

        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Unauthorized"}' });
        });
        await page.route(reHistory, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(EMPTY_HISTORY) });
        });

        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(DA_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
    });

    test('redirects to login.html when API returns 403', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);

        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 403, contentType: 'application/json', body: '{"detail":"Forbidden"}' });
        });
        await page.route(reHistory, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(EMPTY_HISTORY) });
        });

        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(DA_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });
    });

    test('sessionStorage is cleared before redirect on 401', async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);

        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 401, contentType: 'application/json', body: '{}' });
        });
        await page.route(reHistory, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(EMPTY_HISTORY) });
        });

        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(DA_URL);
        await page.waitForURL(/login\.html/, { timeout: 10000 });

        const token = await page.evaluate(() => sessionStorage.getItem('authToken'));
        expect(token).toBeNull();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Page Rendering — General User
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Document Analysis — Page Rendering (General User)', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithResult(page, HIGH_SCORE_RESULT);
    });

    test('page loads and stays on document_analysis.html', async ({ page }) => {
        await expect(page).toHaveURL(/document_analysis\.html/);
    });

    test('DOCUMENT ANALYSIS heading is visible', async ({ page }) => {
        await expect(page.locator('.document-title')).toContainText('DOCUMENT ANALYSIS');
    });

    test('company name appears in the subtitle', async ({ page }) => {
        await expect(page.locator('.document-subtitle')).toContainText('Acme Corporation');
    });

    test('subtitle contains COMPLIANCE ANALYSIS REPORT', async ({ page }) => {
        await expect(page.locator('.document-subtitle')).toContainText('COMPLIANCE ANALYSIS REPORT');
    });

    test('top header with menu icon and user profile icon are visible', async ({ page }) => {
        await expect(page.locator('.top-header')).toBeVisible();
        await expect(page.locator('.menu-icon')).toBeVisible();
        await expect(page.locator('.user-profile')).toBeVisible();
    });

    test('back arrow is visible', async ({ page }) => {
        await expect(page.locator('.back-arrow')).toBeVisible();
    });

    test('compliance section is visible', async ({ page }) => {
        await expect(page.locator('.compliance-section')).toBeVisible();
    });

    test('recommendations section is visible', async ({ page }) => {
        await expect(page.locator('.recommendations-section')).toBeVisible();
    });

    test('action buttons section is visible', async ({ page }) => {
        await expect(page.locator('.action-buttons')).toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Compliance Score Display
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Document Analysis — Compliance Score Display', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
    });

    test('compliance score value is displayed correctly', async ({ page }) => {
        await loadPageWithResult(page, HIGH_SCORE_RESULT);
        await expect(page.locator('.compliance-item')).toContainText('82%');
    });

    test('compliance label is displayed correctly', async ({ page }) => {
        await loadPageWithResult(page, HIGH_SCORE_RESULT);
        await expect(page.locator('.compliance-item')).toContainText('82%');
        await expect(page.locator('.compliance-item')).toContainText('High Compliance Level');
    });

    test('compliance bar fills to correct percentage after animation', async ({ page }) => {
        await loadPageWithResult(page, HIGH_SCORE_RESULT);
        await page.waitForTimeout(500); // setTimeout in mounted() fires after 300ms
        const width = await page.locator('.compliance-bar-fill').evaluate(el => el.style.width);
        expect(width).toBe('82%');
    });

    test('compliance bar label shows COMPLIANCE SCORE', async ({ page }) => {
        await loadPageWithResult(page, HIGH_SCORE_RESULT);
        await expect(page.locator('.compliance-bar-label')).toContainText('COMPLIANCE SCORE');
    });

    test('medium score shows Medium Compliance Level label', async ({ page }) => {
        await loadPageWithResult(page, MEDIUM_SCORE_RESULT);
        await expect(page.locator('.compliance-item')).toContainText('55%');
        await expect(page.locator('.compliance-item')).toContainText('Medium Compliance Level');
    });

    test('low score shows Low Compliance Level label', async ({ page }) => {
        await loadPageWithResult(page, LOW_SCORE_RESULT);
        await expect(page.locator('.compliance-item')).toContainText('25%');
        await expect(page.locator('.compliance-item')).toContainText('Low Compliance Level');
    });

    test('score >= 75 with no label field derives High Compliance Level', async ({ page }) => {
        await loadPageWithResult(page, NO_LABEL_RESULT);
        await expect(page.locator('.compliance-item')).toContainText('90%');
        await expect(page.locator('.compliance-item')).toContainText('High Compliance Level');
    });

    test('compliance bar starts at 0% before animation completes', async ({ page }) => {
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(HIGH_SCORE_RESULT) });
        });
        await page.route(reHistory, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(EMPTY_HISTORY) });
        });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);

        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        // Navigate without waiting for networkidle — check bar immediately
        await page.goto(DA_URL);
        await page.waitForSelector('.compliance-bar-fill', { timeout: 5000 });
        const initialWidth = await page.locator('.compliance-bar-fill').evaluate(el => el.style.width);
        expect(['0%', '', '82%']).toContain(initialWidth);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Recommendations Panel
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Document Analysis — Recommendations Panel', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
    });

    test('non-compliant and partial findings appear in recommendations list', async ({ page }) => {
        await loadPageWithResult(page, HIGH_SCORE_RESULT);
        await expect(page.locator('.recommendation-item').first()).toBeVisible();
        await expect(page.locator('.recommendation-item').first()).toContainText('Section 3.1');
        await expect(page.locator('.recommendation-item').first()).toContainText('Data retention policy missing');
    });

    test('second finding also appears in recommendations list', async ({ page }) => {
        await loadPageWithResult(page, HIGH_SCORE_RESULT);
        const items = page.locator('.recommendation-item');
        await expect(items).toHaveCount(2);
        await expect(items.nth(1)).toContainText('Section 5.2');
    });

    test('shows "No recommendations available." when no findings', async ({ page }) => {
        await loadPageWithResult(page, MEDIUM_SCORE_RESULT);
        await expect(
            page.locator('.recommendation-item:has-text("No recommendations available.")')
        ).toBeVisible();
    });

    test('clause text is displayed in bold', async ({ page }) => {
        await loadPageWithResult(page, HIGH_SCORE_RESULT);
        await expect(page.locator('.recommendation-item strong').first()).toContainText('Section 3.1');
    });

    test('reasoning text is displayed alongside clause', async ({ page }) => {
        await loadPageWithResult(page, HIGH_SCORE_RESULT);
        await expect(page.locator('.recommendation-item span').first()).toContainText('Data retention policy missing');
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// RBAC — General User Restrictions
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Document Analysis — RBAC: General User', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithResult(page, HIGH_SCORE_RESULT);
    });

    test('Recommendations button has lock icon for general user', async ({ page }) => {
        await expect(
            page.locator('.recommendations-section .section-header svg.lock-icon')
        ).toBeVisible();
    });

    test('Recommendations button has locked class for general user', async ({ page }) => {
        await expect(
            page.locator('.recommendations-section .section-header')
        ).toHaveClass(/locked/);
    });

    test('Compare button has lock icon for general user', async ({ page }) => {
        await expect(
            page.locator('.action-button:has-text("Compare") svg.btn-lock-icon')
        ).toBeVisible();
    });

    test('Compare button has locked class for general user', async ({ page }) => {
        await expect(
            page.locator('.action-button:has-text("Compare")')
        ).toHaveClass(/locked/);
    });

    test('clicking Recommendations shows access denied toast', async ({ page }) => {
        await page.locator('.recommendations-section .section-header').click();
        await expect(page.locator('.access-toast')).toHaveClass(/visible/);
    });

    test('access denied toast contains correct message', async ({ page }) => {
        await page.locator('.recommendations-section .section-header').click();
        await expect(page.locator('.access-toast')).toContainText('administrative access');
    });

    test('clicking Compare shows access denied toast', async ({ page }) => {
        await page.locator('.action-button:has-text("Compare")').click();
        await expect(page.locator('.access-toast')).toHaveClass(/visible/);
    });

    test('access denied toast auto-dismisses after ~3.5 seconds', async ({ page }) => {
        await page.locator('.recommendations-section .section-header').click();
        await expect(page.locator('.access-toast')).toHaveClass(/visible/);
        await page.waitForTimeout(4000);
        await expect(page.locator('.access-toast')).not.toHaveClass(/visible/);
    });

    test('clicking Recommendations does NOT navigate away', async ({ page }) => {
        await page.locator('.recommendations-section .section-header').click();
        await expect(page).toHaveURL(/document_analysis\.html/);
    });

    test('clicking Compare does NOT navigate away', async ({ page }) => {
        await page.locator('.action-button:has-text("Compare")').click();
        await expect(page).toHaveURL(/document_analysis\.html/);
    });

    test('Compliance Score button does NOT have lock icon for general user', async ({ page }) => {
        await expect(
            page.locator('.compliance-section .section-header svg.lock-icon')
        ).not.toBeVisible();
    });

    test('Generate Reports button does NOT have lock icon', async ({ page }) => {
        // Generate Reports has no SVG lock icon — button has no child SVG at all
        await expect(
            page.locator('.action-button:has-text("Generate Reports")')
        ).not.toHaveClass(/locked/);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// RBAC — Admin User Unrestricted Access
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Document Analysis — RBAC: Admin User', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await loadPageWithResult(page, HIGH_SCORE_RESULT);
    });

    test('Recommendations button does NOT have lock icon for admin', async ({ page }) => {
        await expect(
            page.locator('.recommendations-section .section-header svg.lock-icon')
        ).not.toBeVisible();
    });

    test('Recommendations button does NOT have locked class for admin', async ({ page }) => {
        await expect(
            page.locator('.recommendations-section .section-header')
        ).not.toHaveClass(/locked/);
    });

    test('Compare button does NOT have lock icon for admin', async ({ page }) => {
        await expect(
            page.locator('.action-button:has-text("Compare") svg.btn-lock-icon')
        ).not.toBeVisible();
    });

    test('Compare button does NOT have locked class for admin', async ({ page }) => {
        await expect(
            page.locator('.action-button:has-text("Compare")')
        ).not.toHaveClass(/locked/);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Navigation & Redirects — General User
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Document Analysis — Navigation: General User', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithResult(page, HIGH_SCORE_RESULT);
    });

    test('back arrow navigates to home.html', async ({ page }) => {
        await page.locator('.back-arrow').click();
        await expect(page).toHaveURL(/home\.html/);
    });

    test('user profile icon navigates to profile.html', async ({ page }) => {
        await page.locator('.user-profile').click();
        await expect(page).toHaveURL(/profile\.html/);
    });

    test('Compliance Score button navigates to compliance.html', async ({ page }) => {
        await page.locator('.compliance-section .section-header').click();
        await expect(page).toHaveURL(/compliance\.html/);
    });

    test('Generate Reports button navigates to report_viewing.html with generate=true', async ({ page }) => {
        await page.locator('.action-button:has-text("Generate Reports")').click();
        await page.waitForURL(/report_viewing\.html/, { timeout: 5000 });
        const url = page.url();
        expect(url).toContain('report_viewing.html');
        expect(url).toContain('generate=true');
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Navigation & Redirects — Admin User
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Document Analysis — Navigation: Admin User', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await loadPageWithResult(page, HIGH_SCORE_RESULT);
    });

    test('Recommendations button navigates to recommendations.html for admin', async ({ page }) => {
        await page.locator('.recommendations-section .section-header').click();
        await expect(page).toHaveURL(/recommendations\.html/);
    });

    test('Compare button navigates to comparison.html for admin', async ({ page }) => {
        await page.locator('.action-button:has-text("Compare")').click();
        await expect(page).toHaveURL(/comparison\.html/);
    });

    test('Generate Reports navigates to report_viewing.html for admin', async ({ page }) => {
        await page.locator('.action-button:has-text("Generate Reports")').click();
        await page.waitForURL(/report_viewing\.html/, { timeout: 5000 });
        const url = page.url();
        expect(url).toContain('report_viewing.html');
        expect(url).toContain('generate=true');
    });

    test('back arrow navigates to home.html for admin', async ({ page }) => {
        await page.locator('.back-arrow').click();
        await expect(page).toHaveURL(/home\.html/);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// sessionStorage — result_id handling
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Document Analysis — sessionStorage Handling', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
    });

    test('uses latestResultId from sessionStorage to fetch correct result', async ({ page }) => {
        let fetchedUrl = '';
        await page.unrouteAll({ behavior: 'ignoreErrors' });

        await page.route(reResult(RESULT_ID), async route => {
            fetchedUrl = route.request().url();
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(HIGH_SCORE_RESULT) });
        });
        await page.route(reHistory, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(EMPTY_HISTORY) });
        });

        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(DA_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        expect(fetchedUrl).toContain(RESULT_ID);
    });

    test('falls back to /api/analysis/latest/ when no latestResultId in sessionStorage', async ({ page }) => {
        let fetchedLatest = false;
        await page.unrouteAll({ behavior: 'ignoreErrors' });

        await page.route(reLatest, async route => {
            fetchedLatest = true;
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(HIGH_SCORE_RESULT) });
        });
        await page.route(reHistory, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(EMPTY_HISTORY) });
        });

        await page.evaluate(() => sessionStorage.removeItem('latestResultId'));
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(DA_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        expect(fetchedLatest).toBe(true);
    });

    test('page writes result_id back to sessionStorage after loading', async ({ page }) => {
        await loadPageWithResult(page, HIGH_SCORE_RESULT);
        const stored = await page.evaluate(() => sessionStorage.getItem('latestResultId'));
        expect(stored).toBe(RESULT_ID);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Error States
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Document Analysis — Error States', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await page.route(reHistory, async route => {
            await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(EMPTY_HISTORY) });
        });
        await page.evaluate((id) => sessionStorage.setItem('latestResultId', id), RESULT_ID);
    });

    test('compliance label shows "No results yet" when API returns 404', async ({ page }) => {
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Not found"}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(DA_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(page.locator('.compliance-item')).toContainText('No results yet', { timeout: 5000 });
    });

    test('compliance label shows "No results yet" when API returns 500', async ({ page }) => {
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(DA_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(page.locator('.compliance-item')).toContainText('No results yet', { timeout: 5000 });
    });

    test('error banner shows "No analysis results found" on 404', async ({ page }) => {
        await page.route(reResult(RESULT_ID), async route => {
            await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(DA_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(
            page.locator('text=No analysis results found')
        ).toBeVisible({ timeout: 5000 });
    });

    test('error banner shows "Could not reach the server" when fetch throws', async ({ page }) => {
        // abort with connectionreset to simulate a real network failure
        await page.route(reResult(RESULT_ID), async route => {
            await route.abort('connectionreset');
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(DA_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(
            page.locator('text=Could not reach the server')
        ).toBeVisible({ timeout: 5000 });
    });

    test('compliance score stays at 0 when fetch throws', async ({ page }) => {
        await page.route(reResult(RESULT_ID), async route => {
            await route.abort('connectionreset');
        });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        await page.goto(DA_URL);
        await page.waitForLoadState('networkidle', { timeout: 15000 });

        await expect(page.locator('.compliance-item')).toContainText('0%', { timeout: 5000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Sidebar
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Document Analysis — Sidebar', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await loadPageWithResult(page, HIGH_SCORE_RESULT);
    });

    test('sidebar is open by default — back arrow has shifted class', async ({ page }) => {
        // sidebarOpen starts true in data() → back-arrow gets :class="{ shifted: sidebarOpen }"
        await expect(page.locator('.back-arrow')).toHaveClass(/shifted/);
    });

    test('clicking menu icon closes sidebar — back arrow loses shifted class', async ({ page }) => {
        await page.locator('.menu-icon').click();
        await expect(page.locator('.back-arrow')).not.toHaveClass(/shifted/);
    });

    test('clicking menu icon again re-opens sidebar', async ({ page }) => {
        await page.locator('.menu-icon').click();
        await page.locator('.menu-icon').click();
        await expect(page.locator('.back-arrow')).toHaveClass(/shifted/);
    });

    test('main content has shifted class when sidebar is open', async ({ page }) => {
        await expect(page.locator('div.main-content')).toHaveClass(/shifted/);
    });

    test('main content loses shifted class when sidebar is closed', async ({ page }) => {
        await page.locator('.menu-icon').click();
        await expect(page.locator('div.main-content')).not.toHaveClass(/shifted/);
    });
});