import { describe, expect, it } from 'vitest'
import {
  availableViews, flattenGroups, gainReach, planColumns, raceTip, gapAxis, groupByLapsDown, outCode, outLabel, raceLaps, signed, splitGains, statusGroups,
  stintLaps, strategySplit, tyreStyle,
} from './raceResults'
import type { ResultRow } from './api'

const row = (over: Partial<Omit<ResultRow, 'constructor'>>): ResultRow => ({
  position: 1, driver: 'NOR', constructor: 'McLaren', gap_label: 'leader', points: 25, strategy: 'M-H', ...over,
})

describe('availableViews', () => {
  it('offers strategy only on a degraded round with stints but no status', () => {
    expect(availableViews([row({ stints: [{ compound: 'MEDIUM', lap_start: 1, lap_end: 20 }] })])).toEqual(['strategy'])
  })
  it('offers finishers and places once any car has a status', () => {
    expect(availableViews([row({ status: 'Finished' })])).toEqual(['finishers', 'places'])
  })
  it('offers nothing when the API predates the fields', () => {
    expect(availableViews([row({})])).toEqual([])
    expect(availableViews([])).toEqual([])
  })
  it('treats an empty status string as no status', () => {
    expect(availableViews([row({ status: '' })])).toEqual([])
  })
})

describe('groupByLapsDown', () => {
  const r = (driver: string, status: string | null, laps_down: number | null = null) => row({ driver, status, laps_down })
  it('covers EVERY laps-down value up to the largest, including empty ones, finishing order inside', () => {
    const cols = groupByLapsDown([
      r('A', 'Finished'), r('B', 'Lapped', 4), r('C', 'Finished'), r('D', 'Lapped', 1), r('E', 'Lapped', 4), r('F', 'Lapped', 1),
    ])
    expect(cols.map((c) => [c.title, c.rows.map((x) => x.driver)])).toEqual([
      ['Lead lap', ['A', 'C']], ['+1 lap', ['D', 'F']], ['+2 laps', []], ['+3 laps', []], ['+4 laps', ['B', 'E']],
    ])
    expect(cols.map((c) => c.kind)).toEqual(['lead', 'lapped', 'lapped', 'lapped', 'lapped'])
  })
  it('never guesses: a lapped car with no laps-down gets its own trailing "Lapped" column', () => {
    const cols = groupByLapsDown([r('A', 'Finished'), r('B', 'Lapped', null), r('C', 'Lapped', 3)])
    expect(cols.map((c) => c.title)).toEqual(['Lead lap', '+1 lap', '+2 laps', '+3 laps', 'Lapped'])
  })
  it('leaves out retirees, DNS, DSQ and unknown status (they are out cars, not column cars)', () => {
    const cols = groupByLapsDown([r('A', 'Retired'), r('B', 'Did not start'), r('C', 'Disqualified'), r('D', null)])
    expect(cols).toEqual([])
  })
  it('keeps an empty lead column when only lapped cars finished, so the +N columns have their origin', () => {
    expect(groupByLapsDown([r('B', 'Lapped', 1)]).map((c) => [c.title, c.rows.length])).toEqual([['Lead lap', 0], ['+1 lap', 1]])
  })
})

describe('flattenGroups', () => {
  it('flattens groups to labelled rows, keeping group order and finishing order inside a group', () => {
    const g = statusGroups([row({ driver: 'A', status: 'Disqualified' }), row({ driver: 'B', status: 'Retired' }), row({ driver: 'E', status: 'Retired' })])
    expect(flattenGroups(g).map((o) => [o.row.driver, o.label])).toEqual([['B', 'DNF'], ['E', 'DNF'], ['A', 'DSQ']])
    expect(flattenGroups([])).toEqual([])
  })
})

describe('outCode / statusGroups', () => {
  it('labels the standard statuses DNF / DNS / DSQ and passes anything else through', () => {
    expect([outCode(row({ status: 'Retired' })), outCode(row({ status: 'Did not start' })), outCode(row({ status: 'Disqualified' })), outCode(row({ status: 'Excluded' })), outCode(row({ status: '' }))]).toEqual(['DNF', 'DNS', 'DSQ', 'Excluded', 'Out'])
  })
  it('orders DNF, DNS, DSQ first, then other labels, keeping finishing order inside a group', () => {
    const g = statusGroups([
      row({ driver: 'A', status: 'Disqualified' }), row({ driver: 'B', status: 'Retired' }), row({ driver: 'C', status: 'Excluded' }),
      row({ driver: 'D', status: 'Did not start' }), row({ driver: 'E', status: 'Retired' }),
    ])
    expect(g.map((x) => [x.label, x.rows.map((r) => r.driver)])).toEqual([['DNF', ['B', 'E']], ['DNS', ['D']], ['DSQ', ['A']], ['Excluded', ['C']]])
  })
  it('is empty with nothing out', () => {
    expect(statusGroups([])).toEqual([])
  })
})

