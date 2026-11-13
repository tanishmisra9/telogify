// Pure maths for the by-round charts' zoom, kept out of the hook so it can be unit-tested.
export const MIN_ZOOM = 1
export const MAX_ZOOM = 5
export const ZOOM_STEP = 1.5

export const clampZoom = (z: number): number => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z))

// One button press: x1.5 in or out, snapping back to exactly 1 when a step would land next to it
// (1.5 / 1.5 is 1, but 2.25 / 1.5 / 1.5 drifts through float error), so "Reset" and "−" agree.
export function stepZoom(z: number, dir: 1 | -1): number {
  const next = dir > 0 ? z * ZOOM_STEP : z / ZOOM_STEP
  return Math.abs(next - 1) < 0.05 ? 1 : clampZoom(next)
}

// Two-finger pinch: the zoom follows the ratio of the current finger distance to the starting one.
export function pinchZoom(z0: number, d0: number, d: number): number {
  return d0 > 0 ? clampZoom((z0 * d) / d0) : z0
}

// ctrl/cmd + wheel (a trackpad pinch arrives as a wheel event with ctrlKey): exponential in the delta so
// equal movements feel equal at any zoom. A mouse wheel notch is ~100px or 3 lines, so the per-event
// delta is capped, otherwise one notch would jump most of the range.
export function wheelZoom(z: number, deltaY: number, deltaMode = 0): number {
  const px = deltaMode === 1 ? deltaY * 16 : deltaY
  const d = Math.max(-50, Math.min(50, px))
  return clampZoom(z * Math.exp(-d * 0.01))
}

// Keep the content under the focal point (pinch midpoint, or the viewport centre for buttons) where it
// is when the content grows or shrinks. `scroll` and `focal` are along one axis, `focal` measured from
// the viewport's start; the result is clamped to the new scrollable range (so zooming back to 1x lands on 0).
export function anchorScroll(scroll: number, focal: number, prevSize: number, nextSize: number, viewSize: number): number {
  if (prevSize <= 0) return scroll
  const target = ((scroll + focal) / prevSize) * nextSize - focal
  return Math.min(Math.max(0, target), Math.max(0, nextSize - viewSize))
}
