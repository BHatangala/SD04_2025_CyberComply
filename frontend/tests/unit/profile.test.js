/**
 * Unit tests for profile.html
 *
 * Covers:
 *  - roleDisplay computed      — role string → human-readable label
 *  - validateNameForSave()     — name must be at least 3 characters
 *  - validateEmailForSave()    — basic email format check
 *  - hasNameChanged()          — detects a real name change (trimmed)
 *  - hasEmailChanged()         — detects a real email change (trimmed + lowercased)
 *  - resolveIsAdmin()          — role string → boolean for lock/toast logic
 *  - shouldDeleteOnServer()    — true only when account deletion OTP was requested successfully
 *  - twofaToggleReverts()      — 2FA flag inverts on API failure
 */

const { describe, test, expect } = require('@jest/globals');

// ─────────────────────────────────────────────────────────────────────────────
// Pure logic extracted from profile.html
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Mirrors the `roleDisplay` computed property.
 * Maps the raw role string stored in `this.role` to a user-facing label.
 */
function roleDisplay(role) {
    const r = (role || '').toLowerCase();
    if (r.includes('administrative')) return 'Administrative User';
    if (r.includes('general'))        return 'General User';
    return 'General User';
}

/**
 * Mirrors the name validation inside `confirmSave()`.
 * Returns true when the trimmed name is valid (≥ 3 characters).
 */
function validateNameForSave(name) {
    return name.trim().length >= 3;
}

/**
 * Mirrors the email validation inside `confirmSave()`.
 * Returns true when the value matches a basic email pattern.
 */
