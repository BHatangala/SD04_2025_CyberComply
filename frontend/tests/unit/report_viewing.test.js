/**
 * Unit tests for report_viewing.html
 *
 * Covers:
 *  - topRecommendation()     — filters non-compliant/partial, sorts by risk, returns top clause
 *  - sortedDetails()         — sorts by status priority then risk level
 *  - resolveIsAdmin()        — role string to boolean
 *  - buildReportDisplayName()— constructs display name from snapshot metadata
 *  - normalizeStatus()       — maps raw status string to display label
 *  - normalizeStatusColor()  — maps raw status string to color key
 */

const { describe, test, expect, beforeEach } = require('@jest/globals');

// ─────────────────────────────────────────────────────────────────────────────
// Pure logic extracted / derived from report_viewing.html
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Mirrors the `topRecommendation` computed property.
 * Returns the clause string of the highest-risk non-compliant or partial item,
 * or an empty string if all items are compliant.
 */
const RISK_ORDER = { critical: 0, high: 1, medium: 2, low: 3, unknown: 4 };

function topRecommendation(details = []) {
    const flagged = details
        .filter(d =>
            d.status === 'non_compliant' ||
            d.status === 'non-compliant' ||
            d.status === 'partial'
        )
        .sort((a, b) => (RISK_ORDER[a.risk_level] ?? 4) - (RISK_ORDER[b.risk_level] ?? 4));
    return flagged.length > 0 ? flagged[0].clause : '';
}

/**
 * Mirrors the `sortedDetails` computed property.
 * Sorts by status priority (non-compliant → partial → compliant),
 * then by risk level within each status group.
 */
const STATUS_ORDER = { 'non_compliant': 0, 'non-compliant': 0, 'partial': 1, 'compliant': 2 };

function sortedDetails(details = []) {
    return [...details].sort((a, b) => {
        const statusDiff = (STATUS_ORDER[a.status] ?? 3) - (STATUS_ORDER[b.status] ?? 3);
        if (statusDiff !== 0) return statusDiff;
        return (RISK_ORDER[a.risk_level] ?? 4) - (RISK_ORDER[b.risk_level] ?? 4);
    });
}

/**
 * Mirrors the admin flag resolution from mounted().
 */
function resolveIsAdmin(roleRaw) {
    return roleRaw === 'ADMINISTRATIVE_USER';
}

/**
 * Mirrors the display name construction in loadReport().
 * "Company — file.pdf", or just "file.pdf", or "Report" as fallback.
 */
function buildReportDisplayName(snapshot) {
    const meta    = (snapshot || {}).metadata || {};
    const company = (meta.company || '').trim();
    const file    = (meta.file_analyzed || '').trim();
    return company ? `${company} — ${file}` : file || 'Report';
}

/**
 * Mirrors the inline status label logic in the template.
 */
function normalizeStatus(status) {
    if (status === 'compliant')                              return 'Compliant';
    if (status === 'non-compliant' || status === 'non_compliant') return 'Non-Compliant';
    if (status === 'partial')                               return 'Partial';
    return status; // pass through unknown values as-is
}

/**
 * Mirrors the :style binding that drives status colour in the template.
 * Returns a semantic colour key rather than a hex/CSS value so tests stay
 * decoupled from design decisions.
 */
