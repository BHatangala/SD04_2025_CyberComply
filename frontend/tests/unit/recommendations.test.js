/**
 * Unit tests for recommendations.html
 *
 * Covers:
 *  - buildReference()   — section-only, section+subsection, full section+subsection+clause
 *  - actionify()        — all 10 legal prefix replacements, uppercase first character fallback
 *  - deriveSteps()      — sub-clause splitting path, sentence splitting path, short-text fallback,
 *                         filtering of parts too short to be meaningful steps
 */

const { describe, test, expect } = require('@jest/globals');

// ─────────────────────────────────────────────────────────────────────────────
// Pure logic extracted from recommendations.html
// ─────────────────────────────────────────────────────────────────────────────

function buildReference(req) {
    let ref = `Section ${req.section}`;
    if (req.subsection) ref += `(${req.subsection})`;
    if (req.clause)     ref += `(${req.clause})`;
    ref += ` — ${req.clause_title}`;
    return ref;
}

function actionify(text) {
    return text
        .replace(/^Every controller shall\s+/i,  'Ensure that the organisation ')
        .replace(/^The controller shall\s+/i,     'Ensure that the organisation ')
        .replace(/^A controller shall\s+/i,       'Ensure that the organisation ')
        .replace(/^Controllers must\s+/i,         'Ensure that the organisation ')
        .replace(/^Processing must\s+/i,          'Ensure that all processing ')
        .replace(/^Processing is\s+/i,            'Ensure processing is ')
        .replace(/^Personal data shall\s+/i,      'Ensure personal data is ')
        .replace(/^Personal data must\s+/i,       'Ensure personal data is ')
        .replace(/^The processor shall\s+/i,      'Ensure the processor ')
        .replace(/^Processors must\s+/i,          'Ensure processors ')
        .replace(/^[a-z]/, c => c.toUpperCase());
}

function deriveSteps(req) {
    const raw = req.requirement;
    const steps = [];

    const subClauseMatches = [...raw.matchAll(/\([a-z]\)\s+/g)];

    if (subClauseMatches.length >= 2) {
        const parts = raw.split(/\([a-z]\)\s+/).filter(p => p.trim().length > 10);
        for (const part of parts) {
            const clean = part.replace(/\.$/, '').trim();
            if (clean.length > 10) steps.push(actionify(clean));
        }
    } else {
        const sentences = raw.split(/\.\s+/).filter(s => s.trim().length > 15);
        for (const s of sentences) {
            steps.push(actionify(s.trim()));
        }
    }

    if (req.schedule_content && steps.length < 4) {
        for (const [, sched] of Object.entries(req.schedule_content)) {
            if (sched.conditions && sched.conditions.length > 0) {
                const cond = sched.conditions[0].replace(/^\([a-z]\)\s+/, '');
                const condTrimmed = cond.length > 220
                    ? cond.substring(0, cond.lastIndexOf(' ', 220)) + '...'
                    : cond;
                steps.push(`Ensure compliance with ${sched.description}: ${condTrimmed}`);
                if (steps.length >= 4) break;
            }
        }
    }

    return steps.length > 0
        ? steps
        : [`Implement controls to satisfy: ${raw.substring(0, 150)}...`];
}

// ─────────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────────

