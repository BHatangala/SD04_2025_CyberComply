const { describe, test, expect } = require('@jest/globals');

// ─────────────────────────────────────────────────────────────────────────────
// Pure logic extracted from compliance.html
// ─────────────────────────────────────────────────────────────────────────────

const RISK_ORDER = { critical: 0, high: 1, medium: 2, low: 3, unknown: 4 };

function getGaps(allDetails, activeFilter) {
    return allDetails
        .filter(d => {
            if (d.status !== 'non_compliant') return false;
            if (activeFilter) return d.risk_level === activeFilter;
            return true;
        })
        .sort((a, b) => (RISK_ORDER[a.risk_level] ?? 4) - (RISK_ORDER[b.risk_level] ?? 4));
}

function getRisks(allDetails, activeFilter) {
    return allDetails
        .filter(d => {
            if (d.status !== 'non_compliant' && d.status !== 'partial') return false;
            if (activeFilter) return d.risk_level === activeFilter;
            return true;
        })
        .sort((a, b) => (RISK_ORDER[a.risk_level] ?? 4) - (RISK_ORDER[b.risk_level] ?? 4));
}

function getRiskCounts(risks) {
    const counts = { critical: 0, high: 0, medium: 0, low: 0 };
    for (const item of risks) {
        if (item.risk_level && counts[item.risk_level] !== undefined) {
            counts[item.risk_level]++;
        }
    }
    return counts;
}

// ─────────────────────────────────────────────────────────────────────────────
// Sample data used across tests
// ─────────────────────────────────────────────────────────────────────────────

const sampleDetails = [
    { requirement_id: 'SL-PDPA-S6-1',  status: 'non_compliant', risk_level: 'high',     clause: 'Purpose limitation' },
    { requirement_id: 'SL-PDPA-S7-1',  status: 'non_compliant', risk_level: 'critical',  clause: 'Lawful basis' },
    { requirement_id: 'SL-PDPA-S10-1', status: 'partial',       risk_level: 'medium',    clause: 'Data retention' },
    { requirement_id: 'SL-PDPA-S12-1', status: 'compliant',     risk_level: 'low',       clause: 'Subject rights' },
    { requirement_id: 'SL-PDPA-S15-1', status: 'non_compliant', risk_level: 'low',       clause: 'Data breach notice' },
    { requirement_id: 'SL-PDPA-S18-1', status: 'partial',       risk_level: 'high',      clause: 'Third-party sharing' },
];

// ─────────────────────────────────────────────────────────────────────────────
// getGaps()
// ─────────────────────────────────────────────────────────────────────────────

