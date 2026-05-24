/**
 * Unit tests for signup.html
 *
 * Covers:
 *  - validateEmail()           — valid/invalid formats
 *  - validateFullName()        — all validation rules and edge cases
 *  - passwordChecks computed   — length, uppercase, digit, special character rules
 *  - allPasswordRulesValid     — all rules satisfied gate
 *  - passwordMatch computed    — both fields match, mismatch, empty cases
 *  - submitForm validation     — field-level error production for each field
 *  - acceptTermsFromModal()    — gate on termsScrolledToBottom
 *  - handleTermsScroll()       — sets termsScrolledToBottom when bottom reached
 *  - resolveBackendError()     — HTTP status → correct error field and message
 */

const { describe, test, expect } = require('@jest/globals');

// ─────────────────────────────────────────────────────────────────────────────
// Pure logic extracted from signup.html
// ─────────────────────────────────────────────────────────────────────────────

function validateEmail(email) {
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return regex.test(email);
}

function validateFullName(name) {
    const trimmed = name.trim();
    const normalized = trimmed.replace(/\s+/g, ' ');
    const regex = /^[A-Za-z'-]+(?:\s[A-Za-z'-]+)+$/;

    if (!trimmed) {
        return "Full name is required.";
    }

    if (normalized.length < 3) {
        return "Please enter your full name (first and last name).";
    }

    if (!regex.test(normalized)) {
        return "Please enter your full name (first and last name).";
    }

    const parts = normalized.split(' ');
    if (parts.some(part => part.length < 2)) {
        return "Please enter your full name (first and last name).";
    }

    return null;
}

function passwordChecks(password) {
    const p = password || "";
    return {
        length:    p.length >= 8,
        uppercase: /[A-Z]/.test(p),
        digit:     /\d/.test(p),
        special:   /[!@#$%^&*(),.?":{}|<>_\-\\[\]\/`~+=;']/.test(p)
    };
}

function allPasswordRulesValid(password) {
    const c = passwordChecks(password);
    return c.length && c.uppercase && c.digit && c.special;
}

function passwordMatch(password, confirmPassword) {
    return (
        password.length > 0 &&
        confirmPassword.length > 0 &&
        password === confirmPassword
    );
}

/**
 * Mirrors submitForm() client-side validation — returns errors object.
 * Does not perform the actual fetch (side-effectful).
 */
function validateSignupForm({ name, email, password, confirmPassword, role, termsRead, termsAccepted }) {
    const errors = {};
    const trimmedEmail = (email || '').trim().toLowerCase();

    const nameError = validateFullName(name || '');
    if (nameError) {
        errors.name = nameError;
    }

    if (!validateEmail(trimmedEmail)) {
        errors.email = "Please enter a valid email address.";
    }

    if (!password) {
        errors.password = "Password is required.";
    } else {
        const checks = passwordChecks(password);
        if (!checks.length || !checks.uppercase || !checks.digit || !checks.special) {
            errors.password =
                "Password must contain at least 8 characters with a minimum of 1 uppercase letter, 1 digit and 1 special character.";
        }
    }

    if (!confirmPassword) {
        errors.confirmPassword = "Please confirm your password.";
    } else if (password !== confirmPassword) {
        errors.confirmPassword = "Passwords do not match.";
    }

    if (!role) {
        errors.role = "Please select a role.";
    }

    if (!termsRead) {
        errors.terms = "Please open and read the Terms & Conditions before continuing.";
    } else if (!termsAccepted) {
        errors.terms = "You must accept the Terms & Conditions.";
    }

    return errors;
}

/**
 * Mirrors backend error handling in submitForm() — maps HTTP status + detail
 * to { field, message }.
 */
function resolveBackendError(status, detail) {
    if (status === 409) {
        return { field: 'email', message: "This email is already registered. Please use a different email." };
    }
    if (status === 400) {
        const d = (detail || '').toLowerCase();
        if (d.includes('name'))     return { field: 'name',     message: detail };
        if (d.includes('email'))    return { field: 'email',    message: detail };
        if (d.includes('password')) return { field: 'password', message: detail };
        if (d.includes('role'))     return { field: 'role',     message: detail };
        return { field: 'email', message: detail || "Signup failed. Please try again." };
    }
    if (status === 500) {
        return { field: 'email', message: detail || "Signup failed. Please try again." };
    }
    return { field: 'email', message: "Signup failed. Please try again." };
}

/**
 * Mirrors handleTermsScroll() — returns true if the scroll position has
 * reached the bottom within the given threshold.
 */
function hasReachedTermsBottom({ scrollTop, clientHeight, scrollHeight, threshold = 10 }) {
    return scrollTop + clientHeight >= scrollHeight - threshold;
}

/**
 * Mirrors acceptTermsFromModal() state transition.
 */
function acceptTermsFromModal(state) {
    if (!state.termsScrolledToBottom) return { ...state };
    return {
        ...state,
        termsRead:  true,
        termsAccepted: true,
        showTerms:  false
    };
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared test data
// ─────────────────────────────────────────────────────────────────────────────

const validForm = () => ({
    name:            'Jane Doe',
    email:           'jane@example.com',
    password:        'Secure@1',
    confirmPassword: 'Secure@1',
    role:            'GENERAL_USER',
    termsRead:       true,
    termsAccepted:   true
});

// ─────────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────────

describe('validateEmail', () => {
    test('returns true for a standard valid email', () => {
        expect(validateEmail('user@example.com')).toBe(true);
    });

    test('returns true for email with subdomain', () => {
        expect(validateEmail('user@mail.example.com')).toBe(true);
    });

    test('returns true for email with plus addressing', () => {
        expect(validateEmail('user+tag@example.com')).toBe(true);
    });

    test('returns false for email missing @', () => {
        expect(validateEmail('userexample.com')).toBe(false);
    });

    test('returns false for email missing domain', () => {
        expect(validateEmail('user@')).toBe(false);
    });

    test('returns false for email missing TLD', () => {
        expect(validateEmail('user@example')).toBe(false);
    });

    test('returns false for empty string', () => {
        expect(validateEmail('')).toBe(false);
    });

    test('returns false for email with spaces', () => {
        expect(validateEmail('user @example.com')).toBe(false);
    });

    test('returns false for email with double @', () => {
        expect(validateEmail('user@@example.com')).toBe(false);
    });

    test('returns true for numeric local part', () => {
        expect(validateEmail('123@example.com')).toBe(true);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('validateFullName', () => {
    test('returns null for a valid first and last name', () => {
        expect(validateFullName('Jane Doe')).toBeNull();
    });

    test('returns null for three-part name', () => {
        expect(validateFullName('Mary Anne Smith')).toBeNull();
    });

    test('returns null for hyphenated last name', () => {
        expect(validateFullName('Jane Smith-Jones')).toBeNull();
    });

    test('returns null for name with apostrophe', () => {
        expect(validateFullName("O'Brien James")).toBeNull();
    });

    test('returns error for empty string', () => {
        expect(validateFullName('')).toBe("Full name is required.");
    });

    test('returns error for whitespace-only string', () => {
        expect(validateFullName('   ')).toBe("Full name is required.");
    });

    test('returns error for a single word', () => {
        expect(validateFullName('Jane')).toContain('full name');
    });

    test('returns error when combined length is less than 3 characters', () => {
        expect(validateFullName('A B')).toContain('full name');
    });

    test('returns error when any part is a single character', () => {
        expect(validateFullName('Jane D')).toContain('full name');
    });

    test('returns error for name with numbers', () => {
        expect(validateFullName('Jane Doe2')).toContain('full name');
    });

    test('returns error for name with special characters other than hyphen/apostrophe', () => {
        expect(validateFullName('Jane Doe!')).toContain('full name');
    });

    test('trims leading and trailing whitespace before validating', () => {
        expect(validateFullName('  Jane Doe  ')).toBeNull();
    });

    test('normalises multiple spaces between words', () => {
        expect(validateFullName('Jane   Doe')).toBeNull();
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('passwordChecks', () => {
    test('all checks true for a fully valid password', () => {
        const c = passwordChecks('Secure@1');
        expect(c.length).toBe(true);
        expect(c.uppercase).toBe(true);
        expect(c.digit).toBe(true);
        expect(c.special).toBe(true);
    });

    test('length is false for password shorter than 8 chars', () => {
        expect(passwordChecks('Ab@1').length).toBe(false);
    });

    test('length is true for password exactly 8 chars', () => {
        expect(passwordChecks('Abcde@1x').length).toBe(true);
    });

    test('uppercase is false when no uppercase letter present', () => {
        expect(passwordChecks('secure@1').uppercase).toBe(false);
    });

    test('uppercase is true when at least one uppercase letter present', () => {
        expect(passwordChecks('Secure@1').uppercase).toBe(true);
    });

    test('digit is false when no digit present', () => {
        expect(passwordChecks('Secure@@').digit).toBe(false);
    });

    test('digit is true when at least one digit present', () => {
        expect(passwordChecks('Secure@1').digit).toBe(true);
    });

    test('special is false when no special character present', () => {
        expect(passwordChecks('Secure11').special).toBe(false);
    });

    test('special is true for each supported special character sample', () => {
        const specials = ['!', '@', '#', '$', '%', '^', '&', '*', '_', '-'];
        specials.forEach(char => {
            expect(passwordChecks(`Secure1${char}`).special).toBe(true);
        });
    });

    test('all checks false for empty string', () => {
        const c = passwordChecks('');
        expect(c.length).toBe(false);
        expect(c.uppercase).toBe(false);
        expect(c.digit).toBe(false);
        expect(c.special).toBe(false);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('allPasswordRulesValid', () => {
    test('returns true for a fully valid password', () => {
        expect(allPasswordRulesValid('Secure@1')).toBe(true);
    });

    test('returns false when password is too short', () => {
        expect(allPasswordRulesValid('Se@1')).toBe(false);
    });

    test('returns false when uppercase is missing', () => {
        expect(allPasswordRulesValid('secure@1')).toBe(false);
    });

    test('returns false when digit is missing', () => {
        expect(allPasswordRulesValid('Secure@@')).toBe(false);
    });

    test('returns false when special character is missing', () => {
        expect(allPasswordRulesValid('Secure11')).toBe(false);
    });

    test('returns false for empty string', () => {
        expect(allPasswordRulesValid('')).toBe(false);
    });

    test('returns true for a long complex password', () => {
        expect(allPasswordRulesValid('MyP@ssw0rd!IsVeryLong')).toBe(true);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('passwordMatch', () => {
    test('returns true when both fields are identical and non-empty', () => {
        expect(passwordMatch('Secure@1', 'Secure@1')).toBe(true);
    });

    test('returns false when passwords differ', () => {
        expect(passwordMatch('Secure@1', 'Secure@2')).toBe(false);
    });

    test('returns false when password is empty', () => {
        expect(passwordMatch('', 'Secure@1')).toBe(false);
    });

    test('returns false when confirmPassword is empty', () => {
        expect(passwordMatch('Secure@1', '')).toBe(false);
    });

    test('returns false when both are empty', () => {
        expect(passwordMatch('', '')).toBe(false);
    });

    test('is case-sensitive', () => {
        expect(passwordMatch('secure@1', 'Secure@1')).toBe(false);
    });

    test('returns false when trailing whitespace causes mismatch', () => {
        expect(passwordMatch('Secure@1', 'Secure@1 ')).toBe(false);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('validateSignupForm', () => {
    test('returns no errors for a fully valid form', () => {
        const errors = validateSignupForm(validForm());
        expect(Object.keys(errors).length).toBe(0);
    });

    // name
    test('produces name error for empty name', () => {
        const errors = validateSignupForm({ ...validForm(), name: '' });
        expect(errors.name).toBe("Full name is required.");
    });

    test('produces name error for single-word name', () => {
        const errors = validateSignupForm({ ...validForm(), name: 'Jane' });
        expect(errors.name).toContain('full name');
    });

    // email
    test('produces email error for invalid email', () => {
        const errors = validateSignupForm({ ...validForm(), email: 'not-an-email' });
        expect(errors.email).toContain('valid email');
    });

    test('produces email error for empty email', () => {
        const errors = validateSignupForm({ ...validForm(), email: '' });
        expect(errors.email).toContain('valid email');
    });

    test('trims and lowercases email before validating', () => {
        const errors = validateSignupForm({ ...validForm(), email: '  Jane@Example.COM  ' });
        expect(errors.email).toBeUndefined();
    });

    // password
    test('produces password error for empty password', () => {
        const errors = validateSignupForm({ ...validForm(), password: '', confirmPassword: '' });
        expect(errors.password).toBe("Password is required.");
    });

    test('produces password error for password missing uppercase', () => {
        const errors = validateSignupForm({ ...validForm(), password: 'secure@1', confirmPassword: 'secure@1' });
        expect(errors.password).toContain('uppercase');
    });

    test('produces password error for password missing digit', () => {
        const errors = validateSignupForm({ ...validForm(), password: 'Secure@@', confirmPassword: 'Secure@@' });
        expect(errors.password).toContain('digit');
    });

    test('produces password error for password missing special character', () => {
        const errors = validateSignupForm({ ...validForm(), password: 'Secure11', confirmPassword: 'Secure11' });
        expect(errors.password).toContain('special character');
    });

    test('produces password error for password shorter than 8 characters', () => {
        const errors = validateSignupForm({ ...validForm(), password: 'Se@1', confirmPassword: 'Se@1' });
        expect(errors.password).toContain('8 characters');
    });

    // confirmPassword
    test('produces confirmPassword error when field is empty', () => {
        const errors = validateSignupForm({ ...validForm(), confirmPassword: '' });
        expect(errors.confirmPassword).toContain('confirm');
    });

    test('produces confirmPassword error when passwords do not match', () => {
        const errors = validateSignupForm({ ...validForm(), confirmPassword: 'Different@1' });
        expect(errors.confirmPassword).toContain('do not match');
    });

    test('no confirmPassword error when passwords match', () => {
        const errors = validateSignupForm(validForm());
        expect(errors.confirmPassword).toBeUndefined();
    });

    // role
    test('produces role error when no role selected', () => {
        const errors = validateSignupForm({ ...validForm(), role: '' });
        expect(errors.role).toContain('role');
    });

    test('no role error when role is provided', () => {
        const errors = validateSignupForm(validForm());
        expect(errors.role).toBeUndefined();
    });

    // terms
    test('produces terms error when termsRead is false', () => {
        const errors = validateSignupForm({ ...validForm(), termsRead: false, termsAccepted: false });
        expect(errors.terms).toContain('open and read');
    });

    test('produces terms error when termsRead but not accepted', () => {
        const errors = validateSignupForm({ ...validForm(), termsRead: true, termsAccepted: false });
        expect(errors.terms).toContain('accept');
    });

    test('no terms error when termsRead and termsAccepted are both true', () => {
        const errors = validateSignupForm(validForm());
        expect(errors.terms).toBeUndefined();
    });

    // multiple errors at once
    test('accumulates errors for multiple invalid fields', () => {
        const errors = validateSignupForm({
            name: '',
            email: 'bad',
            password: '',
            confirmPassword: '',
            role: '',
            termsRead: false,
            termsAccepted: false
        });
        expect(Object.keys(errors).length).toBeGreaterThanOrEqual(4);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('resolveBackendError', () => {
    test('maps 409 to email field with already-registered message', () => {
        const result = resolveBackendError(409, '');
        expect(result.field).toBe('email');
        expect(result.message).toContain('already registered');
    });

    test('maps 400 with name detail to name field', () => {
        const result = resolveBackendError(400, 'Invalid name provided.');
        expect(result.field).toBe('name');
        expect(result.message).toBe('Invalid name provided.');
    });

    test('maps 400 with email detail to email field', () => {
        const result = resolveBackendError(400, 'Email is not allowed.');
        expect(result.field).toBe('email');
        expect(result.message).toBe('Email is not allowed.');
    });

    test('maps 400 with password detail to password field', () => {
        const result = resolveBackendError(400, 'Password too weak.');
        expect(result.field).toBe('password');
        expect(result.message).toBe('Password too weak.');
    });

    test('maps 400 with role detail to role field', () => {
        const result = resolveBackendError(400, 'Invalid role specified.');
        expect(result.field).toBe('role');
        expect(result.message).toBe('Invalid role specified.');
    });

    test('maps 400 with unrecognised detail to email field with detail message', () => {
        const result = resolveBackendError(400, 'Something went wrong.');
        expect(result.field).toBe('email');
        expect(result.message).toBe('Something went wrong.');
    });

    test('maps 400 with null detail to fallback message', () => {
        const result = resolveBackendError(400, null);
        expect(result.field).toBe('email');
        expect(result.message).toContain('Signup failed');
    });

    test('maps 500 to email field with detail message', () => {
        const result = resolveBackendError(500, 'Internal server error.');
        expect(result.field).toBe('email');
        expect(result.message).toBe('Internal server error.');
    });

    test('maps 500 with null detail to fallback message', () => {
        const result = resolveBackendError(500, null);
        expect(result.field).toBe('email');
        expect(result.message).toContain('Signup failed');
    });

    test('maps unknown status to generic email error', () => {
        const result = resolveBackendError(503, 'Service unavailable.');
        expect(result.field).toBe('email');
        expect(result.message).toContain('Signup failed');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('hasReachedTermsBottom', () => {
    test('returns true when scrolled to exact bottom', () => {
        expect(hasReachedTermsBottom({ scrollTop: 900, clientHeight: 100, scrollHeight: 1000 })).toBe(true);
    });

    test('returns true when within threshold of bottom', () => {
        expect(hasReachedTermsBottom({ scrollTop: 895, clientHeight: 100, scrollHeight: 1000 })).toBe(true);
    });

    test('returns false when not yet scrolled to bottom', () => {
        expect(hasReachedTermsBottom({ scrollTop: 500, clientHeight: 100, scrollHeight: 1000 })).toBe(false);
    });

    test('returns false when at top of a tall document', () => {
        expect(hasReachedTermsBottom({ scrollTop: 0, clientHeight: 100, scrollHeight: 1000 })).toBe(false);
    });

    test('returns true when content fits in viewport (no scroll needed)', () => {
        expect(hasReachedTermsBottom({ scrollTop: 0, clientHeight: 500, scrollHeight: 500 })).toBe(true);
    });

    test('custom threshold is respected', () => {
        // 895 + 100 = 995 >= 1000 - 20 = 980 → true
        expect(hasReachedTermsBottom({ scrollTop: 895, clientHeight: 100, scrollHeight: 1000, threshold: 20 })).toBe(true);
    });

    test('returns false just above threshold with strict boundary', () => {
        // 880 + 100 = 980 >= 1000 - 10 = 990 → false
        expect(hasReachedTermsBottom({ scrollTop: 880, clientHeight: 100, scrollHeight: 1000 })).toBe(false);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('acceptTermsFromModal', () => {
    const baseState = () => ({
        termsScrolledToBottom: false,
        termsRead:             false,
        termsAccepted:         false,
        showTerms:             true
    });

    test('does not change state when termsScrolledToBottom is false', () => {
        const state = baseState();
        const result = acceptTermsFromModal(state);
        expect(result.termsRead).toBe(false);
        expect(result.termsAccepted).toBe(false);
        expect(result.showTerms).toBe(true);
    });

    test('sets termsRead to true when termsScrolledToBottom is true', () => {
        const state = { ...baseState(), termsScrolledToBottom: true };
        const result = acceptTermsFromModal(state);
        expect(result.termsRead).toBe(true);
    });

    test('sets termsAccepted to true when termsScrolledToBottom is true', () => {
        const state = { ...baseState(), termsScrolledToBottom: true };
        const result = acceptTermsFromModal(state);
        expect(result.termsAccepted).toBe(true);
    });

    test('closes the terms modal when accepted', () => {
        const state = { ...baseState(), termsScrolledToBottom: true };
        const result = acceptTermsFromModal(state);
        expect(result.showTerms).toBe(false);
    });

    test('does not mutate original state object', () => {
        const state = { ...baseState(), termsScrolledToBottom: true };
        acceptTermsFromModal(state);
        expect(state.termsRead).toBe(false);
    });

    test('calling twice when scrolled produces same accepted state', () => {
        const state = { ...baseState(), termsScrolledToBottom: true };
        const first  = acceptTermsFromModal(state);
        const second = acceptTermsFromModal(first);
        expect(second.termsRead).toBe(true);
        expect(second.showTerms).toBe(false);
    });
});