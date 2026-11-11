import { describe, it, expect } from 'vitest'
import { formArrow, formSentence, formatGap, legendValue, niceAxis, pointCopy } from './seasonStart'
import type { SeasonStartRow } from './api'

const row = (over: Partial<SeasonStartRow> = {}): SeasonStartRow => ({
  key: 'Ferrari',
  label: 'Ferrari',
  color_team: 'Ferrari',
  points: [],
  weighted_gap_pct: 3.44,
  flat_gap_pct: 3.95,
  rank_weighted: 2,
  rank_flat: 4,
  form_places: 2,
  n_rounds: 12,
  ...over,
})

describe('formatGap / formArrow', () => {
  it('formats a gap with a sign and one decimal', () => {
    expect(formatGap(3.444)).toBe('+3.4%')
    expect(formatGap(0)).toBe('+0.0%')
  })
  it('up, down, level, and nothing when there are too few rounds', () => {
    expect(formArrow(2)).toBe('▲2')
    expect(formArrow(-1)).toBe('▼1')
    expect(formArrow(0)).toBe('–')
    expect(formArrow(null)).toBe('')
  })
})

describe('legendValue', () => {
  it('combines the weighted gap and the arrow', () => {
    expect(legendValue(row())).toBe('+3.4%  ▲2')
  })
  it('drops the arrow when there is none, and is empty with no weighted gap', () => {
    expect(legendValue(row({ form_places: null }))).toBe('+3.4%')
    expect(legendValue(row({ weighted_gap_pct: null }))).toBe('')
  })
})

describe('niceAxis', () => {
  it('always reaches the data in whole steps starting at 0', () => {
    expect(niceAxis(3.1)).toEqual({ max: 4, ticks: [0, 2, 4] })
    expect(niceAxis(11.5)).toEqual({ max: 12, ticks: [0, 2, 4, 6, 8, 10, 12] })
    expect(niceAxis(18.6)).toEqual({ max: 20, ticks: [0, 5, 10, 15, 20] })
    expect(niceAxis(41)).toEqual({ max: 50, ticks: [0, 10, 20, 30, 40, 50] })
  })
  it('never collapses to a zero-height axis', () => {
    expect(niceAxis(0)).toEqual({ max: 2, ticks: [0, 2] })
  })
})

describe('pointCopy', () => {
  const p = { round: 6, metric: 100 as const, gap_pct: 2.34, gap_s: 0.07, n_cars: 1 }
  it('names the metric fallback and a single car honestly', () => {
    const c = pointCopy('Ferrari', 'Monaco Grand Prix', p)
    expect(c.title).toBe('Ferrari, Monaco Grand Prix')
    expect(c.lines).toEqual(['2.3% behind the best (+0.07 s)', '0 to 100 km/h only this round', '1 car'])
  })
  it('the round leader is called the best start; a full-run round says so', () => {
    const c = pointCopy('Ferrari', undefined, { ...p, metric: 200, gap_pct: 0, gap_s: 0, n_cars: 2 })
    expect(c.title).toBe('Ferrari, round 6')
    expect(c.lines).toEqual(['Best start of the round', 'Full run, 0 to 200 km/h'])
  })
})

describe('formSentence', () => {
  it('says what the arrow means, with both ranks', () => {
    expect(formSentence(row())).toBe('Gains 2 places on recent form: #2 recently, #4 over the season')
    expect(formSentence(row({ form_places: -1, rank_weighted: 5, rank_flat: 4 }))).toBe(
      'Loses 1 place on recent form: #5 recently, #4 over the season',
    )
    expect(formSentence(row({ form_places: 0, rank_weighted: 3, rank_flat: 3 }))).toBe(
      'Holds the same place on recent form: #3 recently, #3 over the season',
    )
  })
  it('is null when there is no form to report', () => {
    expect(formSentence(row({ form_places: null }))).toBeNull()
  })
})
