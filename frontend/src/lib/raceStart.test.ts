import { describe, it, expect } from 'vitest'
import {
  aggregateRows,
  axisMax,
  fmtSeconds,
  median,
  rowTotal,
  secondTicks,
  segmentFractions,
  sortRows,
  type PuGroupDef,
  type StartRow,
} from './raceStart'

const row = (a: number, b: number | null, v: number | null = 150): StartRow => ({
  driver: 'HAM',
  constructor: 'Ferrari',
  t_0_100_s: a,
  t_100_200_s: b == null ? null : b - a,
  t_0_200_s: b,
  v_75m_kmh: v,
  compound: 'M',
})

describe('rowTotal / axisMax', () => {
  it('uses 0-200 on a 200 round', () => {
    expect(rowTotal(row(2.4, 4.5), 200)).toBe(4.5)
    expect(axisMax([row(2.4, 4.5), row(3.0, 5.5), row(2.7, 4.9)], 200)).toBe(5.5)
  })
  it('uses 0-100 on a 100-only round', () => {
    expect(rowTotal(row(2.4, null), 100)).toBe(2.4)
    expect(axisMax([row(2.4, null), row(3.1, null)], 100)).toBe(3.1)
  })
  it('is 0 for no rows', () => {
    expect(axisMax([], 200)).toBe(0)
  })
})

describe('segmentFractions', () => {
  it('splits a bar into its two segments on the shared axis', () => {
    const { first, second } = segmentFractions(row(2.5, 5), 5)
    expect(first).toBeCloseTo(0.5)
    expect(second).toBeCloseTo(0.5)
  })
  it('the slowest row fills the axis exactly', () => {
    const { first, second } = segmentFractions(row(3, 5.5), 5.5)
    expect(first + second).toBeCloseTo(1)
  })
  it('a 100-only row is a single segment', () => {
    expect(segmentFractions(row(2.8, null), 3.4)).toEqual({ first: 2.8 / 3.4, second: 0 })
  })
  it('guards a zero axis', () => {
    expect(segmentFractions(row(2.5, 5), 0)).toEqual({ first: 0, second: 0 })
  })
})

describe('secondTicks', () => {
  it('floors so no tick passes the axis end', () => {
    expect(secondTicks(5.5)).toEqual([0, 1, 2, 3, 4, 5])
  })
  it('is just [0] for an empty axis', () => {
    expect(secondTicks(0)).toEqual([0])
  })
})

describe('fmtSeconds', () => {
  it('shows two decimals', () => {
    expect(fmtSeconds(2.4)).toBe('2.40')
  })
})


const car = (driver: string, team: string, a: number, b: number | null, v: number | null = 150): StartRow => ({
  ...row(a, b, v),
  driver,
  constructor: team,
})

const PU: PuGroupDef[] = [
  { name: 'Mercedes', works_team: 'Mercedes', teams: ['Mercedes', 'McLaren'] },
  { name: 'Honda', works_team: 'Aston Martin', teams: ['Aston Martin'] },
]

describe('median', () => {
  it('handles odd, even and empty', () => {
    expect(median([3, 1, 2])).toBe(2)
    expect(median([1, 2, 3, 10])).toBe(2.5)
    expect(median([])).toBeNull()
  })
})

describe('aggregateRows', () => {
  const rows = [
    car('RUS', 'Mercedes', 2.4, 4.5, 156),
    car('ANT', 'Mercedes', 2.6, 4.7, 158),
    car('NOR', 'McLaren', 2.5, 4.6, 154),
    car('PIA', 'McLaren', 2.5, 4.8, 152),
    car('ALO', 'Aston Martin', 2.8, 5.3, 140),
  ]

  it('teams: the median of a two-car team is its mean; sorted fastest first', () => {
    const g = aggregateRows(rows, 'teams', PU, 200)
    expect(g.map((x) => x.key)).toEqual(['Mercedes', 'McLaren', 'Aston Martin'])
    expect(g[0].t_0_100_s).toBeCloseTo(2.5)
    expect(g[0].t_0_200_s).toBeCloseTo(4.6)
    expect(g[0].n).toBe(2)
    expect(g[0].v_75m_kmh).toBeCloseTo(157)
  })

  it('the 100-200 segment is median(0-200) minus median(0-100), so the bar ends at the median total', () => {
    const [m] = aggregateRows(rows, 'teams', PU, 200)
    expect(m.t_0_100_s + (m.t_100_200_s as number)).toBeCloseTo(m.t_0_200_s as number)
  })

  it('power units pool every supplied team and take the works team colour', () => {
    const g = aggregateRows(rows, 'pu', PU, 200)
    const merc = g.find((x) => x.key === 'Mercedes')!
    expect(merc.n).toBe(4)
    expect(merc.t_0_200_s).toBeCloseTo(4.65) // median of 4.5, 4.7, 4.6, 4.8
    expect(g.find((x) => x.key === 'Honda')!.colorTeam).toBe('Aston Martin')
  })

  it('one outlier cannot drag a pooled median the way a mean would', () => {
    const pool = [
      car('A', 'Mercedes', 2.5, 4.6),
      car('B', 'Mercedes', 2.5, 4.6),
      car('C', 'McLaren', 2.5, 4.6),
      car('D', 'McLaren', 3.0, 7.9), // stalled
    ]
    const [m] = aggregateRows(pool, 'pu', PU, 200)
    expect(m.t_0_200_s).toBeCloseTo(4.6)
  })

  it('a team missing from the supply map is left out of power units, not guessed', () => {
    const g = aggregateRows([...rows, car('XXX', 'Brand New', 2.7, 5.0)], 'pu', PU, 200)
    expect(g.some((x) => x.key === 'Brand New')).toBe(false)
  })

  it('a 100-only round has no 0-200 or split', () => {
    const g = aggregateRows([car('A', 'Mercedes', 2.5, null), car('B', 'Mercedes', 2.7, null)], 'teams', PU, 100)
    expect(g[0].t_0_200_s).toBeNull()
    expect(g[0].t_100_200_s).toBeNull()
    expect(g[0].t_0_100_s).toBeCloseTo(2.6)
  })

  it('km/h is the median of the cars that have one, null when none do', () => {
    const g = aggregateRows([car('A', 'Mercedes', 2.5, 4.6, null), car('B', 'Mercedes', 2.6, 4.7, 160)], 'teams', PU, 200)
    expect(g[0].v_75m_kmh).toBe(160)
    const none = aggregateRows([car('A', 'Mercedes', 2.5, 4.6, null)], 'teams', PU, 200)
    expect(none[0].v_75m_kmh).toBeNull()
  })
})


describe('sortRows', () => {
  // A: quick launch, slow second leg. B: slow launch, quick second leg.
  const A = car('A', 'X', 2.4, 4.8)
  const B = car('B', 'Y', 2.7, 4.7)
  const C = car('C', 'Z', 2.5, 4.6)

  it('total: fastest to 200 first', () => {
    expect(sortRows([A, B, C], 'total', 200).map((r) => r.driver)).toEqual(['C', 'B', 'A'])
  })
  it('first: fastest 0-100 first', () => {
    expect(sortRows([A, B, C], 'first', 200).map((r) => r.driver)).toEqual(['A', 'C', 'B'])
  })
  it('second: fastest 100-200 first', () => {
    // 100-200: A 2.4, B 2.0, C 2.1
    expect(sortRows([A, B, C], 'second', 200).map((r) => r.driver)).toEqual(['B', 'C', 'A'])
  })
  it('a row without the metric goes last, and the input is not mutated', () => {
    const none = car('N', 'W', 2.0, null)
    const input = [none, A, B]
    expect(sortRows(input, 'second', 200).map((r) => r.driver)).toEqual(['B', 'A', 'N'])
    expect(input.map((r) => r.driver)).toEqual(['N', 'A', 'B'])
  })
  it('ties fall back to the total, whatever the input order', () => {
    const t1 = car('T1', 'X', 2.5, 4.9)
    const t2 = car('T2', 'Y', 2.5, 4.6)
    expect(sortRows([t1, t2], 'first', 200).map((r) => r.driver)).toEqual(['T2', 'T1'])
    expect(sortRows([t2, t1], 'first', 200).map((r) => r.driver)).toEqual(['T2', 'T1'])
  })
  it('on a 100-only round the total is the 0-100 time', () => {
    const a = car('a', 'X', 2.9, null)
    const b = car('b', 'Y', 2.6, null)
    expect(sortRows([a, b], 'total', 100).map((r) => r.driver)).toEqual(['b', 'a'])
  })
})
