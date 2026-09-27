import { driverName } from '@/lib/drivers'
import type { QualiTraceDriver, QualiTraceUnavailable } from '@/lib/api'

export const MAX_PICKED = 2

export const surname = (code: string) => driverName(code).split(' ').slice(1).join(' ') || code

// One classified driver as the picker sees them: plottable (has a trace) or not.
export interface PickerRow {
  driver: string
  constructor: string | null
  position: number | null
  // Trace lap time when plottable, else the official best (null = set no time).
  time_s: number | null
  plottable: boolean
}

// Full classification, P1 first: plottable and unplottable drivers merged by official position,
// unclassified ones last (stable sort keeps the API's own order among them).
export function pickerRows(drivers: QualiTraceDriver[], unavailable: QualiTraceUnavailable[]): PickerRow[] {
  const rows: PickerRow[] = [
    ...drivers.map((d) => ({ driver: d.driver, constructor: d.constructor, position: d.position, time_s: d.lap_time_s, plottable: true })),
    ...unavailable.map((u) => ({ driver: u.driver, constructor: u.constructor, position: u.position, time_s: u.best_lap_s, plottable: false })),
  ]
  return rows.sort((a, b) => (a.position ?? Infinity) - (b.position ?? Infinity))
}

// Plain toggle, two at most: a picked driver comes off, a new one joins while there's room.
export function toggleDriver(selected: string[], code: string): string[] {
  if (selected.includes(code)) return selected.filter((c) => c !== code)
  return selected.length < MAX_PICKED ? [...selected, code] : selected
}

// `null` means "untouched" and shows `fallback` (the default pair, and what Reset restores). A
// stored pick naming drivers this data doesn't carry (another session or round) drops them.
export function resolveSelection(picked: string[] | null, available: string[], fallback: string[]): string[] {
  return picked === null ? fallback : picked.filter((c) => available.includes(c))
}

export function sameSet(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((c) => b.includes(c))
}

// P1's own row shows its absolute time; every other row shows its gap to P1 (e.g. "+0.433s").
// A negative gap (a later-position row with an actually-faster raw lap, e.g. a grid penalty)
// renders with a leading "-", matching the sign convention already used elsewhere (gapLadder,
// DegradationChart).
export function pickerTimeLabel(time: number | null, poleTime: number | null, isPole: boolean): string | null {
  if (time == null) return null
  if (isPole || poleTime == null) return `${time.toFixed(3)}s`
  const delta = time - poleTime
  return `${delta >= 0 ? '+' : ''}${delta.toFixed(3)}s`
}

export interface TeamOption {
  team: string
  // The team's two plottable drivers, best-classified first (empty when blocked).
  codes: string[]
  // Why the team can't be compared (a driver has no usable trace / set no time / never ran);
  // null when it can. Shown as text so a greyed team never relies on opacity alone.
  blocked: string | null
  bestPosition: number | null
}

// Teams with a driver in this session, best-classified first. A team is comparable only when it
// has two plottable drivers; otherwise it is blocked and says which driver is the reason.
export function teamOptions(rows: PickerRow[]): TeamOption[] {
  const byTeam = new Map<string, PickerRow[]>()
  for (const r of rows) {
    if (r.constructor == null) continue
    byTeam.set(r.constructor, [...(byTeam.get(r.constructor) ?? []), r])
  }
  const options = [...byTeam.entries()].map(([team, teamRows]) => {
    const plottable = teamRows.filter((r) => r.plottable)
    const ready = plottable.length >= MAX_PICKED
    const reasons = teamRows
      .filter((r) => !r.plottable)
      .map((r) => `${surname(r.driver)}: ${r.time_s != null ? 'no trace' : 'no time'}`)
    return {
      team,
      codes: ready ? plottable.slice(0, MAX_PICKED).map((r) => r.driver) : [],
      blocked: ready ? null : reasons.join(', ') || `Only ${surname(teamRows[0].driver)} ran`,
      bestPosition: Math.min(...teamRows.map((r) => r.position ?? Infinity)),
    }
  })
  return options
    .sort((a, b) => a.bestPosition - b.bestPosition)
    .map((o) => ({ ...o, bestPosition: Number.isFinite(o.bestPosition) ? o.bestPosition : null }))
}
