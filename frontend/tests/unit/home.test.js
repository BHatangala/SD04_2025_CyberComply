/**
 * Unit tests for home.html
 *
 * Covers:
 *  - validateOrgName()       — all validation rules and edge cases
 *  - processFiles()          — file validation, size limit, extension check, queue logic
 *  - canAnalyse computed     — all gate conditions for the Analyse button
 *  - hasUploadingFiles       — detects uploading/pending states
 *  - hasMissingDepartments   — detects missing dept on uploaded files
 *  - hasFileErrors           — detects upload-rule error messages
 *  - formatFileSize()        — bytes → human-readable string
 *  - toggleDeptDropdown()    — closes all others, toggles current
 *  - assignDepartment()      — sets dept, triggers upload for pending files
 *  - removeFile()            — splices file, skips delete for pending/uploading
 *  - uploadErrorMessage()    — correct friendly error based on error type
 *  - historyRow mapping      — sidebar history API response mapping
 *  - resolveIsAdmin()        — role string to boolean
 *  - captureOneDriveToken()  — token extraction from URL hash
 *  - oneDrive fileObj shape  — correct initial shape for admin vs general user
 */

const { describe, test, expect } = require('@jest/globals');

// ─────────────────────────────────────────────────────────────────────────────
// Pure logic extracted from home.html
// ─────────────────────────────────────────────────────────────────────────────

