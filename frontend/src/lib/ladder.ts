// Pure geometry shared by the qualifying segment ladder and the race results graphic (hand-rolled SVG, no chart
// library). Kept free of React so the maths is unit-tested.

export const ROW_H = 28
// A finger needs a bigger target than a cursor: rows are this tall on a device with no hover (the guideline is 44; a dense chart
// of 22-48 rows would grow by ~half a screen at 44, so this is the compromise).
export const TOUCH_ROW_H = 40
export const rowHeight = (canHover: boolean): number => (canHover ? ROW_H : TOUCH_ROW_H)
export const STRIP_H = 58 // each band opens with a header strip: the title line, then (below it) the cut tag, never over a car
export const BAND_GAP = 14

export interface BandBox {
  top: number
  rowsTop: number // y of the first row
  height: number
}

/** Stack bands top to bottom. One entry per band, sized by its row count; `height` is the whole stack. `stripHs` overrides a
 * band's header height (a band with no title needs only a little room, not a full strip of dead space); `rowH` is the row height. */
export function layoutBands(rowCounts: number[], top = 0, stripHs?: number[], rowH = ROW_H): { bands: BandBox[]; height: number } {
  const bands: BandBox[] = []
  let y = top
  rowCounts.forEach((n, i) => {
    const strip = stripHs?.[i] ?? STRIP_H
    const height = strip + n * rowH
    bands.push({ top: y, rowsTop: y + strip, height })
    y += height + BAND_GAP
  })
  return { bands, height: Math.max(top, y - BAND_GAP) }
}

export function scaleLinear(d0: number, d1: number, r0: number, r1: number): (v: number) => number {
  const span = d1 - d0
  return (v) => (span === 0 ? (r0 + r1) / 2 : r0 + ((v - d0) / span) * (r1 - r0))
}

// Average advance of the 13px label face. Used only to decide which side of a car its label fits; a rough figure is
// enough because the chosen side keeps >= 1 char of slack, and the label is never hidden, only moved.
export const CHAR_W = 7.6
export const textWidth = (chars: number) => chars * CHAR_W

/** Which side of a glyph its label goes. `x` is the glyph's left edge and `carW` its width. Prefers the right; flips to
 * the left when the label would leave the plot; with room on neither side picks the roomier one. */
export function labelSide(x: number, carW: number, labelW: number, width: number, pad = 8, gap = 6): 'right' | 'left' {
  const roomRight = width - pad - (x + carW + gap)
  const roomLeft = x - gap - pad
  if (roomRight >= labelW) return 'right'
  if (roomLeft >= labelW) return 'left'
  return roomRight >= roomLeft ? 'right' : 'left'
}

export type ColKind = 'lead' | 'lapped' | 'out'

// Minimum px a column needs and its share of any extra width. The lead column carries real-gap scaling and a long figure
// (the winner's total time), a lapped column only a code and "P12", the out column a code and "DNF".
const COL: Record<ColKind, { min: number; weight: number }> = {
  lead: { min: 300, weight: 2 },
  lapped: { min: 150, weight: 1 },
  out: { min: 96, weight: 0.7 },
}

/** How many laps-down columns fit beside the lead lap (and the out column) at this width. 0 means none: stack instead. */
export function maxLappedColumns(width: number, hasOut: boolean, pad = 16): number {
  const room = width - 2 * pad - COL.lead.min - (hasOut ? COL.out.min : 0)
  return Math.max(0, Math.floor(room / COL.lapped.min))
}

/** Widths for columns side by side, or null when they do not all fit (the caller stacks them as bands). Computed from the
 * real width and the real column kinds, not a breakpoint: a race with +5 laps fits later than one with +2. */
export function columnWidths(width: number, kinds: ColKind[], pad = 16): number[] | null {
  if (kinds.length === 0) return null
  const avail = width - 2 * pad
  const mins = kinds.map((k) => COL[k].min)
  const total = mins.reduce((a, b) => a + b, 0)
  if (total > avail) return null
  const weights = kinds.reduce((a, k) => a + COL[k].weight, 0)
  return kinds.map((k, i) => mins[i] + ((avail - total) * COL[k].weight) / weights)
}

/** Horizontal step between consecutive rows of a column laid out as a staircase (finishing order, not to scale). */
export function staircaseStep(rows: number, span: number, minStep = 3, maxStep = 16): number {
  if (rows <= 1) return 0
  return Math.max(minStep, Math.min(maxStep, span / (rows - 1)))
}
