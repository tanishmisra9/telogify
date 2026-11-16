import { describe, expect, it } from 'vitest'
import { exampleId, gateLines, quoteParts, storedLines, toolCallLines } from './tracedExample'
import type { TracedExample } from './api'

const ex: TracedExample = {
  year: 2026,
  round: 4,
  event_name: 'Bahrain Grand Prix',
  header: 'Red Bull set the pace',
  explanation_web:
    "Max Verstappen's Red Bull Racing car finished first. The team set the fastest race pace, with Mercedes 0.167 seconds per lap behind.",
  traced: '0.167',
  traced_with_unit: '0.167 seconds',
  raw: '0.16695454545454425',
  key: 'gap_to_team_ahead_s',
  tool: 'get_constructor_ranking',
  args: {},
  row: { constructor: 'Mercedes', overall_rank: 2, gap_to_team_ahead_s: 0.16695454545454425 },
}

describe('quoteParts', () => {
  it('takes the sentence with the figure and splits around it', () => {
    const q = quoteParts(ex)
    expect(q.figure).toBe('0.167 seconds')
    expect(q.before + q.figure + q.after).toBe('The team set the fastest race pace, with Mercedes 0.167 seconds per lap behind.')
  })

  it('does not split a sentence on a decimal point', () => {
    expect(quoteParts(ex).before).not.toMatch(/^\d/)
  })

  it('never invents a highlight when the figure text is not in the prose', () => {
    const q = quoteParts({ ...ex, traced_with_unit: '9.9 seconds' })
    expect(q.figure).toBe('')
    expect(q.before).toBe(ex.explanation_web)
  })
})

describe('code lines', () => {
  it('marks the traced value in the tool return row and keeps every field', () => {
    const lines = toolCallLines(ex)
    expect(lines[0]).toBe('get_constructor_ranking({})')
    expect(lines).toContain('    "gap_to_team_ahead_s": {{0.16695454545454425}}')
    expect(lines).toContain('    "constructor": "Mercedes",')
    expect(lines.filter((l) => l.includes('{{')).length).toBe(1)
  })

  it('stores the raw value under its identity and gates prose against it', () => {
    expect(storedLines(ex)).toEqual(['{', '  "constructor": "Mercedes",', '  "gap_to_team_ahead_s": 0.16695454545454425', '}'])
    expect(gateLines(ex)[0]).toBe('prose:  {{0.167}}')
    expect(gateLines(ex)[1]).toContain('{{0.16695454545454425}}')
  })

  it('handles a row with no identifying string', () => {
    const lines = storedLines({ ...ex, row: { sector: 1, gap_to_team_ahead_s: 0.1 } })
    expect(lines).toEqual(['{', '  "gap_to_team_ahead_s": 0.16695454545454425', '}'])
  })
})

describe('exampleId', () => {
  it('is stable and distinguishes two figures of one insight', () => {
    expect(exampleId(ex)).toBe(exampleId({ ...ex }))
    expect(exampleId(ex)).not.toBe(exampleId({ ...ex, traced: '0.5' }))
  })
})
