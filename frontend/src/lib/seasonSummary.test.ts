import { describe, it, expect } from 'vitest'
import { seasonSummary } from './seasonSummary'
import type { SeasonConstructorRow } from '@/lib/api'

function agg(mean: number | null, spread = 0, n = 8) {
  return { mean, spread, n }
}

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
  // Only pace and top-speed carry spread; pace leader is 0.1 (non-zero) so gap != raw is testable.
  const rows = [
    row({ constructor: 'Fast', pace_gap: agg(0.1), top_speed_deficit_kmh: 10 }),
    row({ constructor: 'Mid', pace_gap: agg(0.6), top_speed_deficit_kmh: 5 }),
    row({ constructor: 'Slow', pace_gap: agg(1.3), top_speed_deficit_kmh: 0 }),
    row({ constructor: 'Awful', pace_gap: agg(3.1), top_speed_deficit_kmh: 20 }),
  ]

  it('gives the pace leader the benchmark strength with no gap number', () => {
    const s = seasonSummary(rows)
    expect(s['Fast'].strength?.text).toBe('Sets the race-pace benchmark')
    expect(s['Fast'].strength?.detail).toBe('')
  })

  it('shows the detail as a gap to the field leader, not the raw value', () => {
    const s = seasonSummary(rows)
    // Mid raw pace 0.6, leader 0.1 -> gap 0.50 (matches the ranking table which is leader-anchored)
    expect(s['Mid'].strength?.text).toMatch(/2nd-quickest race pace/)
    expect(s['Mid'].strength?.detail).toBe('+0.50s')
    // Slow's weakness is its race pace, gap 1.3 - 0.1 = 1.20
    expect(s['Slow'].weakness?.detail).toBe('+1.20s')
  })

  it('quantifies the straight-line weakness in km/h off the leader', () => {
    const s = seasonSummary(rows)
    expect(s['Fast'].weakness?.text).toMatch(/straight-line speed/)
    expect(s['Fast'].weakness?.detail).toBe('-10 km/h')
  })

  it('suppresses a bottom-third rank as a strength (worst car shows a weakness only)', () => {
    const s = seasonSummary(rows)
    expect(s['Awful'].strength).toBeNull()
    expect(s['Awful'].weakness?.text).toBe('Slowest in a straight line')
    expect(s['Awful'].weakness?.detail).toBe('-20 km/h')
  })

  it('ignores metrics with no spread across the field', () => {
    const flat = [row({ constructor: 'A' }), row({ constructor: 'B' }), row({ constructor: 'C' })]
    const s = seasonSummary(flat)
    expect(s['A'].strength).toBeNull()
    expect(s['A'].weakness).toBeNull()
  })
})
