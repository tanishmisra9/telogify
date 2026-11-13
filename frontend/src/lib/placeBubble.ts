// Where a floating bubble (tooltip, chart readout) goes, in DOCUMENT coordinates (viewport rect + scroll),
// so it can live in a portal on <body> and scroll with the page instead of being clipped by a card.
// It prefers below the anchor, flips above only when below doesn't fit and above does, and is clamped
// `margin` px inside the viewport horizontally so it can never run off a phone. `align` is the preferred
// horizontal anchor: centered on the anchor, or its left / right edge.
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
  const above = !fitsBelow && fitsAbove
  return { left, top: above ? aboveTop : below, above }
}
