import { describe, expect, it } from 'vitest'
import { paceAxis, splitOutliers } from './paceAxis'

const col = (whisker_low: number, whisker_high: number, outliers: number[] = []) => ({ whisker_low, whisker_high, outliers })

describe('paceAxis', () => {
  it('is bounded by the whiskers, not by a far outlier (a 30s safety-car lap no longer squashes every box)', () => {
    const a = paceAxis([col(74, 78, [85.4]), col(74.5, 77.5, [79])])
    expect(a.yMax).toBeLessThan(82) // the 85.4 lap is clipped, not plotted to scale
    expect(a.yMax).toBeGreaterThan(79) // the 79 lap, within the margin, is still on the scale
    expect(a.yMin).toBeLessThan(74)
  })
  it('still plots a near outlier to scale', () => {
    const a = paceAxis([col(74, 78, [79.5])])
    expect(a.yMax).toBeGreaterThanOrEqual(79.5)
    expect(splitOutliers([79.5], a).inside).toEqual([79.5])
  })
  it('splits outliers into shown and clipped, and loses none', () => {
    const a = paceAxis([col(74, 78)])
    const s = splitOutliers([70, 73, 79, 90, 120], a)
    expect(s.inside.length + s.slower + s.faster).toBe(5)
    expect(s).toMatchObject({ slower: 2, faster: 1 }) // 90 and 120 slower, 70 faster
    expect(s.inside).toEqual([73, 79])
  })
  it('the cap is exact: an outlier on it is shown, one a hair past it is clipped', () => {
    const a = paceAxis([col(74, 78)])
    expect(splitOutliers([a.capHi], a).slower).toBe(0)
    expect(splitOutliers([a.capHi + 0.001], a).slower).toBe(1)
  })
  it('has an axis with no columns, and with identical whiskers', () => {
    expect(paceAxis([])).toMatchObject({ yMin: 0, yMax: 1 })
    const a = paceAxis([col(75, 75)])
    expect(a.yMax).toBeGreaterThan(a.yMin)
  })
})