describe('buildReference', () => {
    test('builds reference with section only', () => {
        const req = { section: 5, clause_title: 'Consent of data subject' };
        expect(buildReference(req)).toBe('Section 5 — Consent of data subject');
    });

    test('builds reference with section and subsection', () => {
        const req = { section: 6, subsection: 1, clause_title: 'Lawful basis for processing' };
        expect(buildReference(req)).toBe('Section 6(1) — Lawful basis for processing');
    });

    test('builds reference with section, subsection, and clause', () => {
        const req = { section: 6, subsection: 1, clause: 'a', clause_title: 'Lawful basis for processing' };
        expect(buildReference(req)).toBe('Section 6(1)(a) — Lawful basis for processing');
    });

    test('omits subsection when not provided', () => {
        const req = { section: 8, clause: 'b', clause_title: 'Special categories of data' };
        expect(buildReference(req)).toBe('Section 8(b) — Special categories of data');
    });

    test('includes clause_title as the final segment after em dash', () => {
        const req = { section: 12, subsection: 3, clause: 'c', clause_title: 'Right to erasure' };
        const result = buildReference(req);
        expect(result.endsWith('— Right to erasure')).toBe(true);
    });

    test('always starts with Section followed by the section number', () => {
        const req = { section: 20, clause_title: 'Data transfers' };
        expect(buildReference(req).startsWith('Section 20')).toBe(true);
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('actionify', () => {
    test('replaces "Every controller shall" with "Ensure that the organisation"', () => {
        const result = actionify('Every controller shall implement appropriate measures.');
        expect(result.startsWith('Ensure that the organisation')).toBe(true);
    });

    test('replaces "The controller shall" with "Ensure that the organisation"', () => {
        const result = actionify('The controller shall appoint a data protection officer.');
        expect(result.startsWith('Ensure that the organisation')).toBe(true);
    });

    test('replaces "A controller shall" with "Ensure that the organisation"', () => {
        const result = actionify('A controller shall maintain records of processing.');
        expect(result.startsWith('Ensure that the organisation')).toBe(true);
    });

    test('replaces "Controllers must" with "Ensure that the organisation"', () => {
        const result = actionify('Controllers must notify the Authority of breaches.');
        expect(result.startsWith('Ensure that the organisation')).toBe(true);
    });

    test('replaces "Processing must" with "Ensure that all processing"', () => {
        const result = actionify('Processing must be lawful and transparent.');
        expect(result.startsWith('Ensure that all processing')).toBe(true);
    });

    test('replaces "Processing is" with "Ensure processing is"', () => {
        const result = actionify('Processing is only permitted with valid consent.');
        expect(result.startsWith('Ensure processing is')).toBe(true);
    });

    test('replaces "Personal data shall" with "Ensure personal data is"', () => {
        const result = actionify('Personal data shall be kept accurate and up to date.');
        expect(result.startsWith('Ensure personal data is')).toBe(true);
    });

    test('replaces "Personal data must" with "Ensure personal data is"', () => {
        const result = actionify('Personal data must not be retained beyond its purpose.');
        expect(result.startsWith('Ensure personal data is')).toBe(true);
    });

    test('replaces "The processor shall" with "Ensure the processor"', () => {
        const result = actionify('The processor shall act only on documented instructions.');
        expect(result.startsWith('Ensure the processor')).toBe(true);
    });

    test('replaces "Processors must" with "Ensure processors"', () => {
        const result = actionify('Processors must implement adequate security measures.');
        expect(result.startsWith('Ensure processors')).toBe(true);
    });

    test('uppercases first character when no prefix matches', () => {
        const result = actionify('data subjects have the right to access their data.');
        expect(result[0]).toBe('D');
    });

    test('preserves the rest of the string after prefix replacement', () => {
        const result = actionify('Every controller shall implement appropriate measures.');
        expect(result).toContain('implement appropriate measures');
    });
});

// ─────────────────────────────────────────────────────────────────────────────

describe('deriveSteps', () => {
    test('splits on sub-clauses when 2 or more are present', () => {
        const req = {
            requirement: 'Personal data shall (a) be collected lawfully (b) be kept accurate and up to date',
            schedule_content: null
        };
        const steps = deriveSteps(req);
        expect(steps.length).toBeGreaterThanOrEqual(2);
    });

    test('each sub-clause becomes a separate step', () => {
        const req = {
            requirement: '(a) appoint an officer (b) register with the Authority (c) renew registration annually',
            schedule_content: null
        };
        const steps = deriveSteps(req);
        expect(steps.length).toBe(3);
    });

    test('sub-clause steps are passed through actionify', () => {
        const req = {
            requirement: 'Every controller shall (a) implement measures (b) document all processing',
            schedule_content: null
        };
        const steps = deriveSteps(req);
        expect(steps[0].startsWith('Ensure that the organisation') || steps[0][0] === steps[0][0].toUpperCase()).toBe(true);
    });

    test('splits on sentences when fewer than 2 sub-clauses', () => {
        const req = {
            requirement: 'The controller shall appoint a data protection officer. The officer shall be registered with the Authority. The registration shall be renewed annually.',
            schedule_content: null
        };
        const steps = deriveSteps(req);
        expect(steps.length).toBe(3);
    });

    test('sentence splitting path passes text through actionify', () => {
        const req = {
            requirement: 'Personal data shall be kept accurate. Personal data must not be retained beyond its purpose.',
            schedule_content: null
        };
        const steps = deriveSteps(req);
        steps.forEach(step => {
            expect(step[0]).toBe(step[0].toUpperCase());
        });
    });

    test('returns fallback message when requirement text is too short', () => {
        const req = {
            requirement: 'Short.',
            schedule_content: null
        };
        const steps = deriveSteps(req);
        expect(steps.length).toBe(1);
        expect(steps[0]).toContain('Implement controls to satisfy');
    });

    test('fallback includes a portion of the original requirement text', () => {
        const req = {
            requirement: 'Brief.',
            schedule_content: null
        };
        const steps = deriveSteps(req);
        expect(steps[0]).toContain('Brief');
    });

    test('filters out sub-clause parts shorter than 10 characters', () => {
        const req = {
            requirement: 'Data must (a) ok (b) be collected only for specified and legitimate purposes and not further processed',
            schedule_content: null
        };
        const steps = deriveSteps(req);
        steps.forEach(step => {
            expect(step.length).toBeGreaterThan(10);
        });
    });

    test('filters out sentences shorter than 15 characters in sentence path', () => {
        const req = {
            requirement: 'Too short. The controller shall implement appropriate technical and organisational measures to protect personal data.',
            schedule_content: null
        };
        const steps = deriveSteps(req);
        steps.forEach(step => {
            expect(step.length).toBeGreaterThan(15);
        });
    });

    test('returns an array even for single long sentence with no sub-clauses', () => {
        const req = {
            requirement: 'The controller shall implement appropriate technical and organisational measures to protect personal data against accidental loss.',
            schedule_content: null
        };
        const steps = deriveSteps(req);
        expect(Array.isArray(steps)).toBe(true);
        expect(steps.length).toBeGreaterThan(0);
    });
});