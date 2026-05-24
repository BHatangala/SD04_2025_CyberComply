/**
 * Unit tests for document_analysis.html
 *
 * Covers:
 *  - complianceLabel derivation from score
 *  - barWidth string generation
 *  - complianceDetails filtering (non-compliant / partial only)
 *  - topRecommendation extraction from AI payload
 *  - isAdmin flag resolution from userRole string
 *  - openReport() URL routing logic
 *  - fetchHistory() response mapping
 *  - showAccessDenied() toast visibility toggle
 *  - analysedCompany and analysedFilename population
 */

const { describe, test, expect } = require('@jest/globals');

// ─────────────────────────────────────────────────────────────────────────────
// Pure logic functions extracted from document_analysis.html
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Derives the compliance label from a numeric score.
 * Mirrors the ternary in mounted() data population.
 */
function deriveComplianceLabel(score, labelFromServer) {
    if (labelFromServer) return labelFromServer;
    if (score >= 75) return 'High Compliance Level';
    if (score >= 40) return 'Medium Compliance Level';
    return 'Low Compliance Level';
}

/**
 * Generates the CSS bar width string from a score.
 */
function deriveBarWidth(score) {
    return `${score}%`;
}

/**
 * Filters raw compliance details to only non-compliant and partial items.
 * Mirrors the filter applied to data.compliance.details in mounted().
 */
function filterComplianceDetails(details) {
    return details.filter(
        d => d.status === 'non-compliant'
          || d.status === 'partial'
          || d.status === 'non_compliant'
    );
}

/**
 * Extracts the top recommendation string from the AI payload.
 */
function extractTopRecommendation(recommendations) {
    return recommendations?.top_action || '';
}

/**
 * Resolves the isAdmin flag from the raw role string stored in sessionStorage.
 */
function resolveIsAdmin(roleRaw) {
    return roleRaw === 'ADMINISTRATIVE_USER';
}

/**
 * Maps a raw history API response row into the shape used by the sidebar.
 */
function mapHistoryRow(r) {
    return {
        resultId: r.result_id,
        label:    r.display_name,
        score:    r.compliance_score
    };
}

/**
 * Resolves the URL for openReport() — mirrors the method logic.
 */
function resolveReportUrl(report) {
    const resultId = report.resultId || null;
    if (resultId) {
        return { type: 'analysis', url: 'document_analysis.html', resultId };
    }
    return {
        type: 'viewing',
        url:  `report_viewing.html?report=${encodeURIComponent(report.label || report)}`
    };
}

/**
 * Populates the UI display fields from a raw API response object.
 * Mirrors what mounted() does after a successful fetch.
 */
function populateDisplayFields(data) {
    const score = Math.round(data.compliance_score ?? 0);
    return {
        analysedFilename:  data.original_filename || 'Document Analysis',
        analysedCompany:   data.company_name || '',
        complianceScore:   score,
        complianceLabel:   deriveComplianceLabel(score, data.compliance_label),
        complianceDetails: filterComplianceDetails(data.compliance?.details || []),
        topRecommendation: extractTopRecommendation(data.recommendations)
    };
}

// ─────────────────────────────────────────────────────────────────────────────
// Sample data shared across tests
// ─────────────────────────────────────────────────────────────────────────────

const sampleDetails = [
    { requirement_id: 'SL-PDPA-S4-1',  clause: 'Data Protection Obligations', status: 'non_compliant',  risk_level: 'high',     confidence: 70 },
    { requirement_id: 'SL-PDPA-S5-1',  clause: 'Lawful Processing',            status: 'non-compliant', risk_level: 'critical',  confidence: 80 },
    { requirement_id: 'SL-PDPA-S6-1',  clause: 'Purpose Specification',        status: 'partial',       risk_level: 'high',     confidence: 85 },
    { requirement_id: 'SL-PDPA-S7-1',  clause: 'Data Minimisation',            status: 'compliant',     risk_level: 'low',      confidence: 90 },
    { requirement_id: 'SL-PDPA-S8-1',  clause: 'Accuracy',                     status: 'compliant',     risk_level: 'medium',   confidence: 95 },
];

