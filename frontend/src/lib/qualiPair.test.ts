import { describe, expect, it } from 'vitest'
import { pickerRows, pickerTimeLabel, resolveSelection, sameSet, teamOptions, toggleDriver, type PickerRow } from '@/lib/qualiPair'

describe('toggleDriver', () => {
  it('adds up to two and ignores a third', () => {
    expect(toggleDriver([], 'VER')).toEqual(['VER'])
    expect(toggleDriver(['VER'], 'NOR')).toEqual(['VER', 'NOR'])
    expect(toggleDriver(['VER', 'NOR'], 'LEC')).toEqual(['VER', 'NOR'])
  })
  it('removes a picked driver', () => {
    expect(toggleDriver(['VER', 'NOR'], 'VER')).toEqual(['NOR'])
    expect(toggleDriver(['VER'], 'VER')).toEqual([])
  })
})

describe('resolveSelection', () => {
  it('shows the fallback until something is picked, and keeps an emptied pick empty', () => {
    expect(resolveSelection(null, ['A', 'B'], ['A', 'B'])).toEqual(['A', 'B'])
    expect(resolveSelection([], ['A', 'B'], ['A', 'B'])).toEqual([])
  })
  it('drops drivers the data no longer carries', () => {
    expect(resolveSelection(['A', 'Z'], ['A', 'B'], ['A', 'B'])).toEqual(['A'])
  })
})

describe('sameSet', () => {
  it('ignores order', () => {
    expect(sameSet(['A', 'B'], ['B', 'A'])).toBe(true)
    expect(sameSet(['A'], ['A', 'B'])).toBe(false)
  })
})

const row = (driver: string, constructor: string | null, position: number | null, time_s: number | null, plottable: boolean): PickerRow => ({
  driver, constructor, position, time_s, plottable,
})

describe('teamOptions', () => {
  it('orders teams by best position and pairs their two plottable drivers', () => {
    const opts = teamOptions([
      row('NOR', 'McLaren', 3, 90, true),
      row('RUS', 'Mercedes', 1, 88, true),
      row('PIA', 'McLaren', 5, 91, true),
      row('ANT', 'Mercedes', 2, 89, true),
    ])
    expect(opts.map((o) => [o.team, o.codes, o.blocked, o.bestPosition])).toEqual([
      ['Mercedes', ['RUS', 'ANT'], null, 1],
      ['McLaren', ['NOR', 'PIA'], null, 3],
    ])
  })
  it('blocks a team by why a driver is missing: no trace vs no time vs only one ran', () => {
    const opts = teamOptions([
      row('OCO', 'Haas F1 Team', 12, 90.3, false),
      row('BEA', 'Haas F1 Team', 18, 91, true),
      row('STR', 'Aston Martin', null, null, false),
      row('ALO', 'Aston Martin', 21, 92, true),
      row('BOT', 'Audi', 20, 93, true),
    ])
    const by = Object.fromEntries(opts.map((o) => [o.team, o]))
    expect(by['Haas F1 Team'].blocked).toBe('Ocon: no trace')
    expect(by['Aston Martin'].blocked).toBe('Stroll: no time')
    expect(by['Audi'].blocked).toBe('Only Bottas ran')
    expect(by['Audi'].codes).toEqual([])
  })
  it('skips drivers with no team', () => {
    expect(teamOptions([row('XXX', null, 1, 90, true)])).toEqual([])
  })
})

describe('pickerTimeLabel', () => {
  it('shows P1 as an absolute time', () => {
    expect(pickerTimeLabel(88, 88, true)).toBe('88.000s')
  })
  it('shows a slower row as a positive delta to pole', () => {
    expect(pickerTimeLabel(88.433, 88, false)).toBe('+0.433s')
  })
  it('shows a row actually faster than pole as a negative delta', () => {
    expect(pickerTimeLabel(87.9, 88, false)).toBe('-0.100s')
  })
  it('falls back to an absolute time when pole has no time', () => {
    expect(pickerTimeLabel(88, null, false)).toBe('88.000s')
  })
  it('returns null when the row has no time', () => {
    expect(pickerTimeLabel(null, 88, false)).toBe(null)
  })
})

describe('pickerRows', () => {
  it('merges plottable and unavailable drivers by position, unclassified last', () => {
    const rows = pickerRows(
      [{ driver: 'A', constructor: 'T', position: 2, lap_time_s: 90 } as never, { driver: 'C', constructor: 'T', position: 1, lap_time_s: 89 } as never],
      [{ driver: 'B', constructor: 'T', position: null, best_lap_s: null }, { driver: 'D', constructor: 'T', position: 3, best_lap_s: 91 }],
    )
    expect(rows.map((r) => [r.driver, r.plottable])).toEqual([['C', true], ['A', true], ['D', false], ['B', false]])
  })
})
