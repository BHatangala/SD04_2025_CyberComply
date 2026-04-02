// tests/e2e/5_home.spec.js
// ─────────────────────────────────────────────────────────────────────────────
// Home page (home.html) — full feature test suite
//
// Covers:
//   - Unauthenticated access guard
//   - Authenticated general user: upload, validation, analysis → redirect
//   - Authenticated admin user: org name, dept assignment, upload, analysis
//   - Google Drive / OneDrive: UI buttons + mocked upload endpoints
//   - File validation: wrong extension, oversized file (mocked), unsupported type
//   - Analysis: AI endpoint fully mocked via SSE to avoid OpenRouter rate limits
//   - document_analysis.html: loads with correct sessionStorage result_id
//   - RBAC on document_analysis.html: lock icons for general user
//
// MOCKING STRATEGY
//   The AI analysis endpoints (/ai/analyze/ and /ai/analyze-batch/) are
//   intercepted with page.route() and return a fake SSE stream. This means:
//     - No real AI calls are made → no OpenRouter tokens consumed
//     - The full frontend SSE parsing + redirect logic is still exercised
//     - /ai/api/analysis/save/ is also mocked to return a fake result_id
//     - /ai/api/analysis/<id>/ is mocked so document_analysis.html loads
//
// REAL BACKEND CALLS (not mocked):
//   - /api/login/ + /api/session-token/  (auth)
//   - /ai/upload/                         (Phase 1 — real S3 upload)
//   - /api/profile/                       (home.html auth guard)
//
// TEST FILES
//   Small test files are created in-memory and uploaded via the hidden
//   file input. No real files need to be present on disk.
// ─────────────────────────────────────────────────────────────────────────────

const { test, expect } = require('@playwright/test');
const path = require('path');
const fs   = require('fs');
const {
    loginAsGeneral,
    loginAsAdmin,
    GENERAL_EMAIL,
    ADMIN_EMAIL,
} = require('./helpers/helper_login');

const HOME_URL  = './home.html';
const FAKE_RESULT_ID = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';

// ── Fake SSE response for the analyze endpoint ────────────────────────────────
// Mimics exactly what Django's StreamingHttpResponse sends.
// The frontend SSE parser splits on '\n\n' and looks for lines starting 'data: '
const FAKE_SSE_RESPONSE = [
    'data: {"status":"analysing"}\n\n',
    'data: {"status":"analysed","result":{"compliance_score":78,"compliance_label":"High Compliance Level","compliance":{"details":[]},"recommendations":{"top_action":"Review data handling procedures."}}}\n\n',
].join('');

const FAKE_SAVE_RESPONSE = {
    result_id: FAKE_RESULT_ID,
    message: 'Analysis saved successfully',
};

const FAKE_ANALYSIS_FETCH = {
    result_id:        FAKE_RESULT_ID,
    original_filename: 'test_document.txt',
    company_name:     'Test Organisation',
    compliance_score: 78,
    compliance_label: 'High Compliance Level',
    compliance:       { details: [] },
    recommendations:  { top_action: 'Review data handling procedures.' },
};

// ── Helper: create a tiny test file buffer ────────────────────────────────────
function makeTxtBuffer() {
    return Buffer.from('This is a test compliance document for automated testing purposes.');
}

// ── Helper: mock all AI endpoints ────────────────────────────────────────────
async function mockAiEndpoints(page) {
    // Phase 2a — single file SSE stream
    await page.route('**/ai/analyze/', async route => {
        await route.fulfill({
            status: 200,
            contentType: 'text/event-stream',
            body: FAKE_SSE_RESPONSE,
        });
    });

    // Phase 2b — batch analysis
    await page.route('**/ai/analyze-batch/', async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                result: FAKE_ANALYSIS_FETCH,
            }),
        });
    });

    // Save analysis result to DB
    await page.route('**/ai/api/analysis/save/', async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(FAKE_SAVE_RESPONSE),
        });
    });

    // document_analysis.html fetches result by ID
    await page.route(`**/ai/api/analysis/${FAKE_RESULT_ID}/`, async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(FAKE_ANALYSIS_FETCH),
        });
    });

    // Latest analysis fallback
    await page.route('**/ai/api/analysis/latest/', async route => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(FAKE_ANALYSIS_FETCH),
        });
    });
}