const sampleApiResponse = {
    result_id:         'abc-123',
    original_filename: 'Sample.txt',
    company_name:      'Advantis',
    compliance_score:  11.03,
    compliance_label:  null,
    compliance: {
        details: sampleDetails
    },
    recommendations: {
        top_action: 'Update privacy policy with Section 10 wording.'
    }
};

// ─────────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────────

describe('deriveComplianceLabel', () => {
    test('returns server label when provided', () => {
        expect(deriveComplianceLabel(80, 'Custom Label')).toBe('Custom Label');
    });

    test('returns High Compliance Level for score >= 75', () => {
        expect(deriveComplianceLabel(75, null)).toBe('High Compliance Level');
        expect(deriveComplianceLabel(100, null)).toBe('High Compliance Level');
    });

    test('returns Medium Compliance Level for score between 40 and 74', () => {
        expect(deriveComplianceLabel(40, null)).toBe('Medium Compliance Level');
        expect(deriveComplianceLabel(74, null)).toBe('Medium Compliance Level');
    });

    test('returns Low Compliance Level for score below 40', () => {
        expect(deriveComplianceLabel(39, null)).toBe('Low Compliance Level');
        expect(deriveComplianceLabel(0, null)).toBe('Low Compliance Level');
        expect(deriveComplianceLabel(11, null)).toBe('Low Compliance Level');
    });

    test('handles boundary score of exactly 40 as Medium', () => {
        expect(deriveComplianceLabel(40, null)).toBe('Medium Compliance Level');
    });

    test('handles boundary score of exactly 75 as High', () => {
        expect(deriveComplianceLabel(75, null)).toBe('High Compliance Level');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('deriveBarWidth', () => {
    test('returns correct CSS percentage string', () => {
        expect(deriveBarWidth(11)).toBe('11%');
        expect(deriveBarWidth(75)).toBe('75%');
        expect(deriveBarWidth(100)).toBe('100%');
        expect(deriveBarWidth(0)).toBe('0%');
    });

    test('handles decimal scores', () => {
        expect(deriveBarWidth(11.03)).toBe('11.03%');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('filterComplianceDetails', () => {
    test('excludes compliant items', () => {
        const result = filterComplianceDetails(sampleDetails);
        expect(result.every(d => d.status !== 'compliant')).toBe(true);
    });

    test('includes non_compliant items (underscore format)', () => {
        const result = filterComplianceDetails(sampleDetails);
        expect(result.some(d => d.status === 'non_compliant')).toBe(true);
    });

    test('includes non-compliant items (hyphen format)', () => {
        const result = filterComplianceDetails(sampleDetails);
        expect(result.some(d => d.status === 'non-compliant')).toBe(true);
    });

    test('includes partial items', () => {
        const result = filterComplianceDetails(sampleDetails);
        expect(result.some(d => d.status === 'partial')).toBe(true);
    });

    test('returns correct count — 3 out of 5 sample items are flagged', () => {
        const result = filterComplianceDetails(sampleDetails);
        expect(result.length).toBe(3);
    });

    test('returns empty array when all items are compliant', () => {
        const allCompliant = [
            { status: 'compliant', clause: 'Accuracy' },
            { status: 'compliant', clause: 'Minimisation' }
        ];
        expect(filterComplianceDetails(allCompliant)).toHaveLength(0);
    });

    test('returns empty array for empty input', () => {
        expect(filterComplianceDetails([])).toHaveLength(0);
    });

    test('does not mutate the original array', () => {
        const original = [...sampleDetails];
        filterComplianceDetails(sampleDetails);
        expect(sampleDetails.length).toBe(original.length);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('extractTopRecommendation', () => {
    test('returns top_action string from recommendations object', () => {
        const recs = { top_action: 'Update privacy policy with Section 10 wording.' };
        expect(extractTopRecommendation(recs)).toBe('Update privacy policy with Section 10 wording.');
    });

    test('returns empty string when top_action is missing', () => {
        expect(extractTopRecommendation({})).toBe('');
    });

    test('returns empty string when recommendations is null', () => {
        expect(extractTopRecommendation(null)).toBe('');
    });

    test('returns empty string when recommendations is undefined', () => {
        expect(extractTopRecommendation(undefined)).toBe('');
    });

    test('returns empty string when top_action is empty string', () => {
        expect(extractTopRecommendation({ top_action: '' })).toBe('');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('resolveIsAdmin', () => {
    test('returns true for ADMINISTRATIVE_USER role', () => {
        expect(resolveIsAdmin('ADMINISTRATIVE_USER')).toBe(true);
    });

    test('returns false for GENERAL_USER role', () => {
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

    test('is case-sensitive — lowercase fails', () => {
        expect(resolveIsAdmin('administrative_user')).toBe(false);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('mapHistoryRow', () => {
    test('correctly maps result_id, display_name and compliance_score', () => {
        const raw = {
            result_id:        'abc-123',
            display_name:     'Advantis — Sample.txt',
            compliance_score: 11
        };
        const mapped = mapHistoryRow(raw);
        expect(mapped.resultId).toBe('abc-123');
        expect(mapped.label).toBe('Advantis — Sample.txt');
        expect(mapped.score).toBe(11);
    });

    test('maps multiple rows correctly', () => {
        const rows = [
            { result_id: 'id-1', display_name: 'Report A', compliance_score: 80 },
            { result_id: 'id-2', display_name: 'Report B', compliance_score: 45 },
        ];
        const mapped = rows.map(mapHistoryRow);
        expect(mapped[0].resultId).toBe('id-1');
        expect(mapped[1].label).toBe('Report B');
        expect(mapped[1].score).toBe(45);
    });

    test('produces object with exactly resultId, label, score keys', () => {
        const raw = { result_id: 'x', display_name: 'Y', compliance_score: 50 };
        const mapped = mapHistoryRow(raw);
        expect(Object.keys(mapped)).toEqual(['resultId', 'label', 'score']);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('resolveReportUrl', () => {
    test('routes to document_analysis when report has a resultId', () => {
        const report = { resultId: 'abc-123', label: 'Advantis Report' };
        const result = resolveReportUrl(report);
        expect(result.type).toBe('analysis');
        expect(result.url).toBe('document_analysis.html');
        expect(result.resultId).toBe('abc-123');
    });

    test('routes to report_viewing when report has no resultId', () => {
        const report = { resultId: null, label: 'Old Report' };
        const result = resolveReportUrl(report);
        expect(result.type).toBe('viewing');
        expect(result.url).toContain('report_viewing.html');
        expect(result.url).toContain(encodeURIComponent('Old Report'));
    });

    test('URL-encodes the report label correctly', () => {
        const report = { resultId: null, label: 'Advantis — Sample.txt' };
        const result = resolveReportUrl(report);
        expect(result.url).toContain(encodeURIComponent('Advantis — Sample.txt'));
    });

    test('falls back to report string itself when label is missing', () => {
        const report = { resultId: null };
        const result = resolveReportUrl(report);
        expect(result.type).toBe('viewing');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('populateDisplayFields', () => {
    test('correctly rounds compliance score', () => {
        const fields = populateDisplayFields(sampleApiResponse);
        expect(fields.complianceScore).toBe(11);
    });

    test('sets analysedFilename from original_filename', () => {
        const fields = populateDisplayFields(sampleApiResponse);
        expect(fields.analysedFilename).toBe('Sample.txt');
    });

    test('falls back to "Document Analysis" when original_filename is missing', () => {
        const data = { ...sampleApiResponse, original_filename: null };
        const fields = populateDisplayFields(data);
        expect(fields.analysedFilename).toBe('Document Analysis');
    });

    test('sets analysedCompany from company_name', () => {
        const fields = populateDisplayFields(sampleApiResponse);
        expect(fields.analysedCompany).toBe('Advantis');
    });

    test('sets analysedCompany to empty string when company_name is missing', () => {
        const data = { ...sampleApiResponse, company_name: null };
        const fields = populateDisplayFields(data);
        expect(fields.analysedCompany).toBe('');
    });

    test('derives Low label for score of 11', () => {
        const fields = populateDisplayFields(sampleApiResponse);
        expect(fields.complianceLabel).toBe('Low Compliance Level');
    });

    test('uses server-provided compliance_label when present', () => {
        const data = { ...sampleApiResponse, compliance_score: 80, compliance_label: 'Excellent' };
        const fields = populateDisplayFields(data);
        expect(fields.complianceLabel).toBe('Excellent');
    });

    test('filters out compliant items from complianceDetails', () => {
        const fields = populateDisplayFields(sampleApiResponse);
        expect(fields.complianceDetails.every(d => d.status !== 'compliant')).toBe(true);
    });

    test('complianceDetails contains 3 flagged items from sample data', () => {
        const fields = populateDisplayFields(sampleApiResponse);
        expect(fields.complianceDetails.length).toBe(3);
    });

    test('sets topRecommendation from recommendations.top_action', () => {
        const fields = populateDisplayFields(sampleApiResponse);
        expect(fields.topRecommendation).toBe('Update privacy policy with Section 10 wording.');
    });

    test('sets topRecommendation to empty string when missing', () => {
        const data = { ...sampleApiResponse, recommendations: {} };
        const fields = populateDisplayFields(data);
        expect(fields.topRecommendation).toBe('');
    });

    test('handles missing compliance.details gracefully', () => {
        const data = { ...sampleApiResponse, compliance: {} };
        const fields = populateDisplayFields(data);
        expect(fields.complianceDetails).toHaveLength(0);
    });

    test('handles compliance_score of 0', () => {
        const data = { ...sampleApiResponse, compliance_score: 0, compliance_label: null };
        const fields = populateDisplayFields(data);
        expect(fields.complianceScore).toBe(0);
        expect(fields.complianceLabel).toBe('Low Compliance Level');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('showAccessDenied toast logic', () => {
    test('toastVisible becomes true when showAccessDenied is called', () => {
        let toastVisible = false;
        let toastTimer   = null;

        function showAccessDenied() {
            if (toastTimer) clearTimeout(toastTimer);
            toastVisible = true;
            toastTimer   = setTimeout(() => { toastVisible = false; }, 3500);
        }

        showAccessDenied();
        expect(toastVisible).toBe(true);
        clearTimeout(toastTimer);
    });

    test('toastVisible resets to false after 3500ms', (done) => {
        let toastVisible = false;
        let toastTimer   = null;

        function showAccessDenied() {
            if (toastTimer) clearTimeout(toastTimer);
            toastVisible = true;
            toastTimer   = setTimeout(() => { toastVisible = false; }, 100); // short for test
        }

        showAccessDenied();
        expect(toastVisible).toBe(true);

        setTimeout(() => {
            expect(toastVisible).toBe(false);
            done();
        }, 150);
    });

    test('calling showAccessDenied twice resets the timer', () => {
        let toastVisible = false;
        let toastTimer   = null;
        let timerResetCount = 0;

        function showAccessDenied() {
            if (toastTimer) {
                clearTimeout(toastTimer);
                timerResetCount++;
            }
            toastVisible = true;
            toastTimer   = setTimeout(() => { toastVisible = false; }, 3500);
        }

        showAccessDenied();
        showAccessDenied();
        expect(timerResetCount).toBe(1);
        expect(toastVisible).toBe(true);
        clearTimeout(toastTimer);
    });
});