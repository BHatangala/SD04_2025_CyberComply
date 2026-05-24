const { describe, test, expect } = require('@jest/globals');

function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email.trim());
}

function validateLoginInputs(email, password) {
    const trimmedEmail = email.trim();

    if (!trimmedEmail && !password) {
        return { ok: false, error: 'Please enter your email and password.' };
    }

    if (!trimmedEmail) {
        return { ok: false, error: 'Please enter your email address.' };
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(trimmedEmail)) {
        return { ok: false, error: 'Please enter a valid email address.' };
    }

    if (!password) {
        return { ok: false, error: 'Please enter your password.' };
    }

    return { ok: true, error: null };
}

describe('isValidEmail', () => {
    test('accepts a standard valid email', () => {
        expect(isValidEmail('user@example.com')).toBe(true);
    });

    test('accepts email with subdomain', () => {
        expect(isValidEmail('user@mail.example.com')).toBe(true);
    });

    test('accepts email with plus sign', () => {
        expect(isValidEmail('user+tag@example.com')).toBe(true);
    });

    test('accepts email with numbers in local part', () => {
        expect(isValidEmail('user123@example.org')).toBe(true);
    });

    test('accepts email with leading/trailing whitespace (trimmed internally)', () => {
        expect(isValidEmail('  user@example.com  ')).toBe(true);
    });

    test('rejects email with no @ symbol', () => {
        expect(isValidEmail('userexample.com')).toBe(false);
    });

    test('rejects email with no domain', () => {
        expect(isValidEmail('user@')).toBe(false);
    });

    test('rejects email with no local part', () => {
        expect(isValidEmail('@example.com')).toBe(false);
    });

    test('rejects email with no TLD', () => {
        expect(isValidEmail('user@example')).toBe(false);
    });

    test('rejects email with spaces inside', () => {
        expect(isValidEmail('user @example.com')).toBe(false);
    });

    test('rejects an empty string', () => {
        expect(isValidEmail('')).toBe(false);
    });

    test('rejects a plain string with no email structure', () => {
        expect(isValidEmail('notanemail')).toBe(false);
    });
});

describe('validateLoginInputs', () => {
    test('returns error when both email and password are empty', () => {
        const result = validateLoginInputs('', '');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Please enter your email and password.');
    });

    test('returns error when both fields contain only whitespace', () => {
        const result = validateLoginInputs('   ', '');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Please enter your email and password.');
    });

    test('returns error when email is empty but password is provided', () => {
        const result = validateLoginInputs('', 'Secret123!');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Please enter your email address.');
    });

    test('returns error when email is only whitespace but password is provided', () => {
        const result = validateLoginInputs('   ', 'Secret123!');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Please enter your email address.');
    });

    test('returns error for email without @ symbol', () => {
        const result = validateLoginInputs('invalidemail.com', 'Secret123!');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Please enter a valid email address.');
    });

    test('returns error for email missing TLD', () => {
        const result = validateLoginInputs('user@example', 'Secret123!');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Please enter a valid email address.');
    });

    test('returns error for email missing local part', () => {
        const result = validateLoginInputs('@example.com', 'Secret123!');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Please enter a valid email address.');
    });

    test('returns error for email with embedded spaces', () => {
        const result = validateLoginInputs('user @example.com', 'Secret123!');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Please enter a valid email address.');
    });

    test('returns error when valid email is provided but password is empty', () => {
        const result = validateLoginInputs('user@example.com', '');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Please enter your password.');
    });

    test('returns ok when valid email and password are both provided', () => {
        const result = validateLoginInputs('user@example.com', 'Secret123!');
        expect(result.ok).toBe(true);
        expect(result.error).toBeNull();
    });

    test('trims email whitespace before validating', () => {
        const result = validateLoginInputs('  user@example.com  ', 'Secret123!');
        expect(result.ok).toBe(true);
        expect(result.error).toBeNull();
    });

    test('accepts complex valid email formats', () => {
        const result = validateLoginInputs('first.last+filter@sub.domain.org', 'P@ssw0rd');
        expect(result.ok).toBe(true);
        expect(result.error).toBeNull();
    });
});
