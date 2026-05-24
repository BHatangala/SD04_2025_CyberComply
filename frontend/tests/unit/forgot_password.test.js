const { describe, test, expect } = require('@jest/globals');

function getPasswordChecks(password) {
    const p = password || '';
    return {
        length:    p.length >= 8,
        uppercase: /[A-Z]/.test(p),
        digit:     /\d/.test(p),
        special:   /[!@#$%^&*(),.?":{}|<>_\-\\\[\]\\/`~+=;']/.test(p)
    };
}

function allPasswordRulesValid(password) {
    const c = getPasswordChecks(password);
    return c.length && c.uppercase && c.digit && c.special;
}

function passwordMatch(newPassword, confirmPassword) {
    return (
        newPassword.length > 0 &&
        confirmPassword.length > 0 &&
        newPassword === confirmPassword
    );
}

function validateForgotPasswordEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const trimmedEmail = email.trim();

    if (!trimmedEmail || !emailRegex.test(trimmedEmail)) {
        return { ok: false, error: 'Please enter a valid email address.' };
    }

    return { ok: true, error: null };
}

function validateResetPassword(newPassword, confirmPassword) {
    if (!newPassword || !confirmPassword) {
        return { ok: false, error: 'Please fill in both password fields.' };
    }

    const unmet = [];
    if (newPassword.length < 8)             unmet.push('at least 8 characters');
    if (!/[A-Z]/.test(newPassword))          unmet.push('1 uppercase letter');
    if (!/[0-9]/.test(newPassword))          unmet.push('1 digit');
    if (!/[^A-Za-z0-9]/.test(newPassword))   unmet.push('and 1 special character');

    if (unmet.length > 0) {
        return { ok: false, error: 'Password must contain ' + unmet.join(', ') + '.' };
    }

    if (newPassword !== confirmPassword) {
        return { ok: false, error: 'Passwords do not match.' };
    }

    return { ok: true, error: null };
}

describe('getPasswordChecks', () => {
    test('all checks fail for an empty string', () => {
        const c = getPasswordChecks('');
        expect(c.length).toBe(false);
        expect(c.uppercase).toBe(false);
        expect(c.digit).toBe(false);
        expect(c.special).toBe(false);
    });

    test('length check passes for exactly 8 characters', () => {
        expect(getPasswordChecks('abcdefgh').length).toBe(true);
    });

    test('length check fails for 7 characters', () => {
        expect(getPasswordChecks('abcdefg').length).toBe(false);
    });

    test('uppercase check passes when an uppercase letter is present', () => {
        expect(getPasswordChecks('Password').uppercase).toBe(true);
    });

    test('uppercase check fails when only lowercase letters are present', () => {
        expect(getPasswordChecks('password').uppercase).toBe(false);
    });

    test('digit check passes when a digit is present', () => {
        expect(getPasswordChecks('password1').digit).toBe(true);
    });

    test('digit check fails when no digit is present', () => {
        expect(getPasswordChecks('Password').digit).toBe(false);
    });

    test('special check passes for !', () => {
        expect(getPasswordChecks('Password1!').special).toBe(true);
    });

    test('special check passes for @', () => {
        expect(getPasswordChecks('Password1@').special).toBe(true);
    });

    test('special check passes for #', () => {
        expect(getPasswordChecks('Password1#').special).toBe(true);
    });

    test('special check passes for _', () => {
        expect(getPasswordChecks('Password1_').special).toBe(true);
    });

    test('special check fails when no special character is present', () => {
        expect(getPasswordChecks('Password1').special).toBe(false);
    });

    test('all checks pass for a fully valid password', () => {
        const c = getPasswordChecks('SecureP@ss1');
        expect(c.length).toBe(true);
        expect(c.uppercase).toBe(true);
        expect(c.digit).toBe(true);
        expect(c.special).toBe(true);
    });
});

describe('allPasswordRulesValid', () => {
    test('returns true for a fully valid password', () => {
        expect(allPasswordRulesValid('SecureP@ss1')).toBe(true);
    });

    test('returns false when password is too short', () => {
        expect(allPasswordRulesValid('Sh0rt!')).toBe(false);
    });

    test('returns false when uppercase is missing', () => {
        expect(allPasswordRulesValid('secure@pass1')).toBe(false);
    });

    test('returns false when digit is missing', () => {
        expect(allPasswordRulesValid('SecureP@ss')).toBe(false);
    });

    test('returns false when special character is missing', () => {
        expect(allPasswordRulesValid('SecurePass1')).toBe(false);
    });

    test('returns false for an empty password', () => {
        expect(allPasswordRulesValid('')).toBe(false);
    });

    test('returns true for minimum viable valid password (exactly 8 chars)', () => {
        expect(allPasswordRulesValid('Abcdef1!')).toBe(true);
    });
});