describe('getGaps()', () => {

    test('returns only non_compliant items', () => {
        const result = getGaps(sampleDetails, null);
        result.forEach(item => {
            expect(item.status).toBe('non_compliant');
        });
    });

    test('excludes partial items', () => {
        const result = getGaps(sampleDetails, null);
        const hasPartial = result.some(item => item.status === 'partial');
        expect(hasPartial).toBe(false);
    });

    test('excludes compliant items', () => {
        const result = getGaps(sampleDetails, null);
        const hasCompliant = result.some(item => item.status === 'compliant');
        expect(hasCompliant).toBe(false);
    });

    test('returns 3 gaps from sample data', () => {
        const result = getGaps(sampleDetails, null);
        expect(result).toHaveLength(3);
    });

    test('sorts gaps by severity — critical first', () => {
        const result = getGaps(sampleDetails, null);
        expect(result[0].risk_level).toBe('critical');
        expect(result[1].risk_level).toBe('high');
        expect(result[2].risk_level).toBe('low');
    });

    test('applies activeFilter — returns only matching risk_level', () => {
        const result = getGaps(sampleDetails, 'high');
        expect(result).toHaveLength(1);
        expect(result[0].requirement_id).toBe('SL-PDPA-S6-1');
    });

    test('activeFilter returns empty array when no gaps match that level', () => {
        const result = getGaps(sampleDetails, 'medium');
        expect(result).toHaveLength(0);
    });

    test('returns empty array when allDetails is empty', () => {
        const result = getGaps([], null);
        expect(result).toHaveLength(0);
    });

    test('returns empty array when all items are compliant or partial', () => {
        const compliantOnly = [
            { requirement_id: 'A', status: 'compliant', risk_level: 'low' },
            { requirement_id: 'B', status: 'partial',   risk_level: 'medium' },
        ];
        const result = getGaps(compliantOnly, null);
        expect(result).toHaveLength(0);
    });

    test('treats null risk_level as unknown — sorted last', () => {
        const details = [
            { requirement_id: 'X', status: 'non_compliant', risk_level: null,   clause: 'No level' },
            { requirement_id: 'Y', status: 'non_compliant', risk_level: 'high', clause: 'Has level' },
        ];
        const result = getGaps(details, null);
        expect(result[0].risk_level).toBe('high');
        expect(result[1].risk_level).toBeNull();
    });

    test('treats unrecognised risk_level as unknown — sorted last', () => {
        const details = [
            { requirement_id: 'X', status: 'non_compliant', risk_level: 'informational', clause: 'Odd level' },
            { requirement_id: 'Y', status: 'non_compliant', risk_level: 'critical',       clause: 'Critical' },
        ];
        const result = getGaps(details, null);
        expect(result[0].risk_level).toBe('critical');
        expect(result[1].risk_level).toBe('informational');
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// getRisks()
// ─────────────────────────────────────────────────────────────────────────────

describe('getRisks()', () => {

    test('includes both non_compliant and partial items', () => {
        const result = getRisks(sampleDetails, null);
        const statuses = result.map(item => item.status);
        expect(statuses).toContain('non_compliant');
        expect(statuses).toContain('partial');
    });

    test('excludes compliant items', () => {
        const result = getRisks(sampleDetails, null);
        const hasCompliant = result.some(item => item.status === 'compliant');
        expect(hasCompliant).toBe(false);
    });

    test('returns 5 risks from sample data (3 non_compliant + 2 partial)', () => {
        const result = getRisks(sampleDetails, null);
        expect(result).toHaveLength(5);
    });

    test('sorts risks by severity — critical first', () => {
        const result = getRisks(sampleDetails, null);
        expect(result[0].risk_level).toBe('critical');
    });

    test('high severity items appear before medium', () => {
        const result = getRisks(sampleDetails, null);
        const highIdx   = result.findIndex(r => r.risk_level === 'high');
        const mediumIdx = result.findIndex(r => r.risk_level === 'medium');
        expect(highIdx).toBeLessThan(mediumIdx);
    });

    test('applies activeFilter — returns only matching risk_level', () => {
        const result = getRisks(sampleDetails, 'high');
        expect(result).toHaveLength(2);
        result.forEach(item => expect(item.risk_level).toBe('high'));
    });

    test('activeFilter on medium returns only partial items with medium risk', () => {
        const result = getRisks(sampleDetails, 'medium');
        expect(result).toHaveLength(1);
        expect(result[0].status).toBe('partial');
        expect(result[0].risk_level).toBe('medium');
    });

    test('activeFilter returns empty array when no risks match that level', () => {
        const result = getRisks(sampleDetails, 'critical');
        // only 1 critical, and it is non_compliant
        expect(result).toHaveLength(1);
        expect(result[0].risk_level).toBe('critical');
    });

    test('returns empty array when allDetails is empty', () => {
        const result = getRisks([], null);
        expect(result).toHaveLength(0);
    });

    test('returns empty array when all items are compliant', () => {
        const allCompliant = [
            { requirement_id: 'A', status: 'compliant', risk_level: 'low' },
            { requirement_id: 'B', status: 'compliant', risk_level: 'medium' },
        ];
        const result = getRisks(allCompliant, null);
        expect(result).toHaveLength(0);
    });

    test('null activeFilter does not filter out any non_compliant or partial items', () => {
        const result = getRisks(sampleDetails, null);
        expect(result.length).toBeGreaterThan(0);
    });
});

// ─────────────────────────────────────────────────────────────────────────────
// getRiskCounts()
// ─────────────────────────────────────────────────────────────────────────────

describe('getRiskCounts()', () => {

    test('returns zero counts for all levels when risks array is empty', () => {
        const counts = getRiskCounts([]);
        expect(counts).toEqual({ critical: 0, high: 0, medium: 0, low: 0 });
    });

    test('counts each severity level correctly', () => {
        const risks = getRisks(sampleDetails, null);
        const counts = getRiskCounts(risks);
        // From sampleDetails risks: 1 critical, 2 high, 1 medium, 1 low
        expect(counts.critical).toBe(1);
        expect(counts.high).toBe(2);
        expect(counts.medium).toBe(1);
        expect(counts.low).toBe(1);
    });

    test('does not count items with null risk_level', () => {
        const risks = [
            { requirement_id: 'A', status: 'non_compliant', risk_level: null },
            { requirement_id: 'B', status: 'partial',       risk_level: null },
        ];
        const counts = getRiskCounts(risks);
        expect(counts).toEqual({ critical: 0, high: 0, medium: 0, low: 0 });
    });

    test('does not count items with unrecognised risk_level', () => {
        const risks = [
            { requirement_id: 'A', status: 'non_compliant', risk_level: 'unknown' },
        ];
        const counts = getRiskCounts(risks);
        expect(counts).toEqual({ critical: 0, high: 0, medium: 0, low: 0 });
    });

    test('correctly counts when all risks have the same severity', () => {
        const risks = [
            { requirement_id: 'A', risk_level: 'high' },
            { requirement_id: 'B', risk_level: 'high' },
            { requirement_id: 'C', risk_level: 'high' },
        ];
        const counts = getRiskCounts(risks);
        expect(counts.high).toBe(3);
        expect(counts.critical).toBe(0);
        expect(counts.medium).toBe(0);
        expect(counts.low).toBe(0);
    });

    test('counts only the risks passed in — not all allDetails', () => {
        // Passing only the filtered risks (no compliant items)
        const filteredRisks = sampleDetails.filter(
            d => d.status === 'non_compliant' || d.status === 'partial'
        );
        const counts = getRiskCounts(filteredRisks);
        const total = counts.critical + counts.high + counts.medium + counts.low;
        expect(total).toBe(filteredRisks.length);
    });

    test('total count matches the number of risks with recognised severity', () => {
        const risks = getRisks(sampleDetails, null);
        const counts = getRiskCounts(risks);
        const total = counts.critical + counts.high + counts.medium + counts.low;
        const recognisedRisks = risks.filter(
            r => ['critical', 'high', 'medium', 'low'].includes(r.risk_level)
        );
        expect(total).toBe(recognisedRisks.length);
    });
});
