import { describe, expect, it } from 'vitest'
import { qualiInsights } from '@/lib/qualiInsights'
import type { CarCharacterRow } from '@/lib/api'

function row(
  constructor: string,
  overrides: Partial<CarCharacterRow> = {},
): CarCharacterRow {
  return {
    constructor,
    driver: constructor.slice(0, 3).toUpperCase(),
    lap_time_s: 66.0,
    top_speed_kmh: 330,
    min_speed_kmh: 70,
    full_throttle_pct: 0.6,
    fastest_corner_kmh: 240,
    drag_label: 'balanced',
    is_top_speed_leader: false,
    is_corner_speed_leader: false,
    is_grip_leader: false,
    ...overrides,
  }
}

describe('qualiInsights', () => {
  it('returns empty for fewer than three teams', () => {
    expect(qualiInsights([row('A'), row('B')], 8)).toEqual([])
  })

  it('never returns two insights about the same team', () => {
    const rows = [
      row('Ferrari', { top_speed_kmh: 320, fastest_corner_kmh: 250, full_throttle_pct: 0.55, min_speed_kmh: 72 }),
      row('Red Bull', { top_speed_kmh: 332, fastest_corner_kmh: 238, full_throttle_pct: 0.62, min_speed_kmh: 68 }),
      row('McLaren', { top_speed_kmh: 326, fastest_corner_kmh: 236, full_throttle_pct: 0.54, min_speed_kmh: 74 }),
      row('Mercedes', { top_speed_kmh: 328, fastest_corner_kmh: 242, full_throttle_pct: 0.58, min_speed_kmh: 69 }),
    ]
    const out = qualiInsights(rows, 8)
    expect(out.length).toBeLessThanOrEqual(2)
    if (out.length === 2) expect(out[0].team).not.toBe(out[1].team)
  })

  it('prefers cross-channel aero trade over raw one-lap gap when trade is large', () => {
    const rows = [
      row('Ferrari', { lap_time_s: 66.5, top_speed_kmh: 315, fastest_corner_kmh: 255, full_throttle_pct: 0.58 }),
      row('Red Bull', { lap_time_s: 66.2, top_speed_kmh: 333, fastest_corner_kmh: 235, full_throttle_pct: 0.61 }),
      row('McLaren', { lap_time_s: 66.8, top_speed_kmh: 325, fastest_corner_kmh: 234, full_throttle_pct: 0.56 }),
      row('Mercedes', { lap_time_s: 66.4, top_speed_kmh: 328, fastest_corner_kmh: 242, full_throttle_pct: 0.59 }),
    ]
    const out = qualiInsights(rows, 8)
    expect(out.some((i) => i.kicker === 'Aero trade')).toBe(true)
    expect(out[0]?.kicker).toBe('Aero trade')
  })
})