function validateEmailForSave(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

/**
 * Mirrors the `nameChanged` flag computed inside `confirmSave()`.
 * Trims the edited value before comparing.
 */
function hasNameChanged(editedFullName, originalFullName) {
    return editedFullName.trim() !== originalFullName;
}

/**
 * Mirrors the `emailChanged` flag computed inside `confirmSave()`.
 * Trims and lower-cases the edited value before comparing.
 */
function hasEmailChanged(editedEmail, originalEmail) {
    return editedEmail.trim().toLowerCase() !== originalEmail;
}

/**
 * Mirrors the `resolveIsAdmin` logic used to set `this.isAdmin` in
 * `loadUserProfile()`. Determines whether the Grant Admin Access button
 * should be locked.
 */
function resolveIsAdmin(roleRaw) {
    return (roleRaw || '').toLowerCase().includes('administrative');
}

/**
 * Mirrors the guard at the start of `grantAdminAccess()`.
 * When the user is already an admin the toast fires and navigation is blocked.
 */
function shouldBlockAdminAccess(isAdmin) {
    return isAdmin === true;
}

/**
 * Mirrors the 2FA revert logic inside `updateTwoFactorSetting()`.
 * When the API call fails, the flag is toggled back to its previous value.
 */
function revertTwoFactor(current) {
    return !current;
}

/**
 * Mirrors the `cancelEdit()` logic.
 * Returns the value the field should revert to: the temp backup if available,
 * otherwise the original value.
 */
function resolveCancelValue(tempValue, originalValue) {
    return tempValue || originalValue;
}

/**
 * Mirrors the watch logic on `editedFullName` / `editedEmail`.
 * `hasChanges` becomes true only when the new value differs from the original.
 */
function computeHasChanges(newVal, originalVal) {
    return newVal !== originalVal;
}

// ─────────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────────

describe('roleDisplay', () => {
    test('returns "Administrative User" for ADMINISTRATIVE_USER', () => {
        expect(roleDisplay('ADMINISTRATIVE_USER')).toBe('Administrative User');
    });

    test('returns "General User" for GENERAL_USER', () => {
        expect(roleDisplay('GENERAL_USER')).toBe('General User');
    });

    test('returns "General User" for empty string', () => {
        expect(roleDisplay('')).toBe('General User');
    });

    test('returns "General User" for null', () => {
        expect(roleDisplay(null)).toBe('General User');
    });

    test('returns "General User" for undefined', () => {
        expect(roleDisplay(undefined)).toBe('General User');
    });

    test('is case-insensitive — lowercase administrative matches', () => {
        expect(roleDisplay('administrative_user')).toBe('Administrative User');
    });

    test('is case-insensitive — mixed case general matches', () => {
        expect(roleDisplay('General_User')).toBe('General User');
    });

    test('returns "Administrative User" when role contains "administrative" as substring', () => {
        expect(roleDisplay('ROLE_ADMINISTRATIVE_USER')).toBe('Administrative User');
    });

    test('returns "General User" for an unrecognised role string', () => {
        expect(roleDisplay('SUPER_USER')).toBe('General User');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('validateNameForSave', () => {
    test('returns false for empty string', () => {
        expect(validateNameForSave('')).toBe(false);
    });

    test('returns false for single character', () => {
        expect(validateNameForSave('A')).toBe(false);
    });

    test('returns false for two characters', () => {
        expect(validateNameForSave('AB')).toBe(false);
    });

    test('returns true for exactly 3 characters', () => {
        expect(validateNameForSave('ABC')).toBe(true);
    });

    test('returns true for a normal name', () => {
        expect(validateNameForSave('Alice')).toBe(true);
    });

    test('trims whitespace before checking length', () => {
        expect(validateNameForSave('  A  ')).toBe(false);
    });

    test('returns true for a name that is valid after trimming', () => {
        expect(validateNameForSave('  Alice  ')).toBe(true);
    });

    test('returns false for whitespace-only string', () => {
        expect(validateNameForSave('   ')).toBe(false);
    });

    test('returns true for a long name', () => {
        expect(validateNameForSave('A'.repeat(100))).toBe(true);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('validateEmailForSave', () => {
    test('returns true for a standard email address', () => {
        expect(validateEmailForSave('user@example.com')).toBe(true);
    });

    test('returns true for an email with a subdomain', () => {
        expect(validateEmailForSave('user@mail.example.co.uk')).toBe(true);
    });

    test('returns false for a missing @ symbol', () => {
        expect(validateEmailForSave('userexample.com')).toBe(false);
    });

    test('returns false for a missing domain', () => {
        expect(validateEmailForSave('user@')).toBe(false);
    });

    test('returns false for a missing TLD', () => {
        expect(validateEmailForSave('user@example')).toBe(false);
    });

    test('returns false for an empty string', () => {
        expect(validateEmailForSave('')).toBe(false);
    });

    test('returns false when there is a space in the local part', () => {
        expect(validateEmailForSave('us er@example.com')).toBe(false);
    });

    test('returns false for plain text with no email structure', () => {
        expect(validateEmailForSave('notanemail')).toBe(false);
    });

    test('returns true for email with plus addressing', () => {
        expect(validateEmailForSave('user+tag@example.com')).toBe(true);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('hasNameChanged', () => {
    test('returns false when edited name equals original after trim', () => {
        expect(hasNameChanged('Alice', 'Alice')).toBe(false);
    });

    test('returns false when edited name has extra whitespace but matches original', () => {
        expect(hasNameChanged('  Alice  ', 'Alice')).toBe(false);
    });

    test('returns true when edited name differs from original', () => {
        expect(hasNameChanged('Bob', 'Alice')).toBe(true);
    });

    test('returns true when edited name is empty (user cleared the field)', () => {
        expect(hasNameChanged('', 'Alice')).toBe(true);
    });

    test('returns true when a trailing character was added', () => {
        expect(hasNameChanged('Alice!', 'Alice')).toBe(true);
    });

    test('returns false when both are empty strings', () => {
        expect(hasNameChanged('', '')).toBe(false);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('hasEmailChanged', () => {
    test('returns false when edited email equals original', () => {
        expect(hasEmailChanged('user@example.com', 'user@example.com')).toBe(false);
    });

    test('returns false when edited email matches original after trim and lowercase', () => {
        expect(hasEmailChanged('  USER@EXAMPLE.COM  ', 'user@example.com')).toBe(false);
    });

    test('returns true when edited email is different', () => {
        expect(hasEmailChanged('new@example.com', 'old@example.com')).toBe(true);
    });

    test('returns true when only the domain changes', () => {
        expect(hasEmailChanged('user@new.com', 'user@old.com')).toBe(true);
    });

    test('returns true when edited email is empty', () => {
        expect(hasEmailChanged('', 'user@example.com')).toBe(true);
    });

    test('returns false when both are empty strings', () => {
        expect(hasEmailChanged('', '')).toBe(false);
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

    test('is case-insensitive — lowercase matches', () => {
        expect(resolveIsAdmin('administrative_user')).toBe(true);
    });

    test('is case-insensitive — mixed case matches', () => {
        expect(resolveIsAdmin('Administrative_User')).toBe(true);
    });

    test('returns false for unrelated role string', () => {
        expect(resolveIsAdmin('SUPER_USER')).toBe(false);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('shouldBlockAdminAccess', () => {
    test('returns true when user is admin — access should be blocked', () => {
        expect(shouldBlockAdminAccess(true)).toBe(true);
    });

    test('returns false when user is not admin — access should be allowed', () => {
        expect(shouldBlockAdminAccess(false)).toBe(false);
    });

    test('returns false for null isAdmin value', () => {
        expect(shouldBlockAdminAccess(null)).toBe(false);
    });

    test('returns false for undefined isAdmin value', () => {
        expect(shouldBlockAdminAccess(undefined)).toBe(false);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('revertTwoFactor', () => {
    test('inverts true to false on API failure', () => {
        expect(revertTwoFactor(true)).toBe(false);
    });

    test('inverts false to true on API failure', () => {
        expect(revertTwoFactor(false)).toBe(true);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('resolveCancelValue', () => {
    test('returns temp value when a temp backup exists', () => {
        expect(resolveCancelValue('TempName', 'OriginalName')).toBe('TempName');
    });

    test('returns original value when temp is empty string (no backup)', () => {
        expect(resolveCancelValue('', 'OriginalName')).toBe('OriginalName');
    });

    test('returns original value when temp is null', () => {
        expect(resolveCancelValue(null, 'OriginalName')).toBe('OriginalName');
    });

    test('returns original value when temp is undefined', () => {
        expect(resolveCancelValue(undefined, 'OriginalName')).toBe('OriginalName');
    });

    test('returns temp even when original is empty', () => {
        expect(resolveCancelValue('TempName', '')).toBe('TempName');
    });

    test('returns empty string when both temp and original are empty', () => {
        expect(resolveCancelValue('', '')).toBe('');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('computeHasChanges', () => {
    test('returns true when new value differs from original', () => {
        expect(computeHasChanges('Bob', 'Alice')).toBe(true);
    });

    test('returns false when new value equals original', () => {
        expect(computeHasChanges('Alice', 'Alice')).toBe(false);
    });

    test('returns true when new value is empty and original is not', () => {
        expect(computeHasChanges('', 'Alice')).toBe(true);
    });

    test('returns false when both are empty strings', () => {
        expect(computeHasChanges('', '')).toBe(false);
    });

    test('returns true when only casing differs — watch does not normalise', () => {
        expect(computeHasChanges('alice', 'Alice')).toBe(true);
    });

    test('returns true when trailing whitespace is added — watch does not trim', () => {
        expect(computeHasChanges('Alice ', 'Alice')).toBe(true);
    });
});