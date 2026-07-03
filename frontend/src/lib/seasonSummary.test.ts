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
    sector_dominance_count: 0,
    tyre_deg_s_per_lap: 0.05,
    trend: { pace: [], quali: [] },
    confidence: 'high',
    ...over,
  }
}

describe('seasonSummary', () => {
  it('gives the pace leader the benchmark strength and the laggard the weakness', () => {
    const rows = [
      row({ constructor: 'Fast', pace_gap: agg(0) }),
      row({ constructor: 'Slow', pace_gap: agg(1.2) }),
    ]
    const s = seasonSummary(rows)
    expect(s['Fast'].strengths.some((x) => x.includes('race-pace benchmark'))).toBe(true)
    expect(s['Slow'].weaknesses.some((x) => x.includes('Slowest race pace'))).toBe(true)
    expect(s['Slow'].weaknesses.some((x) => x.includes('1.200s'))).toBe(true)
  })

  it('fills the real straight-line deficit number for the slowest team', () => {
    const rows = [
      row({ constructor: 'Quick', top_speed_deficit_kmh: 0 }),
      row({ constructor: 'Draggy', top_speed_deficit_kmh: 12 }),
    ]
    const s = seasonSummary(rows)
    expect(s['Quick'].strengths).toContain('Quickest in a straight line')
    expect(s['Draggy'].weaknesses).toContain('Down 12 km/h in a straight line')
  })

  it('does not emit a weakness for a low sector-dominance count', () => {
    const rows = [
      row({ constructor: 'A', sector_dominance_count: 10 }),
      row({ constructor: 'B', sector_dominance_count: 0 }),
    ]
    const s = seasonSummary(rows)
    expect(s['A'].strengths.some((x) => x.includes('Led 10 qualifying sectors'))).toBe(true)
    // B trails on sectors but that is not stated as a weakness
    expect(s['B'].weaknesses.every((x) => !x.includes('sector'))).toBe(true)
  })

  it('falls back to a neutral line for a team that neither leads nor trails anything', () => {
    // Three identical teams -> no metric has a distinct leader/laggard.
    const rows = [row({ constructor: 'A' }), row({ constructor: 'B' }), row({ constructor: 'C' })]
    const s = seasonSummary(rows)
    expect(s['A'].strengths).toEqual(['Solid midfield runner with no standout trait this season'])
    expect(s['A'].weaknesses).toEqual([])
  })
})
