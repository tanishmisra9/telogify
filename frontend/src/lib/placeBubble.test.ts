import { describe, expect, it } from 'vitest'
import { placeBubble, placeFollow, type Box } from './placeBubble'

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

describe('placeBubble prefer above (keep the anchor region clear)', () => {
  it('goes above when it fits, even though below fits too', () => {
    const r = placeBubble(anchor(100, 300), size, view, 'center', 8, 8, 'above')
    expect(r.above).toBe(true)
    expect(r.top).toBe(300 - 8 - 50)
  })

  it('falls back below when above does not fit', () => {
    const r = placeBubble(anchor(100, 20), size, view, 'center', 8, 8, 'above')
    expect(r.above).toBe(false)
    expect(r.top).toBe(40 + 8)
  })

  it('never overlaps the anchor whichever side it takes', () => {
    for (const top of [20, 300, 760]) {
      const a = anchor(100, top)
      const r = placeBubble(a, size, view, 'center', 8, 8, 'above')
      expect(r.top + size.h <= a.top || r.top >= a.bottom).toBe(true)
    }
  })
})

describe('placeFollow', () => {
  const v = { w: 1000, h: 800, scrollX: 0, scrollY: 0 }
  const size = { w: 220, h: 80 }
  const rectOf = (p: { left: number; top: number }): Box => ({ left: p.left, top: p.top, right: p.left + size.w, bottom: p.top + size.h })
  const touches = (a: Box, b: Box) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top

  it('sits below-right of the pointer by default', () => {
    expect(placeFollow({ x: 300, y: 300 }, size, v)).toMatchObject({ left: 316, top: 318, flipX: false, flipY: false })
  })
  it('follows the pointer: the position moves with it', () => {
    const a = placeFollow({ x: 300, y: 300 }, size, v)
    const b = placeFollow({ x: 340, y: 300 }, size, v)
    expect(b.left - a.left).toBe(40)
  })
  it('flips left of the pointer at the right edge and above it at the bottom edge', () => {
    expect(placeFollow({ x: 950, y: 300 }, size, v).left).toBe(950 - 16 - 220)
    expect(placeFollow({ x: 300, y: 780 }, size, v).top).toBe(780 - 18 - 80)
  })
  it('is clamped inside the viewport and works in document coordinates after the page scrolled', () => {
    expect(placeFollow({ x: 5, y: 5 }, size, v)).toMatchObject({ left: 21, top: 23 })
    const s = placeFollow({ x: 300, y: 1500 }, size, { ...v, scrollY: 1000 })
    expect(s.top).toBeGreaterThanOrEqual(1008)
    expect(s.top + size.h).toBeLessThanOrEqual(1000 + 800 - 8)
  })
  it('above (touch) sits above the touch point, and drops below it only when there is no room above', () => {
    expect(placeFollow({ x: 300, y: 400 }, size, v, null, 16, 18, 8, 8, 4, true)).toMatchObject({ left: 316, top: 400 - 18 - 80 })
    expect(placeFollow({ x: 300, y: 40 }, size, v, null, 16, 18, 8, 8, 4, true).top).toBe(40 + 18) // no room above: below
  })
  it('never covers the thing being read: a pointer inside it pushes the tip clear, by the smallest move', () => {
    const own: Box = { left: 250, top: 290, right: 450, bottom: 318 } // a row's glyph + label under the pointer
    const p = placeFollow({ x: 300, y: 300 }, size, v, own)
    expect(touches(rectOf(p), own)).toBe(false)
    expect(p).toMatchObject({ left: 316, top: 326 }) // just below the row (own.bottom + gap), not the far side
  })
  it('leaves the default spot alone when it is already clear of `own`', () => {
    const own: Box = { left: 0, top: 0, right: 100, bottom: 28 }
    expect(placeFollow({ x: 300, y: 300 }, size, v, own)).toMatchObject({ left: 316, top: 318 })
  })
  it('reports which way it flipped', () => {
    expect(placeFollow({ x: 950, y: 300 }, size, v)).toMatchObject({ flipX: true, flipY: false })
    expect(placeFollow({ x: 300, y: 780 }, size, v)).toMatchObject({ flipX: false, flipY: true })
  })
  it('hysteresis: a pointer resting on the flip boundary does not swing the tip back and forth', () => {
    // right room ends at x = 1000 - 8 - 220 - 16 = 756: a pointer at 760 flips; at 750 it would not
    expect(placeFollow({ x: 760, y: 300 }, size, v).flipX).toBe(true)
    expect(placeFollow({ x: 750, y: 300 }, size, v).flipX).toBe(false) // no memory: back to the right at once
    const stick = { x: true, y: false }
    expect(placeFollow({ x: 750, y: 300 }, size, v, null, 16, 18, 8, 8, 4, false, stick).flipX).toBe(true) // stays left
    expect(placeFollow({ x: 740, y: 300 }, size, v, null, 16, 18, 8, 8, 4, false, stick).flipX).toBe(true)
    expect(placeFollow({ x: 700, y: 300 }, size, v, null, 16, 18, 8, 8, 4, false, stick).flipX).toBe(false) // clear of it: returns
  })
  it('does not throw and still clamps when nothing is clear or the viewport is narrower than the tip', () => {
    const huge: Box = { left: 0, top: 0, right: 5000, bottom: 5000 }
    expect(placeFollow({ x: 100, y: 100 }, size, { ...v, w: 200 }, huge).left).toBe(8)
  })
})
