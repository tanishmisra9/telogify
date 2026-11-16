import { describe, expect, it } from 'vitest'
import { canSwitchGap, gapText } from './finishing'
import type { ResultRow } from './api'

const row = (over: Partial<Omit<ResultRow, 'constructor'>>): ResultRow => ({
  position: 2,
  driver: 'LEC',
  constructor: 'Ferrari',
  gap_label: '+2.5s',
  points: 18,
  strategy: 'M-H',
  gap_to_leader_s: 2.456,
  interval_s: 2.456,
  ...over,
})

describe('gapText', () => {
  it('keeps the winner total time in both modes', () => {
    const w = row({ position: 1, gap_label: '1:32:05.123', gap_to_leader_s: 0, interval_s: null })
    expect(gapText(w, 'leader')).toBe('1:32:05.123')
    expect(gapText(w, 'ahead')).toBe('1:32:05.123')
  })

  it('shows seconds to the leader or to the car ahead, to the millisecond', () => {
    const r = row({ position: 3, gap_to_leader_s: 5.0, interval_s: 2.544 })
    expect(gapText(r, 'leader')).toBe('+5.000s')
    expect(gapText(r, 'ahead')).toBe('+2.544s')
  })

  it('never invents seconds for a lapped or retired car', () => {
    for (const label of ['+1 Lap', '+3 Laps', 'DNF', 'DNS']) {
      const r = row({ gap_label: label, gap_to_leader_s: null, interval_s: null })
      expect(gapText(r, 'leader')).toBe(label)
      expect(gapText(r, 'ahead')).toBe(label)
    }
  })

  it('shows a dash, not the gap to the leader, when the car ahead has no time', () => {
    expect(gapText(row({ gap_to_leader_s: 9.0, interval_s: null }), 'ahead')).toBe('–')
  })

  it('falls back to the label on an API that predates the numeric fields', () => {
    expect(gapText(row({ gap_to_leader_s: undefined, interval_s: undefined }), 'leader')).toBe('+2.5s')
  })
})

describe('canSwitchGap', () => {
  it('needs at least one interval', () => {
    expect(canSwitchGap([row({}), row({ interval_s: null })])).toBe(true)
    expect(canSwitchGap([row({ interval_s: null })])).toBe(false)
    expect(canSwitchGap([row({ interval_s: undefined })])).toBe(false)
    expect(canSwitchGap([])).toBe(false)
  })
})
