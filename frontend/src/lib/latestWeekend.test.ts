import { describe, expect, it } from 'vitest'
import { latestWeekendPath } from './api'

const w = (year: number, round: number) => ({
  id: year * 100 + round,
  year,
  round,
  event_name: 'Grand Prix',
  circuit_name: 'Circuit',
  country: 'Country',
  race_laps: null,
})

describe('latestWeekendPath', () => {
  it('takes the last row, since /weekends is ordered (year, round) ascending', () => {
    expect(latestWeekendPath([w(2026, 1), w(2026, 7), w(2026, 12)])).toBe('/weekends/2026/12')
  })

  it('crosses a season boundary rather than picking the highest round', () => {
    expect(latestWeekendPath([w(2025, 24), w(2026, 3)])).toBe('/weekends/2026/3')
  })

  it('falls back to the index while loading or when nothing is ingested', () => {
    expect(latestWeekendPath(null)).toBe('/weekends')
    expect(latestWeekendPath(undefined)).toBe('/weekends')
    expect(latestWeekendPath([])).toBe('/weekends')
  })
})
