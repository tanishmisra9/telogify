// Pure helpers for the qualifying segment ladder: lap-time text and the shared time axis. Every figure arrives
// computed from the API (cut time, gaps); this file only formats and lays out.

/** 87.452 -> "1:27.452". Rounds to the millisecond first so 59.9996 reads "1:00.000", never "0:60.000". */
export function formatLap(seconds: number): string {
  const ms = Math.round(seconds * 1000)
  const m = Math.floor(ms / 60000)
  return `${m}:${((ms - m * 60000) / 1000).toFixed(3).padStart(6, '0')}`
}

export interface TimeAxis {
  min: number
  max: number
  step: number
  ticks: number[]
}

/** A shared axis over every segment's times (so a car is comparable across bands), snapped to a readable step.
 * Null when there is nothing to place. */
export function timeAxis(times: number[]): TimeAxis | null {
  if (times.length === 0) return null
  const lo = Math.min(...times)
  const hi = Math.max(...times)
  const span = hi - lo
  const step = span <= 3 ? 0.5 : span <= 8 ? 1 : 2
  const min = Math.floor(lo / step) * step
  let max = Math.ceil(hi / step) * step
  if (max === min) max = min + step // every time identical: still a drawable axis
  const ticks: number[] = []
  for (let t = min; t <= max + 1e-9; t += step) ticks.push(Math.round(t * 1000) / 1000)
  return { min, max, step, ticks }
}

/** Axis tick text: whole-second steps read "1:27", half-second steps "1:27.5". */
export function formatTick(t: number, step: number): string {
  const m = Math.floor(t / 60)
  const s = t - m * 60
  return step >= 1 ? `${m}:${String(Math.round(s)).padStart(2, '0')}` : `${m}:${s.toFixed(1).padStart(4, '0')}`
}