describe('places view', () => {
  it('draws only cars with a served number; PL and no-grid finishers and DNF/DNS/DSQ are named in blocks', () => {
    const rows = [
      row({ driver: 'A', status: 'Finished', places_gained: 3 }),
      row({ driver: 'B', status: 'Finished', places_gained: -5 }),
      row({ driver: 'P', status: 'Lapped', places_gained: null, pit_lane: true }),
      row({ driver: 'N', status: 'Finished', places_gained: null }),
      row({ driver: 'R', status: 'Retired', places_gained: null }),
      row({ driver: 'S', status: 'Did not start' }),
    ]
    const { listed, blocks } = splitGains(rows)
    expect(listed.map((r) => r.driver)).toEqual(['A', 'B'])
    expect(blocks.map((b) => [b.label, b.rows.map((r) => r.driver)])).toEqual([['DNF', ['R']], ['DNS', ['S']], ['PL', ['P']], ['No grid', ['N']]])
    expect(gainReach(listed)).toBe(5)
  })
  it('keeps an axis when nothing moved or nothing is listed', () => {
    expect(gainReach([row({ places_gained: 0 })])).toBe(1)
    expect(gainReach([])).toBe(1)
  })
  it('signs the figure', () => {
    expect([signed(3), signed(-2), signed(0)]).toEqual(['+3', '-2', '0'])
  })
})

describe('strategySplit', () => {
  it('keeps finishers and retirees as bars; DNS, DSQ and other statuses go to names only', () => {
    const { bars, blocks } = strategySplit([
      row({ driver: 'A', status: 'Finished' }), row({ driver: 'B', status: 'Lapped' }), row({ driver: 'R', status: 'Retired' }),
      row({ driver: 'S', status: 'Did not start' }), row({ driver: 'Q', status: 'Disqualified' }), row({ driver: 'D', status: null }),
    ])
    expect(bars.map((r) => r.driver)).toEqual(['A', 'B', 'R', 'D']) // no status (degraded round) is never called out
    expect(blocks.map((b) => [b.label, b.rows.map((r) => r.driver)])).toEqual([['DNS', ['S']], ['DSQ', ['Q']]])
  })
})

describe('outLabel', () => {
  it('uses the API status and never invents a cause', () => {
    expect(outLabel(row({ status: 'Retired' }))).toBe('Retired')
    expect(outLabel(row({ status: null }))).toBe('No classification')
  })
})

describe('raceLaps / stintLaps', () => {
  it('is the furthest stint end, 0 with no stints', () => {
    expect(raceLaps([row({ stints: [{ compound: 'SOFT', lap_start: 1, lap_end: 20 }] }), row({ stints: [{ compound: null, lap_start: 21, lap_end: 57 }] })])).toBe(57)
    expect(raceLaps([row({})])).toBe(0)
  })
  it('counts both ends of a stint', () => {
    expect(stintLaps({ compound: 'HARD', lap_start: 1, lap_end: 20 })).toBe(20)
  })
})

describe('gapAxis', () => {
  it('covers the slowest gap with at most ~8 ticks, starting at 0', () => {
    for (const g of [0.4, 6, 23.4, 61, 140, 400]) {
      const a = gapAxis(g)
      expect(a.max).toBeGreaterThanOrEqual(g)
      expect(a.ticks[0]).toBe(0)
      expect(a.ticks.length).toBeLessThanOrEqual(9)
    }
  })
  it('is still drawable for a zero gap', () => {
    expect(gapAxis(0).max).toBeGreaterThan(0)
  })
  it('uses fewer ticks when the room is narrow, and the axis still covers the slowest gap', () => {
    const wide = gapAxis(44.15)
    const narrow = gapAxis(44.15, 2)
    expect(narrow.ticks.length).toBeLessThan(wide.ticks.length)
    expect(narrow.ticks.length - 1).toBeLessThanOrEqual(2)
    expect(narrow.max).toBeGreaterThanOrEqual(44.15)
  })
})

describe('tyreStyle', () => {
  it('maps known compounds, case-insensitively, to CSS tokens (so night mode can mute them), null for no data', () => {
    expect(tyreStyle('MEDIUM')?.letter).toBe('M')
    expect(tyreStyle('soft')?.letter).toBe('S')
    expect(tyreStyle('SOFT')?.fill).toBe('var(--tyre-soft)')
    expect(tyreStyle('WET')?.ink).toBe('var(--tyre-wet-ink)')
    expect(tyreStyle(null)).toBeNull()
    expect(tyreStyle('UNOBTAINIUM')).toBeNull()
  })
})

describe('raceTip', () => {
  // `team` stands in for `constructor`, which the shared `row` helper cannot take (it is also a built-in on objects)
  const car = (over: Partial<Omit<ResultRow, 'constructor'>> & { team?: string | null }): ResultRow => {
    const { team = 'Red Bull Racing', ...rest } = over
    return { ...row({ driver: 'VER', position: 6, status: 'Finished', grid: 20, places_gained: 14, gap_label: '+11.276s', gap_to_leader_s: 11.276, ...rest }), constructor: team } as ResultRow
  }

  it('is "Name, Team" then Started / Finished, the gap, and the places', () => {
    expect(raceTip(car({}), 'finishers')).toEqual({
      title: 'Max Verstappen, Red Bull Racing',
      lines: ['Started P20, Finished P6', '+11.276s', 'Gained 14 places'],
    })
  })
  it('shows the winner\'s total time as the gap and "Held position" for no change', () => {
    const t = raceTip(car({ driver: 'ANT', position: 1, grid: 1, places_gained: 0, gap_label: '1:28:15.758', gap_to_leader_s: 0 }), 'finishers')
    expect(t.lines).toEqual(['Started P1, Finished P1', '1:28:15.758', 'Held position'])
  })
  it('singular and plural places', () => {
    expect(raceTip(car({ places_gained: 1 }), 'places').lines.at(-1)).toBe('Gained 1 place')
    expect(raceTip(car({ places_gained: -1 }), 'places').lines.at(-1)).toBe('Lost 1 place')
    expect(raceTip(car({ places_gained: -3 }), 'places').lines.at(-1)).toBe('Lost 3 places')
  })
  it('a lapped car shows its laps down as the gap', () => {
    const t = raceTip(car({ status: 'Lapped', gap_label: '+2 Laps', gap_to_leader_s: null, laps_down: 2, position: 12, grid: 9, places_gained: -3 }), 'finishers')
    expect(t.lines).toEqual(['Started P9, Finished P12', '+2 Laps', 'Lost 3 places'])
  })
  it('a lapped car with a lapped gap shows laps down and its gap to the leader', () => {
    const t = raceTip(car({ status: 'Lapped', gap_label: '+1 Lap', gap_to_leader_s: null, laps_down: 1, lapped_gap_s: 95.167, position: 8, grid: 10, places_gained: 2 }), 'finishers')
    expect(t.lines).toEqual(['Started P10, Finished P8', '+1 Lap, +95.167s', 'Gained 2 places'])
  })
  it('PL replaces the start slot and there is no places line without a number', () => {
    const t = raceTip(car({ pit_lane: true, grid: null, places_gained: null }), 'places')
    expect(t.lines).toEqual(['Started PL, Finished P6', '+11.276s'])
  })
  it('a DNF has Started and Finished DNF, and no gap or places', () => {
    const t = raceTip(car({ status: 'Retired', position: 19, grid: 5, places_gained: null, gap_label: 'DNF', gap_to_leader_s: null }), 'finishers')
    expect(t.lines).toEqual(['Started P5, Finished DNF'])
  })
  it('DNS, DSQ and any other status are only that status, with no Started / Finished', () => {
    expect(raceTip(car({ status: 'Did not start', grid: 3 }), 'finishers').lines).toEqual(['Did not start'])
    expect(raceTip(car({ status: 'Disqualified', grid: 3 }), 'finishers').lines).toEqual(['Disqualified'])
    expect(raceTip(car({ status: 'Excluded' }), 'finishers').lines).toEqual(['Excluded'])
  })
  it('omits what is unknown instead of guessing: no grid means no Started', () => {
    const t = raceTip(car({ grid: null, places_gained: null }), 'finishers')
    expect(t.lines).toEqual(['Finished P6', '+11.276s'])
  })
  it('has no team part when the team is unknown', () => {
    expect(raceTip(car({ team: null }), 'finishers').title).toBe('Max Verstappen')
  })
  it('Strategy appends one line per stint, an unknown tyre named as such', () => {
    const t = raceTip(car({ stints: [{ compound: 'SOFT', lap_start: 1, lap_end: 31 }, { compound: null, lap_start: 32, lap_end: 40 }] }), 'strategy')
    expect(t.lines.slice(-2)).toEqual(['Soft: laps 1-31 (31)', 'No tyre data: laps 32-40 (9)'])
    expect(raceTip(car({ stints: [{ compound: 'SOFT', lap_start: 1, lap_end: 31 }] }), 'finishers').lines.some((l) => l.startsWith('Soft'))).toBe(false)
  })
})

