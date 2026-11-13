import { describe, expect, it } from 'vitest'
import { anchorScroll, clampZoom, MAX_ZOOM, MIN_ZOOM, pinchZoom, stepZoom, wheelZoom } from './zoom'

describe('clampZoom / stepZoom', () => {
  it('stays inside 1x..5x', () => {
    expect(clampZoom(0.2)).toBe(MIN_ZOOM)
    expect(clampZoom(99)).toBe(MAX_ZOOM)
  })

  it('steps x1.5 and stops at the bounds', () => {
    expect(stepZoom(1, 1)).toBe(1.5)
    expect(stepZoom(1.5, 1)).toBeCloseTo(2.25)
    expect(stepZoom(4, 1)).toBe(MAX_ZOOM)
    expect(stepZoom(MAX_ZOOM, 1)).toBe(MAX_ZOOM)
    expect(stepZoom(1, -1)).toBe(MIN_ZOOM)
  })

  it('comes back to exactly 1 stepping out, with no float drift', () => {
    let z = 1
    for (let i = 0; i < 3; i++) z = stepZoom(z, 1)
    for (let i = 0; i < 3; i++) z = stepZoom(z, -1)
    expect(z).toBe(1)
  })
})

describe('stepZoom near 1x', () => {
  it('stepping out from just above 1.5x lands exactly on 1x, not on a stuck 1.01x', () => {
    // a pinch can leave 1.52x; 1.52 / 1.5 = 1.013 would keep the chart "zoomed" with a 5px scroll and an enabled Reset
    expect(stepZoom(1.52, -1)).toBe(1)
  })
})

describe('pinchZoom', () => {
  it('scales with the finger spread and clamps', () => {
    expect(pinchZoom(1, 100, 200)).toBe(2)
    expect(pinchZoom(2, 100, 50)).toBe(1)
    expect(pinchZoom(3, 100, 1000)).toBe(MAX_ZOOM)
  })

  it('ignores a degenerate starting distance', () => {
    expect(pinchZoom(2, 0, 80)).toBe(2)
  })
})

describe('wheelZoom', () => {
  it('zooms in on a negative delta (pinch out) and out on a positive one', () => {
    expect(wheelZoom(2, -10)).toBeGreaterThan(2)
    expect(wheelZoom(2, 10)).toBeLessThan(2)
  })

  it('caps one big mouse-wheel notch and normalises line-mode deltas', () => {
    expect(wheelZoom(1, -100)).toBeCloseTo(Math.exp(0.5)) // capped at 50px, not 100
    expect(wheelZoom(1, -3, 1)).toBeCloseTo(Math.exp(0.48)) // 3 lines = 48px
  })
})

describe('anchorScroll', () => {
  it('keeps the point under the focal position fixed when the content doubles', () => {
    // viewport 400 wide, content 1000 -> 2000, content point under the focal x=200 is at scroll+200 = 700 (70%)
    const next = anchorScroll(500, 200, 1000, 2000, 400)
    expect(next).toBe(0.7 * 2000 - 200)
  })

  it('lands on 0 when zooming back out to the viewport size', () => {
    expect(anchorScroll(800, 200, 2000, 400, 400)).toBe(0)
  })

  it('clamps to the end of the new content, never past it', () => {
    expect(anchorScroll(600, 399, 1000, 2000, 400)).toBeLessThanOrEqual(1600)
    expect(anchorScroll(0, 0, 1000, 2000, 400)).toBe(0)
  })

  it('clamps zooming OUT to the new, shorter range instead of scrolling past the end', () => {
    // content 2000 -> 1000, viewport 400, scrolled to the far end: the point under focal 0 maps to 800, but 600 is the max
    expect(anchorScroll(1600, 0, 2000, 1000, 400)).toBe(600)
  })

  it('never goes negative', () => {
    expect(anchorScroll(0, 300, 1000, 500, 400)).toBe(0)
  })

  it('leaves the scroll alone when there was no prior size', () => {
    expect(anchorScroll(40, 10, 0, 2000, 400)).toBe(40)
  })
})
