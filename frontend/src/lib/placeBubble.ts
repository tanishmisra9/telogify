// Where a floating bubble (tooltip, chart readout) goes, in DOCUMENT coordinates (viewport rect + scroll),
// so it can live in a portal on <body> and scroll with the page instead of being clipped by a card.
// It prefers below the anchor, flips above only when below doesn't fit and above does, and is clamped
// `margin` px inside the viewport horizontally so it can never run off a phone. `align` is the preferred
// horizontal anchor: centered on the anchor, or its left / right edge. `prefer` flips the vertical
// preference ('above' tries above first, falling back below): pass the WHOLE region the reader is looking
// at as the anchor and the bubble lands outside it, so a readout never covers the data it describes.
export interface Box {
  left: number
  top: number
  right: number
  bottom: number
}
export interface View {
  w: number
  h: number
  scrollX: number
  scrollY: number
}

export function placeBubble(
  anchor: Box,
  size: { w: number; h: number },
  view: View,
  align: 'center' | 'start' | 'end' = 'center',
  gap = 8,
  margin = 8,
  prefer: 'below' | 'above' = 'below',
): { left: number; top: number; above: boolean } {
  const pref =
    align === 'start' ? anchor.left : align === 'end' ? anchor.right - size.w : (anchor.left + anchor.right) / 2 - size.w / 2
  const min = view.scrollX + margin
  const max = view.scrollX + view.w - margin - size.w
  const left = max < min ? min : Math.min(Math.max(pref, min), max)

  const below = anchor.bottom + gap
  const fitsBelow = below + size.h <= view.scrollY + view.h - margin
  const aboveTop = anchor.top - gap - size.h
  const fitsAbove = aboveTop >= view.scrollY + margin
  const above = prefer === 'above' ? fitsAbove : !fitsBelow && fitsAbove
  return { left, top: above ? aboveTop : below, above }
}

const hit = (a: Box, b: Box, pad: number) => a.left < b.right + pad && a.right > b.left - pad && a.top < b.bottom + pad && a.bottom > b.top - pad

/** A readout that follows the pointer: below-right of it by (`dx`, `dy`), flipped to the left / above when that side leaves
 * the viewport, clamped inside it. It never covers `own`, the thing being read (the hovered car, the box-plot column): when
 * the default spot would, it takes the nearest side of `own` that is clear. Other content may be passed over, as with any
 * tooltip. `above` puts it above the pointer (touch). All in document coordinates (pointer = client position + scroll), like
 * `placeBubble`. */
export interface FollowSpot {
  left: number
  top: number
  flipX: boolean // placed left of the pointer (it did not fit on the right)
  flipY: boolean // placed above the pointer (it did not fit below)
}

// A flipped tip returns to its default side only once the pointer is this much further inside: a pointer resting on the
// boundary would otherwise swing the tip back and forth with every pixel of movement.
const FLIP_HYSTERESIS = 28

export function placeFollow(
  pointer: { x: number; y: number },
  size: { w: number; h: number },
  view: View,
  own: Box | null = null,
  dx = 16,
  dy = 18,
  margin = 8,
  gap = 8,
  pad = 4,
  above = false,
  stick: { x: boolean; y: boolean } = { x: false, y: false }, // which flips were in effect last frame
): FollowSpot {
  const minL = view.scrollX + margin
  const maxL = view.scrollX + view.w - margin - size.w
  const minT = view.scrollY + margin
  const maxT = view.scrollY + view.h - margin - size.h
  const clampL = (l: number) => (maxL < minL ? minL : Math.min(Math.max(l, minL), maxL))
  const clampT = (t: number) => (maxT < minT ? minT : Math.min(Math.max(t, minT), maxT))
  const rect = (l: number, t: number): Box => ({ left: l, top: t, right: l + size.w, bottom: t + size.h })

  const flipX = stick.x ? !(pointer.x + dx + FLIP_HYSTERESIS <= maxL) : pointer.x + dx > maxL
  let left = flipX ? pointer.x - dx - size.w : pointer.x + dx
  // `above` (touch): a finger hides what is under and beside it, so sit ABOVE the touch point, and only drop below it when
  // there is no room above. Otherwise below, flipping above when there is no room below.
  let flipY: boolean
  let top: number
  if (above) {
    flipY = pointer.y - dy - size.h < minT
    top = flipY ? pointer.y + dy : pointer.y - dy - size.h
  } else {
    flipY = stick.y ? !(pointer.y + dy + FLIP_HYSTERESIS <= maxT) : pointer.y + dy > maxT
    top = flipY ? pointer.y - dy - size.h : pointer.y + dy
  }
  left = clampL(left)
  top = clampT(top)

  if (own && hit(rect(left, top), own, pad)) {
    const clear = (
      [
        [left, own.bottom + gap], // below it
        [left, own.top - gap - size.h], // above it
        [own.right + gap, top], // right of it
        [own.left - gap - size.w, top], // left of it
      ] as [number, number][]
    )
      .map(([l, t]): [number, number] => [clampL(l), clampT(t)])
      .filter(([l, t]) => !hit(rect(l, t), own, pad))
    if (clear.length) {
      const d = ([l, t]: [number, number]) => (l - left) ** 2 + (t - top) ** 2
      const best = clear.reduce((a, c) => (d(c) < d(a) ? c : a))
      return { left: best[0], top: best[1], flipX, flipY }
    }
  }
  return { left, top, flipX, flipY }
}
