import { describe, it, expect } from 'vitest'
import { seasonSummary } from './seasonSummary'
import type { SeasonConstructorRow } from '@/lib/api'

function agg(mean: number | null, spread = 0, n = 8) {
  return { mean, spread, n }
}

// equal on everything except what a test overrides, so only the overridden metrics have spread
function row(over: Partial<SeasonConstructorRow>): SeasonConstructorRow {
  return {
    constructor: 'Team',
    overall_rank: 1,
    pace_gap: agg(0.5),
    quali_gap_pct: agg(0.5),
    top_speed_deficit_kmh: 3,
    top_speed_deficit_mph: 1.9,
    sector_dominance_count: 5,
    tyre_deg_s_per_lap: 0.05,
    trend: { pace: [], quali: [], cumulative: [] },
    confidence: 'high',
    ...over,
  }
}

describe('seasonSummary', () => {
  // Only pace and top-speed carry spread; every other metric is equal across teams (no spread),
  // so strengths/weaknesses come from those two channels.
  const rows = [
    row({ constructor: 'Fast', pace_gap: agg(0), top_speed_deficit_kmh: 10 }),
    row({ constructor: 'Mid', pace_gap: agg(0.5), top_speed_deficit_kmh: 5 }),
    row({ constructor: 'Slow', pace_gap: agg(1.2), top_speed_deficit_kmh: 0 }),
  ]

  it('gives the pace leader the benchmark strength', () => {
    const s = seasonSummary(rows)
    expect(s['Fast'].strength?.text).toBe('Sets the race-pace benchmark')
  })

  it('makes the pace leader with the worst top speed own that as its weakness', () => {
    const s = seasonSummary(rows)
    expect(s['Fast'].weakness?.text).toBe('Slowest in a straight line')
    expect(s['Fast'].weakness?.detail).toBe('-10 km/h')
  })

  it('gives every team both a strength and a weakness', () => {
    const s = seasonSummary(rows)
    for (const team of ['Fast', 'Mid', 'Slow']) {
      expect(s[team].strength).not.toBeNull()
    }
    // the two teams that lead/trail distinct channels both get a weakness
    expect(s['Slow'].strength?.text).toBe('Fastest in a straight line')
    expect(s['Slow'].weakness?.text).toBe('Slowest race pace in the field')
  })

  it('phrases a non-leader strength with its ordinal position', () => {
    const s = seasonSummary(rows)
    // Mid is 2nd on both channels; its strength reads as a 2nd-place trait, not a benchmark
    expect(s['Mid'].strength?.text).toMatch(/2nd-/)
  })

  it('ignores metrics with no spread across the field', () => {
    // all teams identical -> nobody has a distinguishing trait
    const flat = [row({ constructor: 'A' }), row({ constructor: 'B' }), row({ constructor: 'C' })]
    const s = seasonSummary(flat)
    expect(s['A'].strength).toBeNull()
    expect(s['A'].weakness).toBeNull()
  })
})
