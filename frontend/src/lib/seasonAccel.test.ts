import { describe, it, expect } from 'vitest'
import { binBySpeed } from './seasonAccel'

describe('binBySpeed', () => {
  it('groups points into speed bins and takes the median accel per bin', () => {
    const points: [number, number][] = [
      [201, 5.0],
      [205, 7.0],
      [209, 6.0], // same 10-wide bin (200-209) -> median 6.0
      [301, 1.0],
      [308, -1.0], // bin 300-309 -> median 0.0
    ]
    const bins = binBySpeed(points, 10)
    expect(bins).toEqual([
      { speedMid: 205, medianAccel: 6.0, n: 3 },
      { speedMid: 305, medianAccel: 0.0, n: 2 },
    ])
  })

  it('returns empty for no points', () => {
    expect(binBySpeed([])).toEqual([])
  })

  it('sorts bins ascending by speed regardless of input order', () => {
    const points: [number, number][] = [
      [300, 1.0],
      [200, 5.0],
    ]
    const bins = binBySpeed(points, 10)
    expect(bins.map((b) => b.speedMid)).toEqual([205, 305])
  })
})
