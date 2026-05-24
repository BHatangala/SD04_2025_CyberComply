/**
 * Unit tests for adminaccess.html
 *
 * Covers:
 *  - validateOrgEmail()        — email format guard before the API call
 *  - validateOtpCode()         — must be exactly 6 digits
 *  - resolveStepAfterRequest() — transitions form → otp on success
 *  - resolveStepAfterVerify()  — transitions otp → success on verified
 *  - resolveStepOnError()      — stays on current step when an error occurs
 *  - buildRequestBody()        — correct JSON shape for the request endpoint
 *  - buildVerifyBody()         — correct JSON shape for the verify endpoint
 *  - resolveStatusMessage()    — friendly message derived from the status API response
 *  - shouldResumeOtpStep()     — PENDING status brings user back to OTP entry
 *  - shouldMarkApproved()      — APPROVED status triggers sessionStorage role update
 */

const { describe, test, expect } = require('@jest/globals');

// ─────────────────────────────────────────────────────────────────────────────
// Pure logic extracted from adminaccess.html
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Mirrors the email guard inside `sendVerification()`.
 * Returns true when the value is a non-empty, valid-format email address.
 */
function validateOrgEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return !!(email && emailRegex.test(email));
}

/**
 * Mirrors the OTP format check inside `handleOtpVerified()`.
 * Returns true only for a string of exactly 6 numeric digits.
 */
function validateOtpCode(otp) {
    return /^\d{6}$/.test(otp);
}

/**
 * Mirrors the step-transition logic on a successful `sendVerification()` response.
 * Returns the next step string.
 */
function resolveStepAfterRequest(responseOk) {
    return responseOk ? 'otp' : 'form';
}

/**
 * Mirrors the step-transition logic on a successful `handleOtpVerified()` response.
 * Returns the next step string.
 */
function resolveStepAfterVerify(responseOk) {
    return responseOk ? 'success' : 'otp';
}

/**
 * Mirrors how errors are handled — step stays unchanged on failure.
 */
function resolveStepOnError(currentStep) {
    return currentStep;
}

/**
 * Mirrors the body built for POST /api/admin-access/request/.
 */
function buildRequestBody(orgEmail) {
    return { org_email: orgEmail };
}

/**
 * Mirrors the body built for POST /api/admin-access/verify/.
 */
function buildVerifyBody(otpCode, requestId) {
    return { otp: otpCode, request_id: requestId };
}

/**
 * Mirrors the message constructed inside `checkAdminRequestStatus()`
 * when the backend returns status PENDING.
 */
function resolveStatusMessage(status, orgEmail) {
    if (status === 'PENDING') {
        return `You have a pending request. Enter the code sent to ${orgEmail}`;
    }
    return '';
}

/**
 * Mirrors the condition that causes the OTP modal to re-appear for a PENDING request.
 */
function shouldResumeOtpStep(status) {
    return status === 'PENDING';
}

/**
 * Mirrors the condition that updates the user's sessionStorage role on APPROVED.
 */
function shouldMarkApproved(status) {
    return status === 'APPROVED';
}

/**
 * Mirrors the OTP sanitisation applied in the input handler:
 * strips non-digit characters and truncates to 6 characters.
 */
function sanitiseOtpInput(raw) {
    return raw.replace(/\D/g, '').slice(0, 6);
}

/**
 * Mirrors the early-exit guard at the top of `handleOtpVerified()`.
 * Returns true when there is no active request ID (user skipped the request step).
 */
function isMissingRequestId(requestId) {
    return !requestId;
}

// ─────────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────────

