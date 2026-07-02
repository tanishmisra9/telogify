import { describe, it, expect } from 'vitest'
import { summarizeCarCharacter } from './qualiSummary'
import type { CarCharacterRow } from '@/lib/api'

function row(over: Partial<CarCharacterRow>): CarCharacterRow {
  return {
    constructor: 'Team',
    driver: 'DRV',
    lap_time_s: 90,
    top_speed_kmh: 320,
    min_speed_kmh: 100,
    full_throttle_pct: 0.7,
    fastest_corner_kmh: 200,
    drag_label: 'balanced',
    is_top_speed_leader: false,
    is_corner_speed_leader: false,
    is_grip_leader: false,
    ...over,
  }
}

describe('summarizeCarCharacter', () => {
  it('calls the first row the quickest of the compared teams', () => {
    const [line] = summarizeCarCharacter([row({ constructor: 'Ferrari', driver: 'LEC' })])
    expect(line).toContain('Ferrari (LEC)')
    expect(line).toContain('quickest of the compared teams')
  })

  it('picks a single standout trait by priority for non-leaders', () => {
    const rows = [
      row({}),
      row({ constructor: 'Merc', driver: 'RUS', is_top_speed_leader: true, is_grip_leader: true }),
    ]
    // top speed outranks grip in the priority order
    expect(summarizeCarCharacter(rows)[1]).toBe('Merc (RUS): best top speed.')
  })

  it('has a neutral fallback when nothing stands out', () => {
    const rows = [row({}), row({ constructor: 'Mid', driver: 'MID' })]
    expect(summarizeCarCharacter(rows)[1]).toBe('Mid (MID): no standout strength or weakness this session.')
  })
})
