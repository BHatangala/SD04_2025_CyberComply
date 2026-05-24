const { describe, test, expect } = require('@jest/globals');

// ─────────────────────────────────────────────────────────────────────────────
// Pure logic extracted from comparison.html
// ─────────────────────────────────────────────────────────────────────────────

function buildReferenceFromId(id) {
    const stripped = (id || '').replace(/^SL-PDPA-S/, '');
    const parts    = stripped.split('-');
    let ref = `Section ${parts[0]}`;
    if (parts[1]) ref += `(${parts[1]})`;
    return `${ref} of the Personal Data Protection Act No. 9 of 2022 (Sri Lanka)`;
}

function overallRiskLevel(complianceScore) {
    if (complianceScore >= 75) return 'Low';
    if (complianceScore >= 40) return 'Medium';
    return 'High';
}

function hasMultipleDepartments(departments) {
    if (departments && departments.length > 0) {
        return departments.length > 1;
    }
    return false;
}

function departmentRecommendations(allDetails) {
    return allDetails
        .filter(d => d.status === 'non_compliant' || d.status === 'partial')
        .map(d => ({
            requirementId: d.requirement_id,
            clauseTitle:   d.clause || d.requirement_id,
            reference:     buildReferenceFromId(d.requirement_id)
        }));
}

// ─────────────────────────────────────────────────────────────────────────────
// buildReferenceFromId()
// ─────────────────────────────────────────────────────────────────────────────