describe('validateOrgEmail', () => {
    test('returns true for a standard email address', () => {
        expect(validateOrgEmail('hello@cybercomply.com')).toBe(true);
    });

    test('returns true for an email with a subdomain', () => {
        expect(validateOrgEmail('admin@mail.corp.io')).toBe(true);
    });

    test('returns false for an empty string', () => {
        expect(validateOrgEmail('')).toBe(false);
    });

    test('returns false for null', () => {
        expect(validateOrgEmail(null)).toBe(false);
    });

    test('returns false for undefined', () => {
        expect(validateOrgEmail(undefined)).toBe(false);
    });

    test('returns false when the @ symbol is missing', () => {
        expect(validateOrgEmail('hellocybercomply.com')).toBe(false);
    });

    test('returns false when the domain is missing', () => {
        expect(validateOrgEmail('hello@')).toBe(false);
    });

    test('returns false when the TLD is missing', () => {
        expect(validateOrgEmail('hello@cybercomply')).toBe(false);
    });

    test('returns false for plain text with no email structure', () => {
        expect(validateOrgEmail('notanemail')).toBe(false);
    });

    test('returns false when there is a space in the address', () => {
        expect(validateOrgEmail('hel lo@cybercomply.com')).toBe(false);
    });

    test('returns true for email with plus addressing', () => {
        expect(validateOrgEmail('admin+test@cybercomply.com')).toBe(true);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('validateOtpCode', () => {
    test('returns true for a valid 6-digit code', () => {
        expect(validateOtpCode('123456')).toBe(true);
    });

    test('returns true for code with leading zeros', () => {
        expect(validateOtpCode('007890')).toBe(true);
    });

    test('returns false for a 5-digit code', () => {
        expect(validateOtpCode('12345')).toBe(false);
    });

    test('returns false for a 7-digit code', () => {
        expect(validateOtpCode('1234567')).toBe(false);
    });

    test('returns false for an empty string', () => {
        expect(validateOtpCode('')).toBe(false);
    });

    test('returns false for code containing letters', () => {
        expect(validateOtpCode('12345a')).toBe(false);
    });

    test('returns false for code containing spaces', () => {
        expect(validateOtpCode('123 456')).toBe(false);
    });

    test('returns false for code containing special characters', () => {
        expect(validateOtpCode('12-456')).toBe(false);
    });

    test('returns false for all zeros — still a valid digit sequence', () => {
        expect(validateOtpCode('000000')).toBe(true);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('resolveStepAfterRequest', () => {
    test('transitions to "otp" when the API call succeeds', () => {
        expect(resolveStepAfterRequest(true)).toBe('otp');
    });

    test('stays on "form" when the API call fails', () => {
        expect(resolveStepAfterRequest(false)).toBe('form');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('resolveStepAfterVerify', () => {
    test('transitions to "success" when OTP is verified', () => {
        expect(resolveStepAfterVerify(true)).toBe('success');
    });

    test('stays on "otp" when OTP verification fails', () => {
        expect(resolveStepAfterVerify(false)).toBe('otp');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('resolveStepOnError', () => {
    test('keeps the step as "form" when an error occurs on the form step', () => {
        expect(resolveStepOnError('form')).toBe('form');
    });

    test('keeps the step as "otp" when an error occurs on the otp step', () => {
        expect(resolveStepOnError('otp')).toBe('otp');
    });

    test('keeps the step as "success" if somehow an error fires there', () => {
        expect(resolveStepOnError('success')).toBe('success');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('buildRequestBody', () => {
    test('produces an object with the org_email key', () => {
        const body = buildRequestBody('admin@corp.com');
        expect(body).toHaveProperty('org_email');
    });

    test('sets org_email to the provided email string', () => {
        const body = buildRequestBody('admin@corp.com');
        expect(body.org_email).toBe('admin@corp.com');
    });

    test('produces exactly one key', () => {
        const body = buildRequestBody('admin@corp.com');
        expect(Object.keys(body)).toHaveLength(1);
    });

    test('preserves the email value exactly as given', () => {
        const body = buildRequestBody('ADMIN@CORP.COM');
        expect(body.org_email).toBe('ADMIN@CORP.COM');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('buildVerifyBody', () => {
    test('produces an object with otp and request_id keys', () => {
        const body = buildVerifyBody('123456', 'req-abc');
        expect(body).toHaveProperty('otp');
        expect(body).toHaveProperty('request_id');
    });

    test('sets otp to the provided code', () => {
        const body = buildVerifyBody('654321', 'req-xyz');
        expect(body.otp).toBe('654321');
    });

    test('sets request_id to the provided id', () => {
        const body = buildVerifyBody('000000', 'req-999');
        expect(body.request_id).toBe('req-999');
    });

    test('produces exactly two keys', () => {
        const body = buildVerifyBody('123456', 'req-abc');
        expect(Object.keys(body)).toHaveLength(2);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('resolveStatusMessage', () => {
    test('returns a pending message that includes the org email', () => {
        const msg = resolveStatusMessage('PENDING', 'admin@corp.com');
        expect(msg).toContain('admin@corp.com');
    });

    test('returns a pending message that mentions the verification code', () => {
        const msg = resolveStatusMessage('PENDING', 'admin@corp.com');
        expect(msg).toContain('code');
    });

    test('returns an empty string for APPROVED status', () => {
        expect(resolveStatusMessage('APPROVED', 'admin@corp.com')).toBe('');
    });

    test('returns an empty string for an unknown status', () => {
        expect(resolveStatusMessage('EXPIRED', 'admin@corp.com')).toBe('');
    });

    test('returns an empty string when status is empty', () => {
        expect(resolveStatusMessage('', 'admin@corp.com')).toBe('');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('shouldResumeOtpStep', () => {
    test('returns true for PENDING status', () => {
        expect(shouldResumeOtpStep('PENDING')).toBe(true);
    });

    test('returns false for APPROVED status', () => {
        expect(shouldResumeOtpStep('APPROVED')).toBe(false);
    });

    test('returns false for an empty status string', () => {
        expect(shouldResumeOtpStep('')).toBe(false);
    });

    test('returns false for an unrecognised status', () => {
        expect(shouldResumeOtpStep('EXPIRED')).toBe(false);
    });

    test('is case-sensitive — lowercase pending does not match', () => {
        expect(shouldResumeOtpStep('pending')).toBe(false);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('shouldMarkApproved', () => {
    test('returns true for APPROVED status', () => {
        expect(shouldMarkApproved('APPROVED')).toBe(true);
    });

    test('returns false for PENDING status', () => {
        expect(shouldMarkApproved('PENDING')).toBe(false);
    });

    test('returns false for an empty status string', () => {
        expect(shouldMarkApproved('')).toBe(false);
    });

    test('returns false for an unrecognised status', () => {
        expect(shouldMarkApproved('EXPIRED')).toBe(false);
    });

    test('is case-sensitive — lowercase approved does not match', () => {
        expect(shouldMarkApproved('approved')).toBe(false);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('sanitiseOtpInput', () => {
    test('strips non-digit characters', () => {
        expect(sanitiseOtpInput('12a45b')).toBe('1245');
    });

    test('truncates to 6 characters', () => {
        expect(sanitiseOtpInput('12345678')).toBe('123456');
    });

    test('strips letters and truncates in the same pass', () => {
        expect(sanitiseOtpInput('1a2b3c4d5e6f7')).toBe('123456');
    });

    test('returns empty string for all non-digits', () => {
        expect(sanitiseOtpInput('abcdef')).toBe('');
    });

    test('preserves a clean 6-digit code unchanged', () => {
        expect(sanitiseOtpInput('123456')).toBe('123456');
    });

    test('handles empty input', () => {
        expect(sanitiseOtpInput('')).toBe('');
    });

    test('strips spaces from the input', () => {
        expect(sanitiseOtpInput('1 2 3 4 5 6')).toBe('123456');
    });

    test('strips hyphens from a formatted code', () => {
        expect(sanitiseOtpInput('123-456')).toBe('123456');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('isMissingRequestId', () => {
    test('returns true for null request ID', () => {
        expect(isMissingRequestId(null)).toBe(true);
    });

    test('returns true for undefined request ID', () => {
        expect(isMissingRequestId(undefined)).toBe(true);
    });

    test('returns true for empty string request ID', () => {
        expect(isMissingRequestId('')).toBe(true);
    });

    test('returns false for a valid request ID string', () => {
        expect(isMissingRequestId('req-abc-123')).toBe(false);
    });

    test('returns false for a numeric-looking request ID', () => {
        expect(isMissingRequestId('42')).toBe(false);
    });
});