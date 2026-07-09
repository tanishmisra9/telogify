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
    expect(s['Fast'].strengths[0]?.text).toBe('Sets the race-pace benchmark')
    expect(s['Fast'].strengths[0]?.detail).toBe('')
  })

  it('shows the detail as a gap to the field leader, not the raw value', () => {
    const s = seasonSummary(rows)
    // Mid raw pace 0.6, leader 0.1 -> gap 0.50 (matches the ranking table which is leader-anchored)
    expect(s['Mid'].strengths[0]?.text).toMatch(/2nd-quickest race pace/)
    expect(s['Mid'].strengths[0]?.detail).toBe('+0.50s')
    // Slow's weakness is its race pace, gap 1.3 - 0.1 = 1.20
    expect(s['Slow'].weaknesses[0]?.detail).toBe('+1.20s')
  })

  it('quantifies the straight-line weakness in km/h off the leader', () => {
    const s = seasonSummary(rows)
    expect(s['Fast'].weaknesses[0]?.text).toMatch(/straight-line speed/)
    expect(s['Fast'].weaknesses[0]?.detail).toBe('-10 km/h')
  })

  it('suppresses a bottom-third rank as a strength (worst car shows a weakness only)', () => {
    const s = seasonSummary(rows)
    expect(s['Awful'].strengths).toEqual([])
    expect(s['Awful'].weaknesses[0]?.text).toBe('Slowest in a straight line')
    expect(s['Awful'].weaknesses[0]?.detail).toBe('-20 km/h')
  })

  it('ignores metrics with no spread across the field', () => {
    const flat = [row({ constructor: 'A' }), row({ constructor: 'B' }), row({ constructor: 'C' })]
    const s = seasonSummary(flat)
    expect(s['A'].strengths).toEqual([])
    expect(s['A'].weaknesses).toEqual([])
  })

  it('returns empty summaries when fewer than three teams', () => {
    const two = [row({ constructor: 'A' }), row({ constructor: 'B', pace_gap: agg(1.0) })]
    const s = seasonSummary(two)
    expect(s['A']).toEqual({ strengths: [], weaknesses: [] })
    expect(s['B']).toEqual({ strengths: [], weaknesses: [] })
  })

  it('surfaces up to 3 strengths and weaknesses without overlap when more metrics rank', () => {
    // 6 teams so every metric (pace, quali, top speed, tyre deg, sector count, spread-based
    // consistency) has real spread and >= 3 present values, i.e. all 6 metrics rank.
    const wide = [
      row({
        constructor: 'Best',
        pace_gap: agg(0.1, 0.1),
        quali_gap_pct: agg(0.1),
        top_speed_deficit_kmh: 0,
        tyre_deg_s_per_lap: 0.01,
        sector_dominance_count: 10,
      }),
      row({ constructor: 'B', pace_gap: agg(0.4, 0.2), quali_gap_pct: agg(0.3), top_speed_deficit_kmh: 3, tyre_deg_s_per_lap: 0.03, sector_dominance_count: 6 }),
      row({ constructor: 'C', pace_gap: agg(0.7, 0.3), quali_gap_pct: agg(0.5), top_speed_deficit_kmh: 6, tyre_deg_s_per_lap: 0.05, sector_dominance_count: 4 }),
      row({ constructor: 'D', pace_gap: agg(1.0, 0.4), quali_gap_pct: agg(0.7), top_speed_deficit_kmh: 9, tyre_deg_s_per_lap: 0.07, sector_dominance_count: 2 }),
      row({ constructor: 'E', pace_gap: agg(1.3, 0.5), quali_gap_pct: agg(0.9), top_speed_deficit_kmh: 12, tyre_deg_s_per_lap: 0.09, sector_dominance_count: 1 }),
      row({
        constructor: 'Worst',
        pace_gap: agg(1.6, 0.6),
        quali_gap_pct: agg(1.1),
        top_speed_deficit_kmh: 15,
        tyre_deg_s_per_lap: 0.11,
        sector_dominance_count: 0,
      }),
    ]
    const s = seasonSummary(wide)
    expect(s['Best'].strengths.length).toBe(3)
    expect(s['Worst'].weaknesses.length).toBe(3)
    // No metric text should appear on both sides for the same team.
    const mid = s['C']
    const strengthTexts = new Set(mid.strengths.map((t) => t.text))
    const weaknessTexts = new Set(mid.weaknesses.map((t) => t.text))
    for (const t of strengthTexts) expect(weaknessTexts.has(t)).toBe(false)
  })
})