describe('buildReferenceFromId()', () => {

    test('builds a standard section+subsection reference', () => {
        const result = buildReferenceFromId('SL-PDPA-S6-1');
        expect(result).toBe('Section 6(1) of the Personal Data Protection Act No. 9 of 2022 (Sri Lanka)');
    });

    test('handles a larger section number', () => {
        const result = buildReferenceFromId('SL-PDPA-S23-1');
        expect(result).toBe('Section 23(1) of the Personal Data Protection Act No. 9 of 2022 (Sri Lanka)');
    });

    test('handles a subsection number greater than 1', () => {
        const result = buildReferenceFromId('SL-PDPA-S10-3');
        expect(result).toBe('Section 10(3) of the Personal Data Protection Act No. 9 of 2022 (Sri Lanka)');
    });

    test('handles ID without a subsection part', () => {
        const result = buildReferenceFromId('SL-PDPA-S5');
        expect(result).toBe('Section 5 of the Personal Data Protection Act No. 9 of 2022 (Sri Lanka)');
    });

    test('returns a fallback string for an empty id', () => {
        const result = buildReferenceFromId('');
        expect(result).toBe('Section  of the Personal Data Protection Act No. 9 of 2022 (Sri Lanka)');
    });

    test('returns a fallback string for a null id', () => {
        const result = buildReferenceFromId(null);
        expect(result).toBe('Section  of the Personal Data Protection Act No. 9 of 2022 (Sri Lanka)');
    });

    test('always ends with the correct Act citation', () => {
        const result = buildReferenceFromId('SL-PDPA-S12-2');
        expect(result).toMatch(/of the Personal Data Protection Act No\. 9 of 2022 \(Sri Lanka\)$/);
    });

    test('always starts with "Section"', () => {
        const result = buildReferenceFromId('SL-PDPA-S7-1');
        expect(result).toMatch(/^Section /);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// overallRiskLevel()
// ─────────────────────────────────────────────────────────────────────────────

describe('overallRiskLevel()', () => {

    test('score of 75 returns Low', () => {
        expect(overallRiskLevel(75)).toBe('Low');
    });

    test('score of 100 returns Low', () => {
        expect(overallRiskLevel(100)).toBe('Low');
    });

    test('score of 76 returns Low', () => {
        expect(overallRiskLevel(76)).toBe('Low');
    });

    test('score of 74 returns Medium', () => {
        expect(overallRiskLevel(74)).toBe('Medium');
    });

    test('score of 40 returns Medium', () => {
        expect(overallRiskLevel(40)).toBe('Medium');
    });

    test('score of 55 returns Medium', () => {
        expect(overallRiskLevel(55)).toBe('Medium');
    });

    test('score of 39 returns High', () => {
        expect(overallRiskLevel(39)).toBe('High');
    });

    test('score of 0 returns High', () => {
        expect(overallRiskLevel(0)).toBe('High');
    });

    test('score of 1 returns High', () => {
        expect(overallRiskLevel(1)).toBe('High');
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// hasMultipleDepartments()
// ─────────────────────────────────────────────────────────────────────────────

describe('hasMultipleDepartments()', () => {

    test('returns false for an empty array', () => {
        expect(hasMultipleDepartments([])).toBe(false);
    });

    test('returns false for null', () => {
        expect(hasMultipleDepartments(null)).toBe(false);
    });

    test('returns false for undefined', () => {
        expect(hasMultipleDepartments(undefined)).toBe(false);
    });

    test('returns false when only one department exists', () => {
        expect(hasMultipleDepartments(['IT'])).toBe(false);
    });

    test('returns true when two departments exist', () => {
        expect(hasMultipleDepartments(['IT', 'HR'])).toBe(true);
    });

    test('returns true when three or more departments exist', () => {
        expect(hasMultipleDepartments(['IT', 'HR', 'Finance'])).toBe(true);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// departmentRecommendations()
// ─────────────────────────────────────────────────────────────────────────────

describe('departmentRecommendations()', () => {

    const sampleDetails = [
        { requirement_id: 'SL-PDPA-S6-1',  status: 'non_compliant', risk_level: 'high',   clause: 'Purpose limitation' },
        { requirement_id: 'SL-PDPA-S7-1',  status: 'non_compliant', risk_level: 'critical', clause: 'Lawful basis' },
        { requirement_id: 'SL-PDPA-S10-1', status: 'partial',       risk_level: 'medium',  clause: 'Data retention' },
        { requirement_id: 'SL-PDPA-S12-1', status: 'compliant',     risk_level: 'low',     clause: 'Subject rights' },
    ];

    test('includes non_compliant items', () => {
        const result = departmentRecommendations(sampleDetails);
        const ids = result.map(r => r.requirementId);
        expect(ids).toContain('SL-PDPA-S6-1');
        expect(ids).toContain('SL-PDPA-S7-1');
    });

    test('includes partial items', () => {
        const result = departmentRecommendations(sampleDetails);
        const ids = result.map(r => r.requirementId);
        expect(ids).toContain('SL-PDPA-S10-1');
    });

    test('excludes compliant items', () => {
        const result = departmentRecommendations(sampleDetails);
        const ids = result.map(r => r.requirementId);
        expect(ids).not.toContain('SL-PDPA-S12-1');
    });

    test('returns 3 recommendations from sample data (2 non_compliant + 1 partial)', () => {
        const result = departmentRecommendations(sampleDetails);
        expect(result).toHaveLength(3);
    });

    test('uses clause field as clauseTitle when present', () => {
        const result = departmentRecommendations(sampleDetails);
        const purposeItem = result.find(r => r.requirementId === 'SL-PDPA-S6-1');
        expect(purposeItem.clauseTitle).toBe('Purpose limitation');
    });

    test('falls back to requirement_id as clauseTitle when clause is missing', () => {
        const detailsWithoutClause = [
            { requirement_id: 'SL-PDPA-S9-1', status: 'non_compliant', risk_level: 'high' }
        ];
        const result = departmentRecommendations(detailsWithoutClause);
        expect(result[0].clauseTitle).toBe('SL-PDPA-S9-1');
    });

    test('builds the correct PDPA reference string for each item', () => {
        const result = departmentRecommendations(sampleDetails);
        const purposeItem = result.find(r => r.requirementId === 'SL-PDPA-S6-1');
        expect(purposeItem.reference).toBe(
            'Section 6(1) of the Personal Data Protection Act No. 9 of 2022 (Sri Lanka)'
        );
    });

    test('each recommendation has requirementId, clauseTitle, and reference fields', () => {
        const result = departmentRecommendations(sampleDetails);
        result.forEach(rec => {
            expect(rec).toHaveProperty('requirementId');
            expect(rec).toHaveProperty('clauseTitle');
            expect(rec).toHaveProperty('reference');
        });
    });

    test('returns an empty array when all details are compliant', () => {
        const allCompliant = [
            { requirement_id: 'SL-PDPA-S1-1', status: 'compliant', clause: 'Data collection' },
            { requirement_id: 'SL-PDPA-S2-1', status: 'compliant', clause: 'Consent' },
        ];
        const result = departmentRecommendations(allCompliant);
        expect(result).toHaveLength(0);
    });

    test('returns an empty array when allDetails is empty', () => {
        const result = departmentRecommendations([]);
        expect(result).toHaveLength(0);
    });

    test('reference uses correct section number from requirement_id', () => {
        const details = [
            { requirement_id: 'SL-PDPA-S23-1', status: 'non_compliant', clause: 'Breach notification' }
        ];
        const result = departmentRecommendations(details);
        expect(result[0].reference).toContain('Section 23(1)');
    });
});