function validateOrgName(companyName, errorMessages) {
    const name = companyName.trim();
    if (!name) {
        errorMessages.push('Organisation name is required before uploading.');
        return false;
    }
    if (name.length < 2) {
        errorMessages.push('Organisation name must be at least 2 characters.');
        return false;
    }
    if (name.length > 200) {
        errorMessages.push('Organisation name must be 200 characters or fewer.');
        return false;
    }
    const validPattern = /^[a-zA-Z0-9\s\-&.,'/()]+$/;
    if (!validPattern.test(name)) {
        errorMessages.push('Organisation name contains invalid characters. Use only letters, numbers, spaces, hyphens, ampersands, or punctuation.');
        return false;
    }
    return true;
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k     = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i     = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

function resolveIsAdmin(roleRaw) {
    return roleRaw === 'ADMINISTRATIVE_USER';
}

function hasUploadingFiles(uploadedFiles, isAdmin) {
    return uploadedFiles.some(f =>
        f.status === 'uploading' || (f.status === 'pending' && isAdmin)
    );
}

function hasMissingDepartments(uploadedFiles) {
    return uploadedFiles
        .filter(f => f.status !== 'uploading' && f.status !== 'error' && f.status !== 'pending')
        .some(f => !f.department);
}

function canAnalyse({ isAnalysing, uploadedFiles, isAdmin, companyName }) {
    if (isAnalysing) return false;
    if (hasUploadingFiles(uploadedFiles, isAdmin)) return false;
    if (uploadedFiles.length === 0) return false;
    const readyFiles = uploadedFiles.filter(f => f.status === 'uploaded');
    if (readyFiles.length === 0) return false;
    if (isAdmin && !companyName.trim()) return false;
    if (isAdmin && hasMissingDepartments(uploadedFiles)) return false;
    return true;
}

function hasFileErrors(errorMessages) {
    return errorMessages.some(msg =>
        msg.includes('MB limit') ||
        msg.includes('not supported') ||
        msg.includes('Maximum 10') ||
        msg.includes('reach the server')
    );
}

/**
 * Mirrors processFiles() validation logic — returns { valid, errors, fileObjs }
 * without triggering uploads (upload is side-effectful and tested separately).
 */
function processFiles({ files, uploadedFiles, isAdmin, companyName }) {
    const errorMessages = [];
    const newFileObjs   = [];

    if (isAdmin) {
        const orgValid = validateOrgName(companyName, errorMessages);
        if (!orgValid) return { valid: false, errorMessages, newFileObjs };
    }

    if (uploadedFiles.length + files.length > 10) {
        errorMessages.push(`Maximum 10 files allowed. You currently have ${uploadedFiles.length} file(s) uploaded.`);
        return { valid: false, errorMessages, newFileObjs };
    }

    for (const file of files) {
        if (file.size > 50 * 1024 * 1024) {
            errorMessages.push(`"${file.name}" exceeds the 50 MB limit.`);
            continue;
        }
        const validExts = ['.pdf', '.docx', '.txt'];
        if (!validExts.some(ext => file.name.toLowerCase().endsWith(ext))) {
            errorMessages.push(`"${file.name}" is not supported. Only PDF, DOCX, and TXT files are allowed.`);
            continue;
        }
        newFileObjs.push({
            name:       file.name,
            size:       file.size,
            status:     isAdmin ? 'pending' : 'uploading',
            department: '',
            deptOpen:   false,
            rawFile:    file,
            source:     'device',
            documentId: null
        });
    }

    return { valid: errorMessages.length === 0, errorMessages, newFileObjs };
}

function toggleDeptDropdown(uploadedFiles, index) {
    const isOpen = uploadedFiles[index].deptOpen;
    uploadedFiles.forEach(f => { f.deptOpen = false; });
    uploadedFiles[index].deptOpen = !isOpen;
    return uploadedFiles;
}

function assignDepartment(uploadedFiles, index, dept) {
    uploadedFiles[index].department = dept;
    uploadedFiles[index].deptOpen   = false;
    const fileObj = uploadedFiles[index];
    if (fileObj.status === 'pending') {
        fileObj.status = 'uploading';
    }
    return uploadedFiles;
}

function removeFileFromList(uploadedFiles, index) {
    const file    = uploadedFiles[index];
    const removed = uploadedFiles.splice(index, 1)[0];
    // Returns whether a delete API call should be made
    const shouldDelete = file.status !== 'uploading' && file.status !== 'pending';
    return { uploadedFiles, removed, shouldDelete };
}

function resolveUploadErrorMessage(errorMessage, fileName) {
    return errorMessage.toLowerCase().includes('failed to fetch')
        ? `Could not reach the server while uploading "${fileName}". Please check your connection and try again.`
        : `"${fileName}" could not be stored. Our file storage is temporarily unavailable — please try again in a few minutes.`;
}

function mapHistoryRow(r) {
    return {
        resultId: r.result_id,
        label:    r.display_name,
        score:    r.compliance_score
    };
}

function captureOneDriveTokenFromHash(hash) {
    if (!hash.includes('access_token')) return null;
    const params = new URLSearchParams(hash.substring(1));
    return params.get('access_token') || null;
}

function buildOneDriveFileObj(file, isAdmin, microsoftAccessToken) {
    return {
        name:            file.name,
        size:            file.size,
        status:          isAdmin ? 'pending' : 'uploading',
        department:      '',
        deptOpen:        false,
        rawFile:         null,
        source:          'onedrive',
        documentId:      null,
        _oneDriveFileId: file.id,
        _oneDriveToken:  microsoftAccessToken
    };
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared test data
// ─────────────────────────────────────────────────────────────────────────────

const makeFile = (name, size = 1024) => ({ name, size });

const uploadedFile = (overrides = {}) => ({
    name:       'Sample.pdf',
    size:       1024,
    status:     'uploaded',
    department: 'IT',
    deptOpen:   false,
    rawFile:    null,
    source:     'device',
    documentId: 'doc-123',
    ...overrides
});

// ─────────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────────

describe('validateOrgName', () => {
    test('returns false and pushes error for empty string', () => {
        const errors = [];
        expect(validateOrgName('', errors)).toBe(false);
        expect(errors[0]).toContain('required');
    });

    test('returns false and pushes error for whitespace-only string', () => {
        const errors = [];
        expect(validateOrgName('   ', errors)).toBe(false);
        expect(errors[0]).toContain('required');
    });

    test('returns false for single character name', () => {
        const errors = [];
        expect(validateOrgName('A', errors)).toBe(false);
        expect(errors[0]).toContain('2 characters');
    });

    test('returns false for name exceeding 200 characters', () => {
        const errors = [];
        expect(validateOrgName('A'.repeat(201), errors)).toBe(false);
        expect(errors[0]).toContain('200 characters');
    });

    test('returns false for name with invalid characters', () => {
        const errors = [];
        expect(validateOrgName('Acme@Corp!', errors)).toBe(false);
        expect(errors[0]).toContain('invalid characters');
    });

    test('returns false for name with special symbols like # $ % ^', () => {
        const errors = [];
        expect(validateOrgName('Corp#123', errors)).toBe(false);
    });

    test('returns true for valid simple name', () => {
        const errors = [];
        expect(validateOrgName('Advantis', errors)).toBe(true);
        expect(errors.length).toBe(0);
    });

    test('returns true for name with allowed special characters', () => {
        const errors = [];
        expect(validateOrgName("O'Brien & Sons (Pvt) Ltd.", errors)).toBe(true);
    });

    test('returns true for name with hyphens and commas', () => {
        const errors = [];
        expect(validateOrgName('ABC-Corp, Inc.', errors)).toBe(true);
    });

    test('returns true for exactly 2 characters', () => {
        const errors = [];
        expect(validateOrgName('AB', errors)).toBe(true);
    });

    test('returns true for exactly 200 characters', () => {
        const errors = [];
        expect(validateOrgName('A'.repeat(200), errors)).toBe(true);
    });

    test('trims leading and trailing whitespace before validating', () => {
        const errors = [];
        expect(validateOrgName('  Advantis  ', errors)).toBe(true);
    });

    test('accumulates multiple errors across separate calls', () => {
        const errors = [];
        validateOrgName('', errors);
        validateOrgName('X', errors);
        expect(errors.length).toBe(2);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('formatFileSize', () => {
    test('returns "0 Bytes" for 0 bytes', () => {
        expect(formatFileSize(0)).toBe('0 Bytes');
    });

    test('formats bytes correctly', () => {
        expect(formatFileSize(512)).toBe('512 Bytes');
    });

    test('formats kilobytes correctly', () => {
        expect(formatFileSize(1024)).toBe('1 KB');
    });

    test('formats megabytes correctly', () => {
        expect(formatFileSize(1024 * 1024)).toBe('1 MB');
    });

    test('formats gigabytes correctly', () => {
        expect(formatFileSize(1024 * 1024 * 1024)).toBe('1 GB');
    });

    test('formats fractional MB correctly', () => {
        expect(formatFileSize(1536 * 1024)).toBe('1.5 MB');
    });

    test('formats 4.36 KB correctly', () => {
        expect(formatFileSize(4465)).toBe('4.36 KB');
    });

    test('formats 50 MB limit boundary correctly', () => {
        expect(formatFileSize(50 * 1024 * 1024)).toBe('50 MB');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('resolveIsAdmin', () => {
    test('returns true for ADMINISTRATIVE_USER', () => {
        expect(resolveIsAdmin('ADMINISTRATIVE_USER')).toBe(true);
    });

    test('returns false for GENERAL_USER', () => {
        expect(resolveIsAdmin('GENERAL_USER')).toBe(false);
    });

    test('returns false for null', () => {
        expect(resolveIsAdmin(null)).toBe(false);
    });

    test('returns false for undefined', () => {
        expect(resolveIsAdmin(undefined)).toBe(false);
    });

    test('returns false for empty string', () => {
        expect(resolveIsAdmin('')).toBe(false);
    });

    test('is case-sensitive', () => {
        expect(resolveIsAdmin('administrative_user')).toBe(false);
        expect(resolveIsAdmin('Administrative_User')).toBe(false);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('hasUploadingFiles', () => {
    test('returns true when a file is uploading', () => {
        const files = [uploadedFile({ status: 'uploading' })];
        expect(hasUploadingFiles(files, false)).toBe(true);
    });

    test('returns true when admin has a pending file', () => {
        const files = [uploadedFile({ status: 'pending' })];
        expect(hasUploadingFiles(files, true)).toBe(true);
    });

    test('returns false when general user has a pending file', () => {
        const files = [uploadedFile({ status: 'pending' })];
        expect(hasUploadingFiles(files, false)).toBe(false);
    });

    test('returns false when all files are uploaded', () => {
        const files = [uploadedFile(), uploadedFile({ name: 'B.pdf' })];
        expect(hasUploadingFiles(files, false)).toBe(false);
    });

    test('returns false for empty array', () => {
        expect(hasUploadingFiles([], false)).toBe(false);
    });

    test('returns true when only one of multiple files is uploading', () => {
        const files = [
            uploadedFile({ status: 'uploaded' }),
            uploadedFile({ name: 'B.pdf', status: 'uploading' })
        ];
        expect(hasUploadingFiles(files, false)).toBe(true);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('hasMissingDepartments', () => {
    test('returns true when an uploaded file has no department', () => {
        const files = [uploadedFile({ department: '' })];
        expect(hasMissingDepartments(files)).toBe(true);
    });

    test('returns false when all uploaded files have departments', () => {
        const files = [uploadedFile({ department: 'IT' })];
        expect(hasMissingDepartments(files)).toBe(false);
    });

    test('ignores uploading files when checking departments', () => {
        const files = [uploadedFile({ status: 'uploading', department: '' })];
        expect(hasMissingDepartments(files)).toBe(false);
    });

    test('ignores pending files when checking departments', () => {
        const files = [uploadedFile({ status: 'pending', department: '' })];
        expect(hasMissingDepartments(files)).toBe(false);
    });

    test('ignores error files when checking departments', () => {
        const files = [uploadedFile({ status: 'error', department: '' })];
        expect(hasMissingDepartments(files)).toBe(false);
    });

    test('returns true when at least one uploaded file has no department', () => {
        const files = [
            uploadedFile({ department: 'IT' }),
            uploadedFile({ name: 'B.pdf', department: '' })
        ];
        expect(hasMissingDepartments(files)).toBe(true);
    });

    test('returns false for empty array', () => {
        expect(hasMissingDepartments([])).toBe(false);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('canAnalyse', () => {
    const baseArgs = {
        isAnalysing:   false,
        uploadedFiles: [uploadedFile()],
        isAdmin:       false,
        companyName:   ''
    };

    test('returns true for general user with one uploaded file', () => {
        expect(canAnalyse(baseArgs)).toBe(true);
    });

    test('returns false when isAnalysing is true', () => {
        expect(canAnalyse({ ...baseArgs, isAnalysing: true })).toBe(false);
    });

    test('returns false when uploadedFiles is empty', () => {
        expect(canAnalyse({ ...baseArgs, uploadedFiles: [] })).toBe(false);
    });

    test('returns false when no files have uploaded status', () => {
        const files = [uploadedFile({ status: 'uploading' })];
        expect(canAnalyse({ ...baseArgs, uploadedFiles: files })).toBe(false);
    });

    test('returns false when file is still uploading', () => {
        const files = [uploadedFile({ status: 'uploading' })];
        expect(canAnalyse({ ...baseArgs, uploadedFiles: files })).toBe(false);
    });

    test('returns false for admin with empty companyName', () => {
        expect(canAnalyse({ ...baseArgs, isAdmin: true, companyName: '' })).toBe(false);
    });

    test('returns false for admin with whitespace-only companyName', () => {
        expect(canAnalyse({ ...baseArgs, isAdmin: true, companyName: '   ' })).toBe(false);
    });

    test('returns false for admin with missing department on uploaded file', () => {
        const files = [uploadedFile({ department: '' })];
        expect(canAnalyse({ ...baseArgs, isAdmin: true, companyName: 'Acme', uploadedFiles: files })).toBe(false);
    });

    test('returns true for admin with all conditions satisfied', () => {
        expect(canAnalyse({ ...baseArgs, isAdmin: true, companyName: 'Acme' })).toBe(true);
    });

    test('returns true for general user regardless of missing department', () => {
        const files = [uploadedFile({ department: '' })];
        expect(canAnalyse({ ...baseArgs, uploadedFiles: files })).toBe(true);
    });

    test('returns false when admin has a pending file (still uploading)', () => {
        const files = [uploadedFile({ status: 'pending' })];
        expect(canAnalyse({ ...baseArgs, isAdmin: true, companyName: 'Acme', uploadedFiles: files })).toBe(false);
    });

    test('returns true when mix of uploaded and error files — at least one uploaded', () => {
        const files = [
            uploadedFile({ status: 'uploaded' }),
            uploadedFile({ name: 'B.pdf', status: 'error' })
        ];
        expect(canAnalyse({ ...baseArgs, uploadedFiles: files })).toBe(true);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('hasFileErrors', () => {
    test('returns true for "MB limit" error', () => {
        expect(hasFileErrors(['"file.pdf" exceeds the 50 MB limit.'])).toBe(true);
    });

    test('returns true for "not supported" error', () => {
        expect(hasFileErrors(['"file.exe" is not supported. Only PDF, DOCX, and TXT files are allowed.'])).toBe(true);
    });

    test('returns true for "Maximum 10" error', () => {
        expect(hasFileErrors(['Maximum 10 files allowed. You currently have 10 file(s) uploaded.'])).toBe(true);
    });

    test('returns true for "reach the server" error', () => {
        expect(hasFileErrors(['Could not reach the server while uploading "file.pdf".'])).toBe(true);
    });

    test('returns false for org name error', () => {
        expect(hasFileErrors(['Organisation name is required before uploading.'])).toBe(false);
    });

    test('returns false for empty array', () => {
        expect(hasFileErrors([])).toBe(false);
    });

    test('returns true when at least one message matches even with others present', () => {
        const msgs = ['Organisation name is required.', '"file.exe" is not supported.'];
        expect(hasFileErrors(msgs)).toBe(true);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('processFiles', () => {
    const validPdf  = makeFile('policy.pdf',  1024);
    const validDocx = makeFile('report.docx', 2048);
    const validTxt  = makeFile('notes.txt',   512);

    test('adds valid PDF to queue for general user with status uploading', () => {
        const { newFileObjs, errorMessages } = processFiles({
            files: [validPdf], uploadedFiles: [], isAdmin: false, companyName: ''
        });
        expect(newFileObjs.length).toBe(1);
        expect(newFileObjs[0].status).toBe('uploading');
        expect(errorMessages.length).toBe(0);
    });

    test('adds valid PDF to queue for admin with status pending', () => {
        const { newFileObjs } = processFiles({
            files: [validPdf], uploadedFiles: [], isAdmin: true, companyName: 'Acme'
        });
        expect(newFileObjs[0].status).toBe('pending');
    });

    test('accepts DOCX files', () => {
        const { newFileObjs, errorMessages } = processFiles({
            files: [validDocx], uploadedFiles: [], isAdmin: false, companyName: ''
        });
        expect(newFileObjs.length).toBe(1);
        expect(errorMessages.length).toBe(0);
    });

    test('accepts TXT files', () => {
        const { newFileObjs, errorMessages } = processFiles({
            files: [validTxt], uploadedFiles: [], isAdmin: false, companyName: ''
        });
        expect(newFileObjs.length).toBe(1);
        expect(errorMessages.length).toBe(0);
    });

    test('rejects unsupported file type and adds error', () => {
        const exeFile = makeFile('virus.exe', 1024);
        const { newFileObjs, errorMessages } = processFiles({
            files: [exeFile], uploadedFiles: [], isAdmin: false, companyName: ''
        });
        expect(newFileObjs.length).toBe(0);
        expect(errorMessages[0]).toContain('not supported');
    });

    test('rejects file exceeding 50MB limit', () => {
        const bigFile = makeFile('huge.pdf', 51 * 1024 * 1024);
        const { newFileObjs, errorMessages } = processFiles({
            files: [bigFile], uploadedFiles: [], isAdmin: false, companyName: ''
        });
        expect(newFileObjs.length).toBe(0);
        expect(errorMessages[0]).toContain('50 MB limit');
    });

    test('rejects batch when total exceeds 10 files', () => {
        const existing = Array(9).fill(null).map((_, i) => uploadedFile({ name: `file${i}.pdf` }));
        const newFiles = [validPdf, validDocx]; // would make 11 total
        const { newFileObjs, errorMessages } = processFiles({
            files: newFiles, uploadedFiles: existing, isAdmin: false, companyName: ''
        });
        expect(newFileObjs.length).toBe(0);
        expect(errorMessages[0]).toContain('Maximum 10');
    });

    test('processes valid files and skips invalid in same batch', () => {
        const exeFile = makeFile('bad.exe', 1024);
        const { newFileObjs, errorMessages } = processFiles({
            files: [validPdf, exeFile], uploadedFiles: [], isAdmin: false, companyName: ''
        });
        expect(newFileObjs.length).toBe(1);
        expect(newFileObjs[0].name).toBe('policy.pdf');
        expect(errorMessages.length).toBe(1);
    });

    test('fails early for admin with missing org name', () => {
        const { newFileObjs, errorMessages } = processFiles({
            files: [validPdf], uploadedFiles: [], isAdmin: true, companyName: ''
        });
        expect(newFileObjs.length).toBe(0);
        expect(errorMessages[0]).toContain('required');
    });

    test('sets source to "device" for all processed files', () => {
        const { newFileObjs } = processFiles({
            files: [validPdf], uploadedFiles: [], isAdmin: false, companyName: ''
        });
        expect(newFileObjs[0].source).toBe('device');
    });

    test('sets documentId to null initially', () => {
        const { newFileObjs } = processFiles({
            files: [validPdf], uploadedFiles: [], isAdmin: false, companyName: ''
        });
        expect(newFileObjs[0].documentId).toBeNull();
    });

    test('sets deptOpen to false initially', () => {
        const { newFileObjs } = processFiles({
            files: [validPdf], uploadedFiles: [], isAdmin: false, companyName: ''
        });
        expect(newFileObjs[0].deptOpen).toBe(false);
    });

    test('handles case-insensitive file extensions', () => {
        const upperFile = makeFile('POLICY.PDF', 1024);
        const { newFileObjs, errorMessages } = processFiles({
            files: [upperFile], uploadedFiles: [], isAdmin: false, companyName: ''
        });
        expect(newFileObjs.length).toBe(1);
        expect(errorMessages.length).toBe(0);
    });

    test('exactly 10 files total is allowed', () => {
        const existing = Array(9).fill(null).map((_, i) => uploadedFile({ name: `file${i}.pdf` }));
        const { newFileObjs, errorMessages } = processFiles({
            files: [validPdf], uploadedFiles: existing, isAdmin: false, companyName: ''
        });
        expect(newFileObjs.length).toBe(1);
        expect(errorMessages.length).toBe(0);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('toggleDeptDropdown', () => {
    let files;

    beforeEach(() => {
        files = [
            uploadedFile({ name: 'A.pdf', deptOpen: false }),
            uploadedFile({ name: 'B.pdf', deptOpen: false }),
            uploadedFile({ name: 'C.pdf', deptOpen: false }),
        ];
    });

    test('opens dropdown for selected index', () => {
        toggleDeptDropdown(files, 1);
        expect(files[1].deptOpen).toBe(true);
    });

    test('closes all other dropdowns when one is opened', () => {
        files[0].deptOpen = true;
        toggleDeptDropdown(files, 1);
        expect(files[0].deptOpen).toBe(false);
        expect(files[1].deptOpen).toBe(true);
        expect(files[2].deptOpen).toBe(false);
    });

    test('toggles closed if already open', () => {
        files[1].deptOpen = true;
        toggleDeptDropdown(files, 1);
        expect(files[1].deptOpen).toBe(false);
    });

    test('only one dropdown can be open at a time', () => {
        toggleDeptDropdown(files, 0);
        toggleDeptDropdown(files, 2);
        const openCount = files.filter(f => f.deptOpen).length;
        expect(openCount).toBe(1);
        expect(files[2].deptOpen).toBe(true);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('assignDepartment', () => {
    test('sets department on the file at given index', () => {
        const files = [uploadedFile({ status: 'pending', department: '' })];
        assignDepartment(files, 0, 'Finance & Accounting');
        expect(files[0].department).toBe('Finance & Accounting');
    });

    test('closes the dept dropdown after assignment', () => {
        const files = [uploadedFile({ status: 'pending', deptOpen: true, department: '' })];
        assignDepartment(files, 0, 'IT');
        expect(files[0].deptOpen).toBe(false);
    });

    test('changes status from pending to uploading', () => {
        const files = [uploadedFile({ status: 'pending', department: '' })];
        assignDepartment(files, 0, 'IT');
        expect(files[0].status).toBe('uploading');
    });

    test('does not change status if file is already uploaded', () => {
        const files = [uploadedFile({ status: 'uploaded', department: 'IT' })];
        assignDepartment(files, 0, 'Finance & Accounting');
        expect(files[0].status).toBe('uploaded');
    });

    test('can assign department to specific index without affecting others', () => {
        const files = [
            uploadedFile({ name: 'A.pdf', department: 'IT' }),
            uploadedFile({ name: 'B.pdf', department: '', status: 'pending' })
        ];
        assignDepartment(files, 1, 'Finance & Accounting');
        expect(files[0].department).toBe('IT');
        expect(files[1].department).toBe('Finance & Accounting');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('removeFileFromList', () => {
    test('removes file at correct index', () => {
        const files = [
            uploadedFile({ name: 'A.pdf' }),
            uploadedFile({ name: 'B.pdf' }),
            uploadedFile({ name: 'C.pdf' })
        ];
        const { uploadedFiles } = removeFileFromList(files, 1);
        expect(uploadedFiles.length).toBe(2);
        expect(uploadedFiles.find(f => f.name === 'B.pdf')).toBeUndefined();
    });

    test('returns the removed file object', () => {
        const files = [uploadedFile({ name: 'A.pdf' })];
        const { removed } = removeFileFromList(files, 0);
        expect(removed.name).toBe('A.pdf');
    });

    test('shouldDelete is true for uploaded file', () => {
        const files = [uploadedFile({ status: 'uploaded' })];
        const { shouldDelete } = removeFileFromList(files, 0);
        expect(shouldDelete).toBe(true);
    });

    test('shouldDelete is false for uploading file', () => {
        const files = [uploadedFile({ status: 'uploading' })];
        const { shouldDelete } = removeFileFromList(files, 0);
        expect(shouldDelete).toBe(false);
    });

    test('shouldDelete is false for pending file', () => {
        const files = [uploadedFile({ status: 'pending' })];
        const { shouldDelete } = removeFileFromList(files, 0);
        expect(shouldDelete).toBe(false);
    });

    test('shouldDelete is true for analysed file', () => {
        const files = [uploadedFile({ status: 'analysed' })];
        const { shouldDelete } = removeFileFromList(files, 0);
        expect(shouldDelete).toBe(true);
    });

    test('removing first file leaves remaining files intact', () => {
        const files = [
            uploadedFile({ name: 'A.pdf' }),
            uploadedFile({ name: 'B.pdf' })
        ];
        const { uploadedFiles } = removeFileFromList(files, 0);
        expect(uploadedFiles[0].name).toBe('B.pdf');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('resolveUploadErrorMessage', () => {
    test('returns connection error message for "failed to fetch" errors', () => {
        const msg = resolveUploadErrorMessage('failed to fetch', 'policy.pdf');
        expect(msg).toContain('Could not reach the server');
        expect(msg).toContain('policy.pdf');
    });

    test('returns storage unavailable message for other errors', () => {
        const msg = resolveUploadErrorMessage('Server returned HTTP 500', 'policy.pdf');
        expect(msg).toContain('could not be stored');
        expect(msg).toContain('policy.pdf');
    });

    test('is case-insensitive for "failed to fetch" detection', () => {
        const msg = resolveUploadErrorMessage('Failed to Fetch', 'policy.pdf');
        expect(msg).toContain('Could not reach the server');
    });

    test('includes the filename in connection error message', () => {
        const msg = resolveUploadErrorMessage('failed to fetch', 'annual_report.docx');
        expect(msg).toContain('annual_report.docx');
    });

    test('includes the filename in storage error message', () => {
        const msg = resolveUploadErrorMessage('timeout', 'notes.txt');
        expect(msg).toContain('notes.txt');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('mapHistoryRow', () => {
    test('maps result_id to resultId', () => {
        const row = { result_id: 'abc-123', display_name: 'Advantis — Sample.txt', compliance_score: 11 };
        expect(mapHistoryRow(row).resultId).toBe('abc-123');
    });

    test('maps display_name to label', () => {
        const row = { result_id: 'x', display_name: 'Atlas — Report.pdf', compliance_score: 80 };
        expect(mapHistoryRow(row).label).toBe('Atlas — Report.pdf');
    });

    test('maps compliance_score to score', () => {
        const row = { result_id: 'x', display_name: 'Y', compliance_score: 55 };
        expect(mapHistoryRow(row).score).toBe(55);
    });

    test('produces object with exactly three keys', () => {
        const row = { result_id: 'x', display_name: 'Y', compliance_score: 0 };
        expect(Object.keys(mapHistoryRow(row))).toEqual(['resultId', 'label', 'score']);
    });

    test('maps multiple rows correctly', () => {
        const rows = [
            { result_id: 'id-1', display_name: 'A', compliance_score: 20 },
            { result_id: 'id-2', display_name: 'B', compliance_score: 90 },
        ];
        const mapped = rows.map(mapHistoryRow);
        expect(mapped[0].resultId).toBe('id-1');
        expect(mapped[1].score).toBe(90);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('captureOneDriveTokenFromHash', () => {
    test('extracts access_token from URL hash', () => {
        const hash = '#access_token=mytoken123&token_type=Bearer';
        expect(captureOneDriveTokenFromHash(hash)).toBe('mytoken123');
    });

    test('returns null when hash does not contain access_token', () => {
        expect(captureOneDriveTokenFromHash('#state=xyz')).toBeNull();
    });

    test('returns null for empty hash', () => {
        expect(captureOneDriveTokenFromHash('')).toBeNull();
    });

    test('returns null for hash with only #', () => {
        expect(captureOneDriveTokenFromHash('#')).toBeNull();
    });

    test('returns correct token when multiple params present', () => {
        const hash = '#token_type=Bearer&access_token=abc456&expires_in=3600';
        expect(captureOneDriveTokenFromHash(hash)).toBe('abc456');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('buildOneDriveFileObj', () => {
    const oneDriveFile = { id: 'drive-file-id-001', name: 'Policy.pdf', size: 4096 };
    const token = 'ms-access-token-xyz';

    test('sets status to pending for admin user', () => {
        const obj = buildOneDriveFileObj(oneDriveFile, true, token);
        expect(obj.status).toBe('pending');
    });

    test('sets status to uploading for general user', () => {
        const obj = buildOneDriveFileObj(oneDriveFile, false, token);
        expect(obj.status).toBe('uploading');
    });

    test('sets source to onedrive', () => {
        const obj = buildOneDriveFileObj(oneDriveFile, false, token);
        expect(obj.source).toBe('onedrive');
    });

    test('stashes _oneDriveFileId for deferred upload', () => {
        const obj = buildOneDriveFileObj(oneDriveFile, true, token);
        expect(obj._oneDriveFileId).toBe('drive-file-id-001');
    });

    test('stashes _oneDriveToken for deferred upload', () => {
        const obj = buildOneDriveFileObj(oneDriveFile, true, token);
        expect(obj._oneDriveToken).toBe('ms-access-token-xyz');
    });

    test('sets rawFile to null (file not stored locally)', () => {
        const obj = buildOneDriveFileObj(oneDriveFile, false, token);
        expect(obj.rawFile).toBeNull();
    });

    test('sets documentId to null initially', () => {
        const obj = buildOneDriveFileObj(oneDriveFile, false, token);
        expect(obj.documentId).toBeNull();
    });

    test('sets department to empty string initially', () => {
        const obj = buildOneDriveFileObj(oneDriveFile, false, token);
        expect(obj.department).toBe('');
    });

    test('sets deptOpen to false initially', () => {
        const obj = buildOneDriveFileObj(oneDriveFile, false, token);
        expect(obj.deptOpen).toBe(false);
    });

    test('correctly copies name and size from file', () => {
        const obj = buildOneDriveFileObj(oneDriveFile, false, token);
        expect(obj.name).toBe('Policy.pdf');
        expect(obj.size).toBe(4096);
    });
});