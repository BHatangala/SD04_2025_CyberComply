/**
 * Unit tests for comparison_dashboard_graphical.html
 *
 * Covers:
 *  - riskClass() mapping
 *  - resetControls() default state restoration
 *  - displayedDepartments filtering by risk
 *  - displayedDepartments sorting by compliance
 *  - displayedDepartments sorting by improvements
 *  - displayedDepartments sorting by risk rank
 *  - color assignment and riskRank derivation
 *  - polarToCartesian() coordinate generation
 *  - describeArc() SVG path generation
 *  - sliceTransform() active slice translation
 */

const { describe, test, expect } = require('@jest/globals');

// ─────────────────────────────────────────────────────────────────────────────
// Pure logic functions extracted from comparison_dashboard_graphical.html
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Returns CSS class name for a given risk label.
 */
function riskClass(r) {
    if (r === 'High') return 'high';
    if (r === 'Medium') return 'medium';
    return 'low';
}

/**
 * Resets dashboard controls back to default values.
 */
function resetControlsState() {
    return {
        riskFilter: 'All',
        sortBy: 'compliance',
        sortOrder: 'desc'
    };
}

/**
 * Mirrors displayedDepartments computed property.
 * Applies color assignment, riskRank derivation, filtering, and sorting.
 */
function getDisplayedDepartments(departments, riskFilter, sortBy, sortOrder) {
    const riskRank = { High: 3, Medium: 2, Low: 1 };
    const palette = ['#f2f6fa', '#94a6b4', '#1c3f60', '#355679', '#afc1cf', '#7b8ea3'];

    let list = departments.map((d, idx) => ({
        ...d,
        color: palette[idx % palette.length],
        riskRank: riskRank[d.risk] || 0,
    }));

    if (riskFilter !== 'All') {
        list = list.filter((d) => d.risk === riskFilter);
    }

    const dir = sortOrder === 'asc' ? 1 : -1;

    list.sort((a, b) => {
        if (sortBy === 'compliance') return (a.compliance - b.compliance) * dir;
        if (sortBy === 'improvements') return (a.improvements - b.improvements) * dir;
        if (sortBy === 'risk') return (a.riskRank - b.riskRank) * dir;
        return 0;
    });

    return list;
}

/**
 * Converts polar coordinates to cartesian coordinates.
 */
function polarToCartesian(cx, cy, r, angleDeg) {
    const rad = (angleDeg * Math.PI) / 180;
    return {
        x: cx + r * Math.cos(rad),
        y: cy + r * Math.sin(rad)
    };
}

/**
 * Builds SVG arc path for a pie slice.
 */
function describeArc(cx, cy, r, startAngle, endAngle) {
    const start = polarToCartesian(cx, cy, r, startAngle);
    const end = polarToCartesian(cx, cy, r, endAngle);
    const largeArcFlag = endAngle - startAngle <= 180 ? '0' : '1';

    return [
        `M ${cx} ${cy}`,
        `L ${start.x} ${start.y}`,
        `A ${r} ${r} 0 ${largeArcFlag} 1 ${end.x} ${end.y}`,
        'Z',
    ].join(' ');
}

/**
 * Mirrors sliceTransform() method for active pie slice animation.
 */