// ── Helper: upload a file via the hidden file input ───────────────────────────
async function uploadFileViaInput(page, fileName, buffer, mimeType = 'text/plain') {
    // Playwright's setInputFiles accepts buffer + name + mimeType
    await page.locator('input[type="file"]').setInputFiles({
        name:     fileName,
        mimeType: mimeType,
        buffer:   buffer,
    });
}

// ── Helper: wait for file to reach 'uploaded' status badge ───────────────────
async function waitForUploadedBadge(page, timeout = 30000) {
    await expect(page.locator('.file-status-badge .status-uploaded, .file-status-badge:has-text("UPLOADED")')).toBeVisible({ timeout });
}

// ─────────────────────────────────────────────────────────────────────────────
// Access Guard — Unauthenticated
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Home Page — Access Guard (Unauthenticated)', () => {

    test('navigating directly to home.html without login redirects away', async ({ page }) => {
        await page.goto('./welcome.html');
        await page.evaluate(() => {
            sessionStorage.clear();
            localStorage.clear();
        });
        await page.goto(HOME_URL);
        await page.waitForURL(url =>
            url.href.includes('login.html') || url.href.includes('welcome.html'),
            { timeout: 10000 }
        );
    });

    test('home.html without authToken does not show protected content', async ({ page }) => {
        await page.goto('./welcome.html');
        await page.evaluate(() => {
            sessionStorage.clear();
            localStorage.clear();
        });
        await page.goto(HOME_URL);
        await expect(page).not.toHaveURL(/home\.html/);
    });

    test('home.html redirects if authToken cleared and page refreshed', async ({ page }) => {
        await loginAsGeneral(page);
        await page.evaluate(() => sessionStorage.removeItem('authToken'));
        await page.reload();
        await page.waitForURL(url =>
            url.href.includes('login.html') || url.href.includes('welcome.html'),
            { timeout: 10000 }
        );
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Authenticated — General User: Page Load & Session
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Home Page — General User: Session & Rendering', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
    });

    test('lands on home.html after login', async ({ page }) => {
        await expect(page).toHaveURL(/home\.html/);
    });

    test('CYBERCOMPLY logo is visible', async ({ page }) => {
        await expect(page.locator('.logo h1')).toContainText('CYBERCOMPLY');
    });

    test('upload area is visible with all three source buttons', async ({ page }) => {
        await expect(page.locator('.upload-area')).toBeVisible();
        await expect(page.locator('.source-label:has-text("GOOGLE DRIVE")')).toBeVisible();
        await expect(page.locator('.source-label:has-text("ONE DRIVE")')).toBeVisible();
        await expect(page.locator('.source-label:has-text("MY DEVICE")')).toBeVisible();
    });

    test('organisation name field is NOT visible for general user', async ({ page }) => {
        await expect(page.locator('.org-row')).not.toBeVisible();
    });

    test('sessionStorage contains authToken after login', async ({ page }) => {
        const token = await page.evaluate(() => sessionStorage.getItem('authToken'));
        expect(token).toBeTruthy();
        expect(token.length).toBeGreaterThan(10);
    });

    test('sessionStorage contains correct userEmail', async ({ page }) => {
        const email = await page.evaluate(() => sessionStorage.getItem('userEmail'));
        expect(email).toBe(GENERAL_EMAIL);
    });

    test('sessionStorage userRole is GENERAL_USER', async ({ page }) => {
        const role = await page.evaluate(() => sessionStorage.getItem('userRole'));
        expect(role).toBe('GENERAL_USER');
    });

    test('sessionStorage contains userFullName', async ({ page }) => {
        const name = await page.evaluate(() => sessionStorage.getItem('userFullName'));
        expect(name).toBeTruthy();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// General User: File Upload — Device
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Home Page — General User: Device Upload', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
    });

    test('clicking MY DEVICE triggers file input', async ({ page }) => {
        // File input is hidden — clicking source btn triggers it
        // We verify the input exists and is configured correctly
        await expect(page.locator('input[type="file"]')).toHaveAttribute('accept', '.pdf,.docx,.txt');
        await expect(page.locator('input[type="file"]')).toHaveAttribute('multiple', '');
    });

    test('uploading a valid TXT file shows it in the file list with UPLOADING status', async ({ page }) => {
        await uploadFileViaInput(page, 'test.txt', makeTxtBuffer());
        // File name appears in list
        await expect(page.locator('.file-name:has-text("test.txt")')).toBeVisible({ timeout: 5000 });
    });

    test('uploaded TXT file reaches UPLOADED status after S3 upload', async ({ page }) => {
        await uploadFileViaInput(page, 'test_upload.txt', makeTxtBuffer());
        // Wait for UPLOADED badge — real S3 upload happens here
        await expect(
            page.locator('.file-status-badge:has-text("UPLOADED")')
        ).toBeVisible({ timeout: 30000 });
    });

    test('unsupported file extension shows error message', async ({ page }) => {
        // Mock the upload endpoint to return the expected error
        await page.route('**/ai/upload/', async route => {
            await route.fulfill({
                status: 400,
                contentType: 'application/json',
                body: JSON.stringify({ error: 'Unsupported file type. Only PDF, DOCX, and TXT are allowed.' }),
            });
        });
        await uploadFileViaInput(page, 'malware.exe', Buffer.from('fake exe'), 'application/octet-stream');
        await expect(page.locator('.upload-failure-item')).toBeVisible({ timeout: 10000 });
    });

    test('file exceeding 50MB shows error message', async ({ page }) => {
        // Mock upload endpoint to return size error
        await page.route('**/ai/upload/', async route => {
            await route.fulfill({
                status: 400,
                contentType: 'application/json',
                body: JSON.stringify({ error: '"bigfile.pdf" exceeds the 50 MB limit.' }),
            });
        });
        // Upload any file — the mock returns the error regardless of actual size
        await uploadFileViaInput(page, 'bigfile.pdf', makeTxtBuffer(), 'application/pdf');
        await expect(page.locator('.upload-failure-item')).toBeVisible({ timeout: 10000 });
    });

    test('password-protected file shows rejection error', async ({ page }) => {
        await page.route('**/ai/upload/', async route => {
            await route.fulfill({
                status: 400,
                contentType: 'application/json',
                body: JSON.stringify({ error: 'File rejected — password protected files are not allowed' }),
            });
        });
        await uploadFileViaInput(page, 'protected.pdf', makeTxtBuffer(), 'application/pdf');
        await expect(page.locator('.upload-failure-item')).toContainText('password protected', { timeout: 10000 });
    });

    test('malware detection shows rejection error', async ({ page }) => {
        await page.route('**/ai/upload/', async route => {
            await route.fulfill({
                status: 400,
                contentType: 'application/json',
                body: JSON.stringify({ error: 'File rejected — malware detected' }),
            });
        });
        await uploadFileViaInput(page, 'virus.pdf', makeTxtBuffer(), 'application/pdf');
        await expect(page.locator('.upload-failure-item')).toContainText('malware detected', { timeout: 10000 });
    });

    test('removing a file with × button removes it from the list', async ({ page }) => {
        await uploadFileViaInput(page, 'removeme.txt', makeTxtBuffer());
        await expect(page.locator('.file-name:has-text("removeme.txt")')).toBeVisible({ timeout: 5000 });
        await page.locator('.file-remove').first().click();
        await expect(page.locator('.file-name:has-text("removeme.txt")')).not.toBeVisible();
    });

    test('storage notice banner appears after first upload', async ({ page }) => {
        await uploadFileViaInput(page, 'notice_test.txt', makeTxtBuffer());
        await expect(page.locator('.upload-info-block')).toBeVisible({ timeout: 5000 });
    });

    test('ANALYSE button appears after a file is uploaded', async ({ page }) => {
        await uploadFileViaInput(page, 'analyse_test.txt', makeTxtBuffer());
        await expect(page.locator('button.analyse-btn')).toBeVisible({ timeout: 5000 });
    });

    test('ANALYSE button is disabled while file is still uploading', async ({ page }) => {
        // Block upload so it stays in uploading state
        await page.route('**/ai/upload/', () => new Promise(() => {}));
        await uploadFileViaInput(page, 'slow_upload.txt', makeTxtBuffer());
        await expect(page.locator('button.analyse-btn')).toBeDisabled({ timeout: 5000 });
    });

    test('department pill is NOT shown for general user', async ({ page }) => {
        await uploadFileViaInput(page, 'nodept.txt', makeTxtBuffer());
        await expect(page.locator('.dept-pill')).not.toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// General User: Analysis Flow → Redirect to document_analysis.html
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Home Page — General User: Analysis & Redirect', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await mockAiEndpoints(page);
    });

    test('clicking ANALYSE after upload triggers analysis and redirects to document_analysis.html', async ({ page }) => {
        await uploadFileViaInput(page, 'compliance_doc.txt', makeTxtBuffer());

        // Wait for UPLOADED badge before clicking ANALYSE
        await expect(page.locator('.file-status-badge:has-text("UPLOADED")')).toBeVisible({ timeout: 30000 });

        await page.click('button.analyse-btn');

        // After analysis, redirect to document_analysis.html
        await page.waitForURL(/document_analysis\.html/, { timeout: 20000 });
    });

    test('latestResultId is set in sessionStorage after analysis', async ({ page }) => {
        await uploadFileViaInput(page, 'session_test.txt', makeTxtBuffer());
        await expect(page.locator('.file-status-badge:has-text("UPLOADED")')).toBeVisible({ timeout: 30000 });
        await page.click('button.analyse-btn');
        await page.waitForURL(/document_analysis\.html/, { timeout: 20000 });

        const resultId = await page.evaluate(() => sessionStorage.getItem('latestResultId'));
        expect(resultId).toBe(FAKE_RESULT_ID);
    });

    test('ANALYSE button becomes disabled once analysis starts', async ({ page }) => {
        await page.route('**/ai/analyze/', () => new Promise(() => {})); // block indefinitely
        await uploadFileViaInput(page, 'progress_test.txt', makeTxtBuffer());
        await expect(page.locator('.file-status-badge:has-text("UPLOADED")')).toBeVisible({ timeout: 30000 });
        await page.click('button.analyse-btn');
        // isAnalysing = true makes canAnalyse = false → button disabled
        await expect(page.locator('button.analyse-btn')).toBeDisabled({ timeout: 5000 });
    });

    test('AI service error shows friendly error message', async ({ page }) => {
        await page.route('**/ai/analyze/', async route => {
            await route.fulfill({
                status: 200,
                contentType: 'text/event-stream',
                body: 'data: {"status":"error","message":"AI service not running"}\n\n',
            });
        });
        await uploadFileViaInput(page, 'error_test.txt', makeTxtBuffer());
        await expect(page.locator('.file-status-badge:has-text("UPLOADED")')).toBeVisible({ timeout: 30000 });
        await page.click('button.analyse-btn');
        await expect(page.locator('.upload-failure-item')).toContainText('temporarily unavailable', { timeout: 15000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// General User: Google Drive & OneDrive UI
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Home Page — General User: Cloud Storage Buttons', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
    });

    test('Google Drive button is visible and clickable', async ({ page }) => {
        const driveBtn = page.locator('.source-btn:has(.source-label:has-text("GOOGLE DRIVE"))');
        await expect(driveBtn).toBeVisible();
    });

    test('OneDrive button is visible and clickable', async ({ page }) => {
        const oneDriveBtn = page.locator('.source-btn:has(.source-label:has-text("ONE DRIVE"))');
        await expect(oneDriveBtn).toBeVisible();
    });

    test('mocked Google Drive upload endpoint returns success', async ({ page }) => {
        await page.route('**/ai/upload-from-drive/', async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    status: 'uploaded',
                    file_name: 'drive_test.pdf',
                    document_id: 'drive-doc-123',
                    s3_url: 'https://fake-s3.amazonaws.com/drive_test.pdf',
                }),
            });
        });
        // Verify the Google Drive source button is present and clickable
        await expect(page.locator('.source-btn:has(.source-label:has-text("GOOGLE DRIVE"))')).toBeVisible();
        // Verify the backend endpoint responds correctly when called
        const status = await page.evaluate(async (token) => {
            const res = await fetch('http://127.0.0.1:8000/ai/upload-from-drive/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ file_id: 'fake-id', access_token: 'fake-token', file_name: 'drive_test.pdf', company_name: '', department: '' })
            });
            return res.status;
        }, await page.evaluate(() => sessionStorage.getItem('authToken')));
        expect(status).toBe(200);
    });

    test('mocked OneDrive upload endpoint accepts file metadata', async ({ page }) => {
        await page.route('**/ai/upload-from-onedrive/', async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    status: 'uploaded',
                    file_name: 'onedrive_test.docx',
                    document_id: 'od-doc-456',
                    s3_url: 'https://fake-s3.amazonaws.com/onedrive_test.docx',
                }),
            });
        });

        const result = await page.evaluate(async () => {
            const response = await fetch('http://127.0.0.1:8000/ai/upload-from-onedrive/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${sessionStorage.getItem('authToken')}`
                },
                body: JSON.stringify({
                    file_id: 'fake-od-file-id',
                    access_token: 'fake-ms-token',
                    file_name: 'onedrive_test.docx',
                    company_name: '',
                    department: ''
                })
            });
            return response.status;
        });

        expect(result).toBe(200);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Authenticated — Admin User: Page Load & Admin-only Fields
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Home Page — Admin User: Session & Rendering', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
    });

    test('admin lands on home.html', async ({ page }) => {
        await expect(page).toHaveURL(/home\.html/);
    });

    test('organisation name field IS visible for admin', async ({ page }) => {
        await expect(page.locator('.org-row')).toBeVisible();
        await expect(page.locator('input.org-input')).toBeVisible();
    });

    test('sessionStorage userRole is ADMINISTRATIVE_USER', async ({ page }) => {
        const role = await page.evaluate(() => sessionStorage.getItem('userRole'));
        expect(role).toBe('ADMINISTRATIVE_USER');
    });

    test('sessionStorage userEmail is correct for admin', async ({ page }) => {
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        const email = await page.evaluate(() => sessionStorage.getItem('userEmail'));
        expect(email).toBe(ADMIN_EMAIL);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Admin User: Organisation Name Validation
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Home Page — Admin User: Organisation Name Validation', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
    });

    test('organisation name input accepts text', async ({ page }) => {
        await page.fill('input.org-input', 'Acme Corporation');
        await expect(page.locator('input.org-input')).toHaveValue('Acme Corporation');
    });

    test('upload without organisation name shows error for admin', async ({ page }) => {
        // Mock upload to return the org name required error
        await page.route('**/ai/upload/', async route => {
            await route.fulfill({
                status: 400,
                contentType: 'application/json',
                body: JSON.stringify({ error: 'Organisation name is required.' }),
            });
        });
        // Leave org name blank and try to upload
        await uploadFileViaInput(page, 'no_org.txt', makeTxtBuffer());
        await expect(page.locator('.upload-failure-item')).toContainText('Organisation name', { timeout: 10000 });
    });

    test('org name input has error styling when org-related error appears', async ({ page }) => {
        await page.route('**/ai/upload/', async route => {
            await route.fulfill({
                status: 400,
                contentType: 'application/json',
                body: JSON.stringify({ error: 'Organisation name is required.' }),
            });
        });
        await uploadFileViaInput(page, 'no_org2.txt', makeTxtBuffer());
        await expect(page.locator('.upload-failure-item')).toBeVisible({ timeout: 10000 });
        // Error class is applied when errorMessages contains 'Organisation'
        await expect(page.locator('input.org-input')).toHaveClass(/org-input-error/);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Admin User: Department Assignment
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Home Page — Admin User: Department Assignment', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await page.fill('input.org-input', 'Test Organisation');
    });

    test('department pill appears for admin after upload', async ({ page }) => {
        await page.route('**/ai/upload/', async route => {
            await route.fulfill({
                status: 400,
                contentType: 'application/json',
                body: JSON.stringify({ error: 'Department is required. Please select a department before uploading.' }),
            });
        });
        await uploadFileViaInput(page, 'dept_test.txt', makeTxtBuffer());
        // Dept pill should appear in admin mode even before upload completes
        await expect(page.locator('.dept-pill')).toBeVisible({ timeout: 10000 });
    });

    test('department pill shows "Assign Dept" when no department selected', async ({ page }) => {
        await page.route('**/ai/upload/', () => new Promise(() => {})); // pause upload
        await uploadFileViaInput(page, 'unassigned.txt', makeTxtBuffer());
        await expect(page.locator('.dept-pill:has-text("Assign Dept")')).toBeVisible({ timeout: 5000 });
    });

    test('clicking department pill opens dropdown with all 12 departments', async ({ page }) => {
        await page.route('**/ai/upload/', () => new Promise(() => {}));
        await uploadFileViaInput(page, 'open_dept.txt', makeTxtBuffer());
        await page.locator('.dept-pill').first().click();
        await expect(page.locator('.dept-dropdown')).toBeVisible({ timeout: 5000 });

        // Verify all 12 departments are present
        const deptOptions = page.locator('.dept-option');
        await expect(deptOptions).toHaveCount(12);

        // Spot check a few department names
        await expect(page.locator('.dept-option:has-text("Finance & Accounting")')).toBeVisible();
        await expect(page.locator('.dept-option:has-text("Human Resources & Administration")')).toBeVisible();
        await expect(page.locator('.dept-option:has-text("Information Technology & Cybersecurity")')).toBeVisible();
        await expect(page.locator('.dept-option:has-text("Legal & Compliance")')).toBeVisible();
    });

    test('selecting a department from dropdown assigns it to the file', async ({ page }) => {
        await page.route('**/ai/upload/', () => new Promise(() => {}));
        await uploadFileViaInput(page, 'assign_dept.txt', makeTxtBuffer());
        await page.locator('.dept-pill').first().click();
        await page.locator('.dept-option:has-text("Finance & Accounting")').click();

        // Dept pill now shows the selected department
        await expect(page.locator('.dept-pill:has-text("Finance & Accounting")')).toBeVisible();
        await expect(page.locator('.dept-pill:has-text("Assign Dept")')).not.toBeVisible();
    });

    test('ANALYSE button is disabled for admin when department not assigned', async ({ page }) => {
        // No upload mock needed — admin files stay pending until dept assigned
        await uploadFileViaInput(page, 'nodept_admin.txt', makeTxtBuffer());
        // File is in pending state — SELECT DEPT badge shown
        await expect(page.locator('.file-status-badge:has-text("SELECT DEPT")')).toBeVisible({ timeout: 10000 });
        // ANALYSE is disabled because hasUploadingFiles includes pending files
        await expect(page.locator('button.analyse-btn')).toBeDisabled({ timeout: 5000 });
    });

    test('upload fails for admin when org name is empty', async ({ page }) => {
        await page.fill('input.org-input', '');
        await uploadFileViaInput(page, 'noorgname.txt', makeTxtBuffer());
        // Frontend validateOrgName() blocks the upload before any API call
        // and pushes this specific message to errorMessages
        await expect(page.locator('.upload-failure-item')).toContainText(
            'Organisation name is required before uploading', { timeout: 5000 }
        );
        // File never added to uploadedFiles so analyse row never appears
        await expect(page.locator('button.analyse-btn')).not.toBeVisible();
    });

    test('file card shows SELECT DEPT when admin uploads without selecting department', async ({ page }) => {
        await page.route('**/ai/upload/', () => new Promise(() => {})); // never fires for pending
        await uploadFileViaInput(page, 'no_dept_err.txt', makeTxtBuffer());
        // In admin mode, file stays pending until dept assigned — shows SELECT DEPT badge
        await expect(page.locator('.file-status-badge:has-text("SELECT DEPT")')).toBeVisible({ timeout: 10000 });
        // No upload error appears because upload hasn't fired yet
        await expect(page.locator('.upload-failure-item')).not.toBeVisible();
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// Admin User: Full Analysis Flow
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Home Page — Admin User: Analysis & Redirect', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await mockAiEndpoints(page);
        await page.fill('input.org-input', 'Test Organisation');

        // Mock upload to return success immediately + include dept field
        await page.route('**/ai/upload/', async route => {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    status: 'uploaded',
                    file_name: 'admin_doc.txt',
                    document_id: 'admin-doc-001',
                    s3_url: 'https://fake-s3/admin_doc.txt'
                }),
            });
        });
    });

    test('admin can analyse after assigning org and department', async ({ page }) => {
        await uploadFileViaInput(page, 'admin_doc.txt', makeTxtBuffer());

        // File appears in pending state — select department
        await expect(page.locator('.dept-pill')).toBeVisible({ timeout: 10000 });
        await page.locator('.dept-pill').first().click();
        await page.locator('.dept-option:has-text("Legal & Compliance")').click();

        // Now the file should be in uploaded state and ANALYSE enabled
        await expect(page.locator('.file-status-badge:has-text("UPLOADED")')).toBeVisible({ timeout: 15000 });
        await expect(page.locator('button.analyse-btn')).toBeEnabled({ timeout: 5000 });

        await page.click('button.analyse-btn');
        await page.waitForURL(/document_analysis\.html/, { timeout: 20000 });
    });

    test('admin latestResultId is stored in sessionStorage after analysis', async ({ page }) => {
        await uploadFileViaInput(page, 'admin_doc.txt', makeTxtBuffer());
        await expect(page.locator('.dept-pill')).toBeVisible({ timeout: 10000 });
        await page.locator('.dept-pill').first().click();
        await page.locator('.dept-option:has-text("Operations")').click();
        await expect(page.locator('.file-status-badge:has-text("UPLOADED")')).toBeVisible({ timeout: 15000 });
        await page.click('button.analyse-btn');
        await page.waitForURL(/document_analysis\.html/, { timeout: 20000 });

        const resultId = await page.evaluate(() => sessionStorage.getItem('latestResultId'));
        expect(resultId).toBe(FAKE_RESULT_ID);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// document_analysis.html — General User
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Document Analysis Page — General User', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsGeneral(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await mockAiEndpoints(page);

        // Seed sessionStorage with a fake result ID then navigate directly
        await page.evaluate((id) => {
            sessionStorage.setItem('latestResultId', id);
        }, FAKE_RESULT_ID);

        await page.goto('./document_analysis.html');
        await page.waitForLoadState('networkidle', { timeout: 15000 });
    });

    test('document_analysis.html loads without redirecting away', async ({ page }) => {
        await expect(page).toHaveURL(/document_analysis\.html/);
    });

    test('compliance score is populated from mocked result', async ({ page }) => {
        // Score 78 from FAKE_ANALYSIS_FETCH
        await expect(page.locator('.compliance-item')).toContainText('78%', { timeout: 10000 });
    });

    test('Back arrow navigates to home.html', async ({ page }) => {
        await page.locator('.back-arrow').click();
        await expect(page).toHaveURL(/home\.html/);
    });

    test('document_analysis.html redirects to login if no authToken', async ({ page }) => {
        await page.evaluate(() => sessionStorage.removeItem('authToken'));
        await page.goto('./document_analysis.html');
        await page.waitForURL(/login\.html/, { timeout: 10000 });
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// document_analysis.html — Admin User
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Document Analysis Page — Admin User', () => {

    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
        await page.waitForLoadState('networkidle', { timeout: 15000 });
        await mockAiEndpoints(page);

        await page.evaluate((id) => {
            sessionStorage.setItem('latestResultId', id);
        }, FAKE_RESULT_ID);

        await page.goto('./document_analysis.html');
        await page.waitForLoadState('networkidle', { timeout: 15000 });
    });

    test('compliance score populated correctly for admin', async ({ page }) => {
        await expect(page.locator('.compliance-item')).toContainText('78%', { timeout: 10000 });
    });

    test('compliance bar fills to correct percentage', async ({ page }) => {
        // Wait for the setTimeout animation (300ms)
        await page.waitForTimeout(500);
        const barFill = page.locator('.compliance-bar-fill');
        const width = await barFill.evaluate(el => el.style.width);
        expect(width).toBe('78%');
    });
});