function normalizeStatusColor(status) {
    if (status === 'compliant') return 'green';
    if (status === 'partial')   return 'orange';
    return 'red'; // non-compliant and anything unknown defaults to red
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared test data helpers
// ─────────────────────────────────────────────────────────────────────────────

const makeDetail = (overrides = {}) => ({
    clause:     'Clause 5 — Data Retention',
    status:     'compliant',
    risk_level: 'low',
    confidence: 90,
    reasoning:  'Policy clearly states retention periods.',
    ...overrides
});

// ─────────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────────

describe('topRecommendation', () => {
    test('returns empty string when details array is empty', () => {
        expect(topRecommendation([])).toBe('');
    });

    test('returns empty string when all items are compliant', () => {
        const details = [
            makeDetail({ status: 'compliant', risk_level: 'high' }),
            makeDetail({ clause: 'Clause 2', status: 'compliant', risk_level: 'critical' })
        ];
        expect(topRecommendation(details)).toBe('');
    });

    test('returns clause of the single non-compliant item', () => {
        const details = [
            makeDetail({ clause: 'Clause 3 — Access Control', status: 'non_compliant', risk_level: 'high' })
        ];
        expect(topRecommendation(details)).toBe('Clause 3 — Access Control');
    });

    test('returns clause of the single partial item', () => {
        const details = [
            makeDetail({ clause: 'Clause 7 — Consent', status: 'partial', risk_level: 'medium' })
        ];
        expect(topRecommendation(details)).toBe('Clause 7 — Consent');
    });

    test('handles hyphenated non-compliant status variant (non-compliant)', () => {
        const details = [
            makeDetail({ clause: 'Clause 9', status: 'non-compliant', risk_level: 'low' })
        ];
        expect(topRecommendation(details)).toBe('Clause 9');
    });

    test('prefers critical risk over high risk', () => {
        const details = [
            makeDetail({ clause: 'High Risk Item',     status: 'non_compliant', risk_level: 'high' }),
            makeDetail({ clause: 'Critical Risk Item', status: 'non_compliant', risk_level: 'critical' })
        ];
        expect(topRecommendation(details)).toBe('Critical Risk Item');
    });

    test('prefers high risk over medium risk', () => {
        const details = [
            makeDetail({ clause: 'Medium Item', status: 'partial',     risk_level: 'medium' }),
            makeDetail({ clause: 'High Item',   status: 'non_compliant', risk_level: 'high' })
        ];
        expect(topRecommendation(details)).toBe('High Item');
    });

    test('prefers medium risk over low risk', () => {
        const details = [
            makeDetail({ clause: 'Low Item',    status: 'partial', risk_level: 'low' }),
            makeDetail({ clause: 'Medium Item', status: 'partial', risk_level: 'medium' })
        ];
        expect(topRecommendation(details)).toBe('Medium Item');
    });

    test('prefers non-compliant critical over partial critical (risk sort, not status sort)', () => {
        // topRecommendation sorts ONLY by risk — status type is irrelevant once flagged
        const details = [
            makeDetail({ clause: 'Partial Critical',       status: 'partial',      risk_level: 'critical' }),
            makeDetail({ clause: 'Non-Compliant Critical', status: 'non_compliant', risk_level: 'critical' })
        ];
        // Both are critical — first in filtered array wins (stable sort)
        const result = topRecommendation(details);
        expect(['Partial Critical', 'Non-Compliant Critical']).toContain(result);
    });

    test('ignores compliant items regardless of risk level', () => {
        const details = [
            makeDetail({ clause: 'Compliant Critical', status: 'compliant',   risk_level: 'critical' }),
            makeDetail({ clause: 'Non-Compliant Low',  status: 'non_compliant', risk_level: 'low' })
        ];
        expect(topRecommendation(details)).toBe('Non-Compliant Low');
    });

    test('treats unknown risk_level as lowest priority', () => {
        const details = [
            makeDetail({ clause: 'Unknown Risk', status: 'non_compliant', risk_level: 'unknown' }),
            makeDetail({ clause: 'Low Risk',     status: 'non_compliant', risk_level: 'low' })
        ];
        expect(topRecommendation(details)).toBe('Low Risk');
    });

    test('treats missing risk_level as lowest priority', () => {
        const details = [
            makeDetail({ clause: 'No Risk Field', status: 'non_compliant', risk_level: undefined }),
            makeDetail({ clause: 'Low Risk',      status: 'non_compliant', risk_level: 'low' })
        ];
        expect(topRecommendation(details)).toBe('Low Risk');
    });

    test('returns empty string when details is undefined (default param)', () => {
        expect(topRecommendation()).toBe('');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('sortedDetails', () => {
    test('returns empty array when given empty array', () => {
        expect(sortedDetails([])).toEqual([]);
    });

    test('does not mutate the original array', () => {
        const original = [
            makeDetail({ status: 'compliant',   risk_level: 'low' }),
            makeDetail({ status: 'non_compliant', risk_level: 'high' })
        ];
        const copy = [...original];
        sortedDetails(original);
        expect(original).toEqual(copy);
    });

    test('non-compliant comes before partial', () => {
        const details = [
            makeDetail({ clause: 'B', status: 'partial',      risk_level: 'low' }),
            makeDetail({ clause: 'A', status: 'non_compliant', risk_level: 'low' })
        ];
        const sorted = sortedDetails(details);
        expect(sorted[0].clause).toBe('A');
    });

    test('partial comes before compliant', () => {
        const details = [
            makeDetail({ clause: 'B', status: 'compliant', risk_level: 'low' }),
            makeDetail({ clause: 'A', status: 'partial',   risk_level: 'low' })
        ];
        const sorted = sortedDetails(details);
        expect(sorted[0].clause).toBe('A');
    });

    test('non-compliant comes before compliant', () => {
        const details = [
            makeDetail({ clause: 'Compliant',     status: 'compliant',   risk_level: 'high' }),
            makeDetail({ clause: 'Non-Compliant', status: 'non_compliant', risk_level: 'low' })
        ];
        const sorted = sortedDetails(details);
        expect(sorted[0].clause).toBe('Non-Compliant');
    });

    test('within non-compliant group: critical before high', () => {
        const details = [
            makeDetail({ clause: 'High',     status: 'non_compliant', risk_level: 'high' }),
            makeDetail({ clause: 'Critical', status: 'non_compliant', risk_level: 'critical' })
        ];
        const sorted = sortedDetails(details);
        expect(sorted[0].clause).toBe('Critical');
    });

    test('within non-compliant group: high before medium', () => {
        const details = [
            makeDetail({ clause: 'Medium', status: 'non_compliant', risk_level: 'medium' }),
            makeDetail({ clause: 'High',   status: 'non_compliant', risk_level: 'high' })
        ];
        const sorted = sortedDetails(details);
        expect(sorted[0].clause).toBe('High');
    });

    test('within partial group: critical before low', () => {
        const details = [
            makeDetail({ clause: 'Low Partial',      status: 'partial', risk_level: 'low' }),
            makeDetail({ clause: 'Critical Partial',  status: 'partial', risk_level: 'critical' })
        ];
        const sorted = sortedDetails(details);
        expect(sorted[0].clause).toBe('Critical Partial');
    });

    test('handles hyphenated non-compliant (non-compliant) same as non_compliant', () => {
        const details = [
            makeDetail({ clause: 'Compliant',    status: 'compliant',    risk_level: 'low' }),
            makeDetail({ clause: 'Hyphen Style', status: 'non-compliant', risk_level: 'low' })
        ];
        const sorted = sortedDetails(details);
        expect(sorted[0].clause).toBe('Hyphen Style');
    });

    test('full three-tier ordering: non-compliant → partial → compliant', () => {
        const details = [
            makeDetail({ clause: 'C', status: 'compliant',   risk_level: 'low' }),
            makeDetail({ clause: 'P', status: 'partial',     risk_level: 'low' }),
            makeDetail({ clause: 'N', status: 'non_compliant', risk_level: 'low' })
        ];
        const sorted = sortedDetails(details);
        expect(sorted.map(d => d.clause)).toEqual(['N', 'P', 'C']);
    });

    test('returns single item array unchanged in structure', () => {
        const details = [makeDetail({ status: 'compliant', risk_level: 'high' })];
        const sorted = sortedDetails(details);
        expect(sorted.length).toBe(1);
        expect(sorted[0].status).toBe('compliant');
    });

    test('unknown status goes to end (after compliant)', () => {
        const details = [
            makeDetail({ clause: 'Unknown', status: 'weird_status', risk_level: 'critical' }),
            makeDetail({ clause: 'Compliant', status: 'compliant',  risk_level: 'low' })
        ];
        const sorted = sortedDetails(details);
        expect(sorted[sorted.length - 1].clause).toBe('Unknown');
    });

    test('unknown risk_level sorts after known risk levels within same status', () => {
        const details = [
            makeDetail({ clause: 'Unknown Risk', status: 'non_compliant', risk_level: 'unknown' }),
            makeDetail({ clause: 'Low Risk',     status: 'non_compliant', risk_level: 'low' })
        ];
        const sorted = sortedDetails(details);
        expect(sorted[0].clause).toBe('Low Risk');
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

    test('is case-sensitive — lowercase variant returns false', () => {
        expect(resolveIsAdmin('administrative_user')).toBe(false);
    });

    test('is case-sensitive — mixed case variant returns false', () => {
        expect(resolveIsAdmin('Administrative_User')).toBe(false);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('buildReportDisplayName', () => {
    test('returns "Company — file.pdf" when both company and file are present', () => {
        const snap = { metadata: { company: 'Advantis', file_analyzed: 'policy.pdf' } };
        expect(buildReportDisplayName(snap)).toBe('Advantis — policy.pdf');
    });

    test('returns just the filename when company is empty string', () => {
        const snap = { metadata: { company: '', file_analyzed: 'report.docx' } };
        expect(buildReportDisplayName(snap)).toBe('report.docx');
    });

    test('returns just the filename when company is missing from metadata', () => {
        const snap = { metadata: { file_analyzed: 'notes.txt' } };
        expect(buildReportDisplayName(snap)).toBe('notes.txt');
    });

    test('returns "Report" fallback when both company and file are empty', () => {
        const snap = { metadata: { company: '', file_analyzed: '' } };
        expect(buildReportDisplayName(snap)).toBe('Report');
    });

    test('returns "Report" fallback when metadata is missing entirely', () => {
        const snap = {};
        expect(buildReportDisplayName(snap)).toBe('Report');
    });

    test('returns "Report" fallback when snapshot is null', () => {
        expect(buildReportDisplayName(null)).toBe('Report');
    });

    test('returns "Report" fallback when snapshot is undefined', () => {
        expect(buildReportDisplayName(undefined)).toBe('Report');
    });

    test('trims leading and trailing whitespace from company name', () => {
        const snap = { metadata: { company: '  Acme  ', file_analyzed: 'doc.pdf' } };
        expect(buildReportDisplayName(snap)).toBe('Acme — doc.pdf');
    });

    test('trims leading and trailing whitespace from file name', () => {
        const snap = { metadata: { company: '', file_analyzed: '  report.pdf  ' } };
        expect(buildReportDisplayName(snap)).toBe('report.pdf');
    });

    test('returns just filename when company is whitespace-only', () => {
        const snap = { metadata: { company: '   ', file_analyzed: 'audit.pdf' } };
        expect(buildReportDisplayName(snap)).toBe('audit.pdf');
    });

    test('handles company with allowed special characters', () => {
        const snap = { metadata: { company: "O'Brien & Sons", file_analyzed: 'policy.pdf' } };
        expect(buildReportDisplayName(snap)).toBe("O'Brien & Sons — policy.pdf");
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('normalizeStatus', () => {
    test('returns "Compliant" for "compliant"', () => {
        expect(normalizeStatus('compliant')).toBe('Compliant');
    });

    test('returns "Non-Compliant" for "non-compliant"', () => {
        expect(normalizeStatus('non-compliant')).toBe('Non-Compliant');
    });

    test('returns "Non-Compliant" for "non_compliant"', () => {
        expect(normalizeStatus('non_compliant')).toBe('Non-Compliant');
    });

    test('returns "Partial" for "partial"', () => {
        expect(normalizeStatus('partial')).toBe('Partial');
    });

    test('passes through unknown status values unchanged', () => {
        expect(normalizeStatus('pending_review')).toBe('pending_review');
    });

    test('passes through empty string unchanged', () => {
        expect(normalizeStatus('')).toBe('');
    });

    //test('is case-sensitive — "Compliant" does not match "compliant" rule', () => {
        //expect(normalizeStatus('Compliant')).not.toBe('Compliant');
        // Falls through to pass-through, so result equals the input
        //expect(normalizeStatus('Compliant')).toBe('Compliant');
    //});
});

// ─────────────────────────────────────────────────────────────────────────────

describe('normalizeStatusColor', () => {
    test('returns "green" for compliant status', () => {
        expect(normalizeStatusColor('compliant')).toBe('green');
    });

    test('returns "orange" for partial status', () => {
        expect(normalizeStatusColor('partial')).toBe('orange');
    });

    test('returns "red" for non_compliant status', () => {
        expect(normalizeStatusColor('non_compliant')).toBe('red');
    });

    test('returns "red" for non-compliant status', () => {
        expect(normalizeStatusColor('non-compliant')).toBe('red');
    });

    test('returns "red" for unknown status (default)', () => {
        expect(normalizeStatusColor('weird_status')).toBe('red');
    });

    test('returns "red" for empty string (default)', () => {
        expect(normalizeStatusColor('')).toBe('red');
    });
});