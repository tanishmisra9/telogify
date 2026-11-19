import { describe, expect, it } from 'vitest'
import { BAND_GAP, ROW_H, STRIP_H, TOUCH_ROW_H, columnWidths, labelSide, maxLappedColumns, rowHeight, layoutBands, scaleLinear, staircaseStep } from './ladder'

describe('layoutBands', () => {
  it('stacks bands with a header strip each and a gap between, no trailing gap', () => {
    const { bands, height } = layoutBands([2, 3], 10)
    expect(bands[0]).toEqual({ top: 10, rowsTop: 10 + STRIP_H, height: STRIP_H + 2 * ROW_H })
    expect(bands[1].top).toBe(10 + STRIP_H + 2 * ROW_H + BAND_GAP)
    expect(height).toBe(bands[1].top + bands[1].height)
  })
  it('lets a band take its own header height, and stacks the next band from it', () => {
    const { bands, height } = layoutBands([1, 1], 0, [14, STRIP_H])
    expect(bands[0]).toEqual({ top: 0, rowsTop: 14, height: 14 + ROW_H })
    expect(bands[1].top).toBe(14 + ROW_H + BAND_GAP)
    expect(bands[1].rowsTop).toBe(bands[1].top + STRIP_H)
    expect(height).toBe(bands[1].top + STRIP_H + ROW_H)
  })
  it('handles no bands and an empty band', () => {
    expect(layoutBands([], 5)).toEqual({ bands: [], height: 5 })
    expect(layoutBands([0]).bands[0].height).toBe(STRIP_H)
  })
})

describe('scaleLinear', () => {
  it('maps the domain ends to the range ends', () => {
    const f = scaleLinear(80, 90, 0, 100)
    expect([f(80), f(85), f(90)]).toEqual([0, 50, 100])
  })
  it('does not divide by zero on a flat domain', () => {
    expect(scaleLinear(5, 5, 0, 100)(5)).toBe(50)
  })
})

describe('labelSide', () => {
  it('goes right when it fits, left when only the left fits', () => {
    expect(labelSide(10, 26, 100, 400)).toBe('right')
    expect(labelSide(300, 26, 100, 400)).toBe('left')
  })
  it('picks the roomier side when neither fits, and never throws', () => {
    expect(labelSide(60, 26, 500, 400)).toBe('right')
    expect(labelSide(200, 26, 500, 300)).toBe('left')
  })
  it('is exact at the boundary: room right of 160 keeps a 160 label right and flips a 161 one left', () => {
    // x=200, carW=26, gap=6, pad=8, width=400 -> roomRight = 400 - 8 - 232 = 160, roomLeft = 186
    expect(labelSide(200, 26, 160, 400)).toBe('right')
    expect(labelSide(200, 26, 161, 400)).toBe('left')
  })
})

describe('columnWidths', () => {
  it('fits columns of different kinds side by side and the widths add up to the available width', () => {
    const w = columnWidths(1280, ['lead', 'lapped', 'lapped', 'lapped', 'lapped', 'out'])!
    expect(w).not.toBeNull()
    expect(w.reduce((a, b) => a + b, 0)).toBeCloseTo(1280 - 32)
    expect(w[0]).toBeGreaterThan(w[1]) // the lead column (real gaps, long figure) is the widest
    expect(w[5]).toBeLessThan(w[1]) // the out column is the narrowest
  })
  it('is null when the minimums do not fit (the caller stacks), exact at the boundary', () => {
    const kinds = ['lead', 'lapped', 'out'] as const
    const need = 300 + 150 + 96 + 32
    expect(columnWidths(need, [...kinds])).not.toBeNull()
    expect(columnWidths(need - 1, [...kinds])).toBeNull()
  })
  it('needs more room for more laps down: a +5 race stacks where a +2 race fits', () => {
    expect(columnWidths(900, ['lead', 'lapped', 'lapped', 'out'])).not.toBeNull()
    expect(columnWidths(900, ['lead', 'lapped', 'lapped', 'lapped', 'lapped', 'lapped', 'out'])).toBeNull()
  })
  it('has nothing to fit with no columns', () => {
    expect(columnWidths(1200, [])).toBeNull()
  })
})

describe('staircaseStep', () => {
  it('is 0 for one row, clamped to the min and max step otherwise', () => {
    expect(staircaseStep(1, 100)).toBe(0)
    expect(staircaseStep(30, 40)).toBe(3)
    expect(staircaseStep(12, 40)).toBeCloseTo(40 / 11)
    expect(staircaseStep(3, 1000)).toBe(16)
    expect(staircaseStep(5, 40)).toBe(10)
  })
})

describe('maxLappedColumns', () => {
  it('counts the laps-down columns that fit beside the lead lap and the out column', () => {
    expect(maxLappedColumns(1280, true)).toBe(5) // (1248 - 300 - 96) / 150 = 5.68
    expect(maxLappedColumns(1280, false)).toBe(6)
    expect(maxLappedColumns(500, true)).toBe(0) // too narrow for even one: stack
  })
  it('agrees with columnWidths: capacity lapped columns fit, one more does not', () => {
    for (const w of [900, 1100, 1280, 1500]) {
      const n = maxLappedColumns(w, true)
      expect(columnWidths(w, ['lead', ...Array(n).fill('lapped'), 'out'])).not.toBeNull()
      expect(columnWidths(w, ['lead', ...Array(n + 1).fill('lapped'), 'out'])).toBeNull()
    }
  })
})

describe('touch row height', () => {
  it('is taller for a finger than for a cursor, and layoutBands honours it', () => {
    expect(rowHeight(true)).toBe(ROW_H)
    expect(rowHeight(false)).toBe(TOUCH_ROW_H)
    expect(TOUCH_ROW_H).toBeGreaterThan(ROW_H)
    const { bands, height } = layoutBands([3], 10, undefined, TOUCH_ROW_H)
    expect(bands[0].height).toBe(STRIP_H + 3 * TOUCH_ROW_H)
    expect(height).toBe(10 + STRIP_H + 3 * TOUCH_ROW_H)
  })
})