function sliceTransform(slice, activeSliceIndex, i) {
    if (activeSliceIndex !== i) return '';
    const pop = 8;
    const rad = (slice.midAngle * Math.PI) / 180;
    const dx = pop * Math.cos(rad);
    const dy = pop * Math.sin(rad);
    return `translate(${dx} ${dy})`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Sample data shared across tests
// ─────────────────────────────────────────────────────────────────────────────

const sampleDepartments = [
    {
        id: 'd1',
        name: 'Department 1',
        compliance: 72,
        risk: 'Medium',
        improvements: 5,
        topGap: 'Access control reviews',
    },
    {
        id: 'd2',
        name: 'Department 2',
        compliance: 58,
        risk: 'High',
        improvements: 8,
        topGap: 'Incident response readiness',
    },
    {
        id: 'd3',
        name: 'Department 3',
        compliance: 84,
        risk: 'Low',
        improvements: 3,
        topGap: 'Data retention alignment',
    },
    {
        id: 'd4',
        name: 'Department 4',
        compliance: 66,
        risk: 'Medium',
        improvements: 6,
        topGap: 'Vendor / third-party checks',
    },
    {
        id: 'd5',
        name: 'Department 5',
        compliance: 47,
        risk: 'High',
        improvements: 9,
        topGap: 'Encryption & backups',
    },
];

// ─────────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────────

describe('riskClass', () => {
    test('returns high for High risk', () => {
        expect(riskClass('High')).toBe('high');
    });

    test('returns medium for Medium risk', () => {
        expect(riskClass('Medium')).toBe('medium');
    });

    test('returns low for Low risk', () => {
        expect(riskClass('Low')).toBe('low');
    });

    test('defaults to low for unknown value', () => {
        expect(riskClass('Unknown')).toBe('low');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('resetControlsState', () => {
    test('returns default dashboard control values', () => {
        expect(resetControlsState()).toEqual({
            riskFilter: 'All',
            sortBy: 'compliance',
            sortOrder: 'desc'
        });
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('getDisplayedDepartments', () => {
    test('returns all departments when riskFilter is All', () => {
        const result = getDisplayedDepartments(sampleDepartments, 'All', 'compliance', 'desc');
        expect(result).toHaveLength(5);
    });

    test('filters only High risk departments', () => {
        const result = getDisplayedDepartments(sampleDepartments, 'High', 'compliance', 'desc');
        expect(result).toHaveLength(2);
        expect(result.every(d => d.risk === 'High')).toBe(true);
    });

    test('filters only Medium risk departments', () => {
        const result = getDisplayedDepartments(sampleDepartments, 'Medium', 'compliance', 'desc');
        expect(result).toHaveLength(2);
        expect(result.every(d => d.risk === 'Medium')).toBe(true);
    });

    test('returns empty array when no departments match filter', () => {
        const result = getDisplayedDepartments(sampleDepartments, 'Critical', 'compliance', 'desc');
        expect(result).toEqual([]);
    });

    test('sorts by compliance descending', () => {
        const result = getDisplayedDepartments(sampleDepartments, 'All', 'compliance', 'desc');
        expect(result[0].name).toBe('Department 3');
        expect(result[result.length - 1].name).toBe('Department 5');
    });

    test('sorts by compliance ascending', () => {
        const result = getDisplayedDepartments(sampleDepartments, 'All', 'compliance', 'asc');
        expect(result[0].name).toBe('Department 5');
        expect(result[result.length - 1].name).toBe('Department 3');
    });

    test('sorts by improvements descending', () => {
        const result = getDisplayedDepartments(sampleDepartments, 'All', 'improvements', 'desc');
        expect(result[0].name).toBe('Department 5');
        expect(result[1].name).toBe('Department 2');
    });

    test('sorts by improvements ascending', () => {
        const result = getDisplayedDepartments(sampleDepartments, 'All', 'improvements', 'asc');
        expect(result[0].name).toBe('Department 3');
        expect(result[result.length - 1].name).toBe('Department 5');
    });

    test('sorts by risk descending using riskRank', () => {
        const result = getDisplayedDepartments(sampleDepartments, 'All', 'risk', 'desc');
        expect(result[0].risk).toBe('High');
        expect(result[1].risk).toBe('High');
    });

    test('sorts by risk ascending using riskRank', () => {
        const result = getDisplayedDepartments(sampleDepartments, 'All', 'risk', 'asc');
        expect(result[0].risk).toBe('Low');
    });

    test('assigns a color to every department', () => {
        const result = getDisplayedDepartments(sampleDepartments, 'All', 'compliance', 'desc');
        expect(result.every(d => typeof d.color === 'string' && d.color.length > 0)).toBe(true);
    });

    test('assigns riskRank correctly', () => {
        const result = getDisplayedDepartments(sampleDepartments, 'All', 'risk', 'desc');
        const highDept = result.find(d => d.risk === 'High');
        const lowDept = result.find(d => d.risk === 'Low');

        expect(highDept.riskRank).toBe(3);
        expect(lowDept.riskRank).toBe(1);
    });

    test('does not mutate original department count', () => {
        const original = [...sampleDepartments];
        getDisplayedDepartments(sampleDepartments, 'All', 'compliance', 'desc');
        expect(sampleDepartments.length).toBe(original.length);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('polarToCartesian', () => {
    test('returns correct point for angle 0', () => {
        const point = polarToCartesian(100, 100, 50, 0);
        expect(point.x).toBeCloseTo(150);
        expect(point.y).toBeCloseTo(100);
    });

    test('returns correct point for angle 90', () => {
        const point = polarToCartesian(100, 100, 50, 90);
        expect(point.x).toBeCloseTo(100);
        expect(point.y).toBeCloseTo(150);
    });

    test('returns correct point for angle -90', () => {
        const point = polarToCartesian(100, 100, 50, -90);
        expect(point.x).toBeCloseTo(100);
        expect(point.y).toBeCloseTo(50);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('describeArc', () => {
    test('returns an SVG path string', () => {
        const path = describeArc(100, 100, 95, -90, 90);
        expect(typeof path).toBe('string');
        expect(path).toContain('M 100 100');
        expect(path).toContain('A 95 95');
        expect(path).toContain('Z');
    });

    test('uses large arc flag 0 for arcs 180 degrees or less', () => {
        const path = describeArc(100, 100, 95, 0, 180);
        expect(path).toContain('A 95 95 0 0 1');
    });

    test('uses large arc flag 1 for arcs greater than 180 degrees', () => {
        const path = describeArc(100, 100, 95, 0, 270);
        expect(path).toContain('A 95 95 0 1 1');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('sliceTransform', () => {
    test('returns empty string when slice is not active', () => {
        const slice = { midAngle: 45 };
        expect(sliceTransform(slice, null, 0)).toBe('');
        expect(sliceTransform(slice, 1, 0)).toBe('');
    });

    test('returns translate string when slice is active', () => {
        const slice = { midAngle: 0 };
        const result = sliceTransform(slice, 0, 0);
        expect(result).toContain('translate(');
    });

    test('returns correct translation for angle 0', () => {
        const slice = { midAngle: 0 };
        const result = sliceTransform(slice, 0, 0);
        expect(result).toBe('translate(8 0)');
    });
});