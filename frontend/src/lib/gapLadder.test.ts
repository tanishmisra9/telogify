import { describe, it, expect } from 'vitest'
import { gapCells, barFractions, axisTicks } from './gapLadder'

describe('gapCells', () => {
  it('labels the smallest value "best" and formats the rest as a gap to it', () => {
    expect(gapCells([0.5, 0.2, 0.9], (d) => `+${d.toFixed(3)}s`)).toEqual([
      '+0.300s',
      'best',
      '+0.700s',
    ])
  })
  it('carries nulls through as null', () => {
    expect(gapCells([0.2, null, 0.5], (d) => `+${d.toFixed(3)}s`)).toEqual(['best', null, '+0.300s'])
  })
  it('returns all null when nothing is present', () => {
    expect(gapCells([null, null], (d) => `+${d.toFixed(3)}s`)).toEqual([null, null])
  })
})

describe('barFractions', () => {
  it('gives the leader a zero-length bar and scales the rest to the worst gap', () => {
    const [a, b, c] = barFractions([0.5, 0.2, 0.9])
    expect(a).toBeCloseTo(3 / 7)
    expect(b).toBe(0)
    expect(c).toBe(1)
  })
  it('carries nulls through as null', () => {
    expect(barFractions([0.2, null, 0.5])).toEqual([0, null, 1])
  })
  it('returns all null when nothing is present', () => {
    expect(barFractions([null, null])).toEqual([null, null])
  })
  it('returns zero fractions when every present value is tied (no span)', () => {
    expect(barFractions([1.0, 1.0, 1.0])).toEqual([0, 0, 0])
  })
  it('handles a single row', () => {
    expect(barFractions([2.5])).toEqual([0])
  })
})

describe('axisTicks', () => {
  it('produces whole-second ticks from 0 to the floor of the max gap', () => {
    // Floored, not ceiled: a tick past the max gap would sit beyond where any bar reaches.
    expect(axisTicks(3.603)).toEqual([0, 1, 2, 3])
  })
  it('always includes at least the zero tick', () => {
    expect(axisTicks(0)).toEqual([0])
    expect(axisTicks(0.4)).toEqual([0])
  })
})
