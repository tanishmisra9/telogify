import { describe, expect, it } from 'vitest'
import { placeBubble } from './placeBubble'

const view = { w: 390, h: 800, scrollX: 0, scrollY: 0 }
const anchor = (left: number, top: number, w = 40, h = 20) => ({ left, top, right: left + w, bottom: top + h })
const size = { w: 200, h: 50 }

describe('placeBubble horizontal', () => {
  it('centers on the anchor when it fits', () => {
    // anchor center 150, bubble 200 wide -> left 50
    expect(placeBubble(anchor(130, 100), size, view).left).toBe(50)
  })

  it('left- and right-anchors on request', () => {
    expect(placeBubble(anchor(130, 100), size, view, 'start').left).toBe(130)
    // right edge of the anchor (340) minus the bubble width (200) fits; the same at x=130 would go negative and clamps to 8
    expect(placeBubble(anchor(300, 100), size, view, 'end').left).toBe(140)
    expect(placeBubble(anchor(130, 100), size, view, 'end').left).toBe(8)
  })

  it('is clamped 8px inside both viewport edges (the phone overflow)', () => {
    // anchor at the far right: centering would put the bubble past 390
    const r = placeBubble(anchor(350, 100), size, view)
    expect(r.left + size.w).toBeLessThanOrEqual(view.w - 8)
    expect(r.left).toBe(390 - 8 - 200)
    // anchor at the far left: centering would go negative
    expect(placeBubble(anchor(0, 100), size, view).left).toBe(8)
  })

  it('stays inside the viewport after the page has scrolled sideways, in document coordinates', () => {
    const v = { ...view, scrollX: 100 }
    expect(placeBubble(anchor(100, 100), size, v).left).toBe(108)
  })

  it('pins to the left margin when the bubble is wider than the viewport', () => {
    expect(placeBubble(anchor(100, 100), { w: 500, h: 50 }, view).left).toBe(8)
  })
})

describe('placeBubble vertical', () => {
  it('goes below the anchor by default', () => {
    const r = placeBubble(anchor(100, 100), size, view)
    expect(r.above).toBe(false)
    expect(r.top).toBe(120 + 8)
  })

  it('flips above only when below does not fit and above does', () => {
    const near = placeBubble(anchor(100, 760), size, view)
    expect(near.above).toBe(true)
    expect(near.top).toBe(760 - 8 - 50)
    // no room anywhere (tiny viewport): stays below rather than going off the top
    const tiny = placeBubble(anchor(100, 20), { w: 200, h: 90 }, { ...view, h: 100 })
    expect(tiny.above).toBe(false)
  })

  it('accounts for vertical scroll (document coordinates)', () => {
    const v = { ...view, scrollY: 1000 }
    // anchor near the bottom of the scrolled viewport (doc y 1760): must flip above
    expect(placeBubble(anchor(100, 1760), size, v).above).toBe(true)
    // anchor near the top of the scrolled viewport: goes below
    expect(placeBubble(anchor(100, 1010), size, v).above).toBe(false)
  })
})