describe('planColumns', () => {
  // Australia 2026: 6 on the lead lap, 7 at +1, 2 at +2, 1 at +3, and one car 15 laps down
  const r1 = () => {
    const mk = (d: number, n: number, tag: string) => Array.from({ length: n }, (_, i) => row({ driver: `${tag}${i}`, status: 'Lapped', laps_down: d }))
    return groupByLapsDown([...Array.from({ length: 6 }, (_, i) => row({ driver: `L${i}`, status: 'Finished' })), ...mk(1, 7, 'A'), ...mk(2, 2, 'B'), ...mk(3, 1, 'C'), ...mk(15, 1, 'D')])
  }
  const titles = (cols: ReturnType<typeof groupByLapsDown>) => cols.map((c) => c.title)
  const cars = (cols: ReturnType<typeof groupByLapsDown>) => cols.reduce((n, c) => n + c.rows.length, 0)

  it('shows the whole range when it fits, empties included', () => {
    expect(r1().length).toBe(16) // lead + 15 laps-down columns: the shape that failed
    const small = groupByLapsDown([row({ status: 'Finished' }), row({ driver: 'B', status: 'Lapped', laps_down: 1 }), row({ driver: 'C', status: 'Lapped', laps_down: 3 })])
    expect(titles(planColumns(small, 5))).toEqual(['Lead lap', '+1 lap', '+2 laps', '+3 laps'])
  })
  it('drops empty columns from the far end until it fits, keeping the lowest contiguous range', () => {
    expect(titles(planColumns(r1(), 4))).toEqual(['Lead lap', '+1 lap', '+2 laps', '+3 laps', '+15 laps'])
    // one more column of room keeps the LOWEST empty one (+4): empties go farthest-first
    expect(titles(planColumns(r1(), 5))).toEqual(['Lead lap', '+1 lap', '+2 laps', '+3 laps', '+4 laps', '+15 laps'])
  })
  it('merges the farthest columns when empties are not enough, and no car is lost', () => {
    const merged = planColumns(r1(), 3)
    expect(titles(merged)).toEqual(['Lead lap', '+1 lap', '+2 laps', '+3 or more'])
    expect(merged[3].showDown).toBe(true)
    expect(merged[3].rows.map((x) => x.driver)).toEqual(['C0', 'D0'])
    expect(cars(merged)).toBe(cars(r1()))
    expect(titles(planColumns(r1(), 1))).toEqual(['Lead lap', '+1 or more'])
    expect(cars(planColumns(r1(), 1))).toBe(cars(r1()))
  })
  it('stacking (capacity null) drops every empty band and keeps every car', () => {
    const p = planColumns(r1(), null)
    expect(titles(p)).toEqual(['Lead lap', '+1 lap', '+2 laps', '+3 laps', '+15 laps'])
    expect(cars(p)).toBe(cars(r1()))
  })
  it('leaves an unknown-laps "Lapped" column in place and merges it only as the last resort', () => {
    const cols = groupByLapsDown([row({ status: 'Finished' }), row({ driver: 'B', status: 'Lapped', laps_down: 1 }), row({ driver: 'U', status: 'Lapped', laps_down: null })])
    expect(titles(planColumns(cols, 2))).toEqual(['Lead lap', '+1 lap', 'Lapped'])
    const m = planColumns(cols, 1)
    expect(m[1].rows.map((x) => x.driver)).toEqual(['B', 'U'])
  })
})
