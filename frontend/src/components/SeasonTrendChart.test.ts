import { describe, expect, it } from 'vitest'
import { legendTeamOrder, seriesTeamOrder } from './SeasonTrendChart'
import type { SeasonConstructorRow } from '@/lib/api'

// Two teams whose pace/quali ranking flips, plus one with no cumulative data -- mirrors the real
// live regression (Alpine/Racing Bulls swapping between Race pace and Qualifying tabs).
function row(constructor: string, paceMean: number, qualiMean: number, cumulative: number[]): SeasonConstructorRow {
  return {
    constructor,
    overall_rank: null,
    pace_gap: { mean: paceMean, spread: null, n: 1 },
    quali_gap_pct: { mean: qualiMean, spread: null, n: 1 },
    top_speed_deficit_kmh: null,
    top_speed_deficit_mph: null,
    sector_dominance_count: 0,
    tyre_deg_s_per_lap: null,
    trend: {
      pace: [{ round: 1, value: paceMean }],
      quali: [{ round: 1, value: qualiMean }],
      cumulative: cumulative.map((value, i) => ({ round: i + 1, value })),
    },
    confidence: 'high',
  }
}

const rows: SeasonConstructorRow[] = [
  row('Alpine', 1.6, 1.7, [0.5, 0.4]),
  row('Racing Bulls', 1.7, 1.5, [0.6, 0.7]),
  row('Williams', 2.1, 2.8, []),
]

describe('seriesTeamOrder', () => {
  it('stays identical across metrics for the same team set (required for the AnimatePresence morph)', () => {
    expect(seriesTeamOrder(rows, 'pace')).toEqual(seriesTeamOrder(rows, 'quali'))
    expect(seriesTeamOrder(rows, 'pace')).toEqual(['Alpine', 'Racing Bulls', 'Williams'])
  })

  it('drops a team with no data for the metric', () => {
    expect(seriesTeamOrder(rows, 'cumulative')).toEqual(['Alpine', 'Racing Bulls'])
  })
})

describe('legendTeamOrder', () => {
  it('reorders by the selected metric, unlike seriesTeamOrder', () => {
    expect(legendTeamOrder(rows, 'pace')).toEqual(['Alpine', 'Racing Bulls', 'Williams'])
    expect(legendTeamOrder(rows, 'quali')).toEqual(['Racing Bulls', 'Alpine', 'Williams'])
  })

  it('drops a team with no data for the metric', () => {
    expect(legendTeamOrder(rows, 'cumulative')).toEqual(['Alpine', 'Racing Bulls'])
  })
})
