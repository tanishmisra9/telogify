import { describe, expect, it } from 'vitest'
import { formatLap, formatTick, timeAxis } from './qualiSegments'

describe('formatLap', () => {
  it('formats minutes and milliseconds', () => {
    expect(formatLap(87.452)).toBe('1:27.452')
    expect(formatLap(61.5)).toBe('1:01.500')
  })
  it('rolls a rounding carry into the minute instead of printing 60.000', () => {
    expect(formatLap(59.9996)).toBe('1:00.000')
  })
})

describe('timeAxis', () => {
  it('is null with nothing to place', () => {
    expect(timeAxis([])).toBeNull()
  })
  it('snaps outward to the step and includes both end ticks', () => {
    const a = timeAxis([78.52, 79.1, 80.9])!
    expect(a.step).toBe(0.5)
    expect(a.min).toBe(78.5)
    expect(a.max).toBe(81)
    expect(a.ticks[0]).toBe(78.5)
    expect(a.ticks[a.ticks.length - 1]).toBe(81)
  })
  it('widens the step for a long spread so ticks stay readable', () => {
    expect(timeAxis([78, 84])!.step).toBe(1)
    expect(timeAxis([78, 90])!.step).toBe(2)
  })
  it('still draws when every time is identical', () => {
    const a = timeAxis([80, 80])!
    expect(a.max).toBeGreaterThan(a.min)
  })
  it('keeps every input time inside the axis', () => {
    const times = [78.51, 79.9, 82.77, 83.01]
    const a = timeAxis(times)!
    expect(a.min).toBeLessThanOrEqual(Math.min(...times))
    expect(a.max).toBeGreaterThanOrEqual(Math.max(...times))
  })
})

describe('formatTick', () => {
  it('reads whole seconds as m:ss and half seconds with a decimal', () => {
    expect(formatTick(87, 1)).toBe('1:27')
    expect(formatTick(87.5, 0.5)).toBe('1:27.5')
    expect(formatTick(78.5, 0.5)).toBe('1:18.5')
  })
})