describe('passwordMatch', () => {
    test('returns true when both passwords are identical and non-empty', () => {
        expect(passwordMatch('SecureP@ss1', 'SecureP@ss1')).toBe(true);
    });

    test('returns false when passwords differ', () => {
        expect(passwordMatch('SecureP@ss1', 'DifferentP@ss1')).toBe(false);
    });

    test('returns false when newPassword is empty', () => {
        expect(passwordMatch('', 'SecureP@ss1')).toBe(false);
    });

    test('returns false when confirmPassword is empty', () => {
        expect(passwordMatch('SecureP@ss1', '')).toBe(false);
    });

    test('returns false when both are empty', () => {
        expect(passwordMatch('', '')).toBe(false);
    });

    test('is case-sensitive (uppercase vs lowercase differs)', () => {
        expect(passwordMatch('SecureP@ss1', 'securep@ss1')).toBe(false);
    });

    test('returns false when passwords differ only by trailing space', () => {
        expect(passwordMatch('SecureP@ss1', 'SecureP@ss1 ')).toBe(false);
    });
});

describe('validateForgotPasswordEmail', () => {
    test('accepts a standard valid email', () => {
        const result = validateForgotPasswordEmail('user@example.com');
        expect(result.ok).toBe(true);
        expect(result.error).toBeNull();
    });

    test('accepts email with leading/trailing whitespace (trimmed internally)', () => {
        const result = validateForgotPasswordEmail('  user@example.com  ');
        expect(result.ok).toBe(true);
        expect(result.error).toBeNull();
    });

    test('returns error for an empty string', () => {
        const result = validateForgotPasswordEmail('');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Please enter a valid email address.');
    });

    test('returns error for whitespace-only input', () => {
        const result = validateForgotPasswordEmail('   ');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Please enter a valid email address.');
    });

    test('returns error for email missing @', () => {
        const result = validateForgotPasswordEmail('userexample.com');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Please enter a valid email address.');
    });

    test('returns error for email missing domain', () => {
        const result = validateForgotPasswordEmail('user@');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Please enter a valid email address.');
    });

    test('returns error for email missing TLD', () => {
        const result = validateForgotPasswordEmail('user@example');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Please enter a valid email address.');
    });

    test('returns error for plain text', () => {
        const result = validateForgotPasswordEmail('notanemail');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Please enter a valid email address.');
    });
});

describe('validateResetPassword', () => {
    test('returns error when both password fields are empty', () => {
        const result = validateResetPassword('', '');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Please fill in both password fields.');
    });

    test('returns error when only newPassword is empty', () => {
        const result = validateResetPassword('', 'SecureP@ss1');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Please fill in both password fields.');
    });

    test('returns error when only confirmPassword is empty', () => {
        const result = validateResetPassword('SecureP@ss1', '');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Please fill in both password fields.');
    });

    test('returns error when password is shorter than 8 characters', () => {
        const result = validateResetPassword('Sh0!', 'Sh0!');
        expect(result.ok).toBe(false);
        expect(result.error).toContain('at least 8 characters');
    });

    test('returns error when password has no uppercase letter', () => {
        const result = validateResetPassword('secure@pass1', 'secure@pass1');
        expect(result.ok).toBe(false);
        expect(result.error).toContain('1 uppercase letter');
    });

    test('returns error when password has no digit', () => {
        const result = validateResetPassword('SecureP@ss', 'SecureP@ss');
        expect(result.ok).toBe(false);
        expect(result.error).toContain('1 digit');
    });

    test('returns error when password has no special character', () => {
        const result = validateResetPassword('SecurePass1', 'SecurePass1');
        expect(result.ok).toBe(false);
        expect(result.error).toContain('and 1 special character');
    });

    test('error message lists multiple unmet requirements', () => {
        const result = validateResetPassword('alllowercase', 'alllowercase');
        expect(result.ok).toBe(false);
        expect(result.error).toContain('1 uppercase letter');
        expect(result.error).toContain('1 digit');
        expect(result.error).toContain('and 1 special character');
    });

    test('returns error when passwords do not match', () => {
        const result = validateResetPassword('SecureP@ss1', 'DifferentP@ss1');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Passwords do not match.');
    });

    test('is case-sensitive when comparing passwords', () => {
        const result = validateResetPassword('SecureP@ss1', 'securep@ss1');
        expect(result.ok).toBe(false);
        expect(result.error).toBe('Passwords do not match.');
    });

    test('returns ok for a fully valid, matching password pair', () => {
        const result = validateResetPassword('SecureP@ss1', 'SecureP@ss1');
        expect(result.ok).toBe(true);
        expect(result.error).toBeNull();
    });

    test('accepts a minimum-viable password (exactly 8 chars, all rules met)', () => {
        const result = validateResetPassword('Abcdef1!', 'Abcdef1!');
        expect(result.ok).toBe(true);
        expect(result.error).toBeNull();
    });
});
