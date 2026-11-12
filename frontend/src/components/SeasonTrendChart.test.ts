import { describe, expect, it } from 'vitest'
import { legendRowsFor, legendTeamOrder, seriesTeamOrder } from './SeasonTrendChart'
import type { SeasonConstructorRow } from '@/lib/api'

// Two teams whose pace/quali ranking flips, plus one with no cumulative data -- mirrors the real
// live regression (Alpine/Racing Bulls swapping between Race pace and Qualifying tabs).
function row(constructor: string, paceMean: number, qualiMean: number, cumulative: number[]): SeasonConstructorRow {
  return {
    constructor,
    overall_rank: null,
    overall_gap_s: null,
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

describe('legendRowsFor', () => {
  const withForm = (r: SeasonConstructorRow, pace: number, places: number | null): SeasonConstructorRow => ({
    ...r,
    form: { pace: { weighted: pace, rank_weighted: 2, rank_flat: 4, form_places: places } },
  })

  it('shows the weighted figure on the chart axis, the arrow and the hint sentence', () => {
    const [alpine] = legendRowsFor([withForm(rows[0], 1.6, 2)], 'pace')
    expect(alpine).toEqual({
      team: 'Alpine',
      value: '101.6%  ▲2',
      title: 'Gains 2 places on recent form: #2 recently, #4 over the season',
    })
  })

  it('shows a down arrow for lost places and no arrow or hint while there are too few rounds', () => {
    expect(legendRowsFor([withForm(rows[0], 1.6, -3)], 'pace')[0].value).toBe('101.6%  ▼3')
    const early = legendRowsFor([withForm(rows[0], 1.6, null)], 'pace')[0]
    expect(early.value).toBe('101.6%')
    expect(early.title).toBeUndefined()
  })

  it('leaves a team bare when the API sent no form (older API) or none for that tab', () => {
    expect(legendRowsFor(rows, 'pace')[0]).toEqual({ team: 'Alpine' })
    expect(legendRowsFor([withForm(rows[0], 1.6, 1)], 'quali')[0]).toEqual({ team: 'Alpine' })
  })

  it('orders cumulative by the weighted figure the legend shows, not the latest round', () => {
    const cum = (r: SeasonConstructorRow, weighted: number): SeasonConstructorRow => ({
      ...r,
      form: { cumulative: { weighted, rank_weighted: 1, rank_flat: 1, form_places: 0 } },
    })
    // Latest-round values say Alpine (0.4) leads Racing Bulls (0.7); the weighted figures say the reverse.
    expect(legendTeamOrder([cum(rows[0], 0.9), cum(rows[1], 0.2)], 'cumulative')).toEqual(['Racing Bulls', 'Alpine'])
  })
})
