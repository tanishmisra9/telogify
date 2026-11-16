// Pure text for the Finishing order's time column, so the switcher's rules live (and are tested) in one place.
import type { ResultRow } from '@/lib/api'

export type GapTo = 'leader' | 'ahead'

// The switcher is only offered when the API sent an interval for at least one car (an older backend, or a round
// whose results are degraded to position-only, has none, and a "Car ahead" tab of dashes would be a broken control).
export const canSwitchGap = (rows: ResultRow[]): boolean => rows.some((r) => r.interval_s != null)

const seconds = (s: number) => `+${s.toFixed(3)}s`

// `gap_label` is the server's wording (winner's total time, "+1 Lap", "DNF", "DNS"): kept for every car with no
// honest seconds figure, so a lapped or retired car never gets an invented one. A lead-lap car whose neighbour
// ahead has no time shows a dash for "Car ahead" rather than bridging to the car before it.
export function gapText(r: ResultRow, to: GapTo): string {
  if (r.position === 1 || r.gap_to_leader_s == null) return r.gap_label
  if (to === 'leader') return seconds(r.gap_to_leader_s)
  return r.interval_s == null ? '–' : seconds(r.interval_s)
}
