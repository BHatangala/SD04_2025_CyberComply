const { describe, test, expect } = require('@jest/globals');

// ── Recreate canAnalyse and validateOrgName logic from home.html ──

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
        errorMessages.push('Organisation name contains invalid characters.');
        return false;
    }
    return true;
}

function canAnalyse({ isAnalysing, uploadedFiles, isAdmin, companyName }) {
    if (isAnalysing) return false;
    const hasUploading = uploadedFiles.some(f =>
        f.status === 'uploading' || (f.status === 'pending' && isAdmin)
    );
    if (hasUploading) return false;
    if (uploadedFiles.length === 0) return false;
    const readyFiles = uploadedFiles.filter(f => f.status === 'uploaded');
    if (readyFiles.length === 0) return false;
    if (isAdmin && !companyName.trim()) return false;
    const hasMissingDepts = uploadedFiles
        .filter(f => f.status !== 'uploading' && f.status !== 'error' && f.status !== 'pending')
        .some(f => !f.department);
    if (isAdmin && hasMissingDepts) return false;
    return true;
}

describe('validateOrgName', () => {
    test('returns false and pushes error for empty name', () => {
        const errors = [];
        expect(validateOrgName('', errors)).toBe(false);
        expect(errors[0]).toContain('required');
    });

    test('returns false for single character name', () => {
        const errors = [];
        expect(validateOrgName('A', errors)).toBe(false);
        expect(errors[0]).toContain('2 characters');
    });

    test('returns false for name with invalid characters', () => {
        const errors = [];
        expect(validateOrgName('Acme@Corp!', errors)).toBe(false);
        expect(errors[0]).toContain('invalid characters');
    });

    test('returns true for valid org name', () => {
        const errors = [];
        expect(validateOrgName('Advantis Corp', errors)).toBe(true);
        expect(errors.length).toBe(0);
    });

    test('returns true for name with allowed special characters', () => {
        const errors = [];
        expect(validateOrgName("O'Brien & Sons (Pvt) Ltd.", errors)).toBe(true);
    });
});

describe('canAnalyse', () => {
    const baseFile = { name: 'test.pdf', status: 'uploaded', department: 'IT' };

    test('returns false when isAnalysing is true', () => {
        expect(canAnalyse({ isAnalysing: true, uploadedFiles: [baseFile], isAdmin: false, companyName: '' })).toBe(false);
    });

    test('returns false when no files present', () => {
        expect(canAnalyse({ isAnalysing: false, uploadedFiles: [], isAdmin: false, companyName: '' })).toBe(false);
    });

    test('returns false when no files are in uploaded status', () => {
        const files = [{ ...baseFile, status: 'uploading' }];
        expect(canAnalyse({ isAnalysing: false, uploadedFiles: files, isAdmin: false, companyName: '' })).toBe(false);
    });

    test('returns false for admin with empty companyName', () => {
        expect(canAnalyse({ isAnalysing: false, uploadedFiles: [baseFile], isAdmin: true, companyName: '' })).toBe(false);
    });

    test('returns false for admin with missing department', () => {
        const files = [{ ...baseFile, department: '' }];
        expect(canAnalyse({ isAnalysing: false, uploadedFiles: files, isAdmin: true, companyName: 'Acme' })).toBe(false);
    });

    test('returns true for admin with all fields satisfied', () => {
        expect(canAnalyse({ isAnalysing: false, uploadedFiles: [baseFile], isAdmin: true, companyName: 'Acme' })).toBe(true);
    });

    test('returns true for general user with uploaded file and no dept requirement', () => {
        const files = [{ ...baseFile, department: '' }];
        expect(canAnalyse({ isAnalysing: false, uploadedFiles: files, isAdmin: false, companyName: '' })).toBe(true);
    });
});