// Pure shaping for the race results graphic. The backend serves every figure (status, laps down, places gained,
// stints); this file only groups and lays out. Nothing here guesses a status: a row with none is "unknown".
import type { ResultRow, ResultStint } from '@/lib/api'
import { driverName } from '@/lib/drivers'
import { lappedGapText, gapText } from '@/lib/finishing'

export type RaceView = 'finishers' | 'places' | 'strategy'

/** Views that need `status` are offered only when the round has one. A degraded (position-only) round has none for
 * any car, and lapped or out would be guesses. */
export const hasClassification = (rows: ResultRow[]): boolean => rows.some((r) => !!r.status)
export const hasStints = (rows: ResultRow[]): boolean => rows.some((r) => (r.stints?.length ?? 0) > 0)

export function availableViews(rows: ResultRow[]): RaceView[] {
  const views: RaceView[] = []
  if (hasClassification(rows)) views.push('finishers', 'places')
  if (hasStints(rows)) views.push('strategy')
  return views
}

const norm = (s: string | null | undefined) => (s ?? '').trim().toLowerCase()

export interface LapColumn {
  key: string
  title: string // "Lead lap", "+1 lap", "+2 laps", or "Lapped" when the API has no laps-down figure
  kind: 'lead' | 'lapped'
  rows: ResultRow[] // finishing order
  showDown?: boolean // a merged "or more" column: each row also shows its own laps down
}

/** The Finishers columns, as in the printed race-results sheets: the lead lap, then EVERY laps-down value from +1 up to the
 * largest, including ones nobody finished on (an empty +3 between +2 and +4 keeps the scale honest). Only classified
 * finishers (status Finished or Lapped) are in a column; everything else is an out car (`statusGroups`). A Lapped car
 * whose laps-down is unknown gets its own trailing "Lapped" column, never a guessed +1. */
export function groupByLapsDown(rows: ResultRow[]): LapColumn[] {
  const lead: ResultRow[] = []
  const byDown = new Map<number, ResultRow[]>()
  const unknown: ResultRow[] = []
  for (const r of rows) {
    const s = norm(r.status)
    if (s === 'finished') lead.push(r)
    else if (s === 'lapped') {
      const d = r.laps_down
      if (d != null && d > 0) byDown.set(d, [...(byDown.get(d) ?? []), r])
      else unknown.push(r)
    }
  }
  const cols: LapColumn[] = []
  if (lead.length || byDown.size) cols.push({ key: 'lead', title: 'Lead lap', kind: 'lead', rows: lead })
  const max = Math.max(0, ...byDown.keys())
  for (let d = 1; d <= max; d++) {
    cols.push({ key: `down-${d}`, title: `+${d} ${d === 1 ? 'lap' : 'laps'}`, kind: 'lapped', rows: byDown.get(d) ?? [] })
  }
  if (unknown.length) cols.push({ key: 'lapped', title: 'Lapped', kind: 'lapped', rows: unknown })
  return cols
}

/** Fit the laps-down columns to the room. `capacity` is how many laps-down columns fit beside the lead lap (`maxLappedColumns`),
 * or null when stacking (no width limit, but empty bands are only clutter). NO car is ever dropped:
 *   1. everything fits: unchanged (the whole range, empties included, so the scale reads honestly);
 *   2. else empty columns go, from the highest laps-down downward, until it fits (a 15-laps-down car no longer drags 14 empty
 *      columns with it: Lead, +1, +2, +3, +15);
 *   3. else the farthest non-empty columns merge into one "+N laps or more" column whose rows show their own laps down. */
export function planColumns(cols: LapColumn[], capacity: number | null): LapColumn[] {
  const lead = cols.filter((c) => c.kind === 'lead')
  let lapped = cols.filter((c) => c.kind === 'lapped')
  if (capacity === null) return [...lead, ...lapped.filter((c) => c.rows.length > 0)]
  if (lapped.length <= capacity) return cols
  // 2. drop empties from the far end
  for (let i = lapped.length - 1; i >= 0 && lapped.length > capacity; i--) {
    if (lapped[i].rows.length === 0) lapped = lapped.filter((_, j) => j !== i)
  }
  if (lapped.length <= capacity) return [...lead, ...lapped]
  // 3. merge the tail into one column (capacity 0 is handled by the caller: it stacks instead)
  const keep = Math.max(0, capacity - 1)
  const tail = lapped.slice(keep)
  const known = tail.map((c) => Number(c.key.replace('down-', ''))).filter((n) => Number.isFinite(n))
  const merged: LapColumn = {
    key: 'more',
    title: known.length ? `+${Math.min(...known)} or more` : 'Lapped', // short: it has to fit a ~150px column
    kind: 'lapped',
    rows: tail.flatMap((c) => c.rows),
    showDown: true,
  }
  return [...lead, ...lapped.slice(0, keep), merged]
}

/** The short label printed over a names-only block: DNF / DNS / DSQ, else the API's own status text. */
export function outCode(r: ResultRow): string {
  const s = norm(r.status)
  if (s === 'retired') return 'DNF'
  if (s === 'did not start') return 'DNS'
  if (s === 'disqualified') return 'DSQ'
  return (r.status ?? '').trim() || 'Out'
}

export interface StatusGroup {
  label: string
  rows: ResultRow[]
}

/** A names-only row for a car with nothing to point at: the code and its label (DNF, DNS, DSQ, PL, ...), as qualifying
 * does for a car with no time. */
export interface OutRow {
  row: ResultRow
  label: string
}

/** Groups flattened to rows, keeping the group order (DNF first) and finishing order inside a group. */
export const flattenGroups = (groups: StatusGroup[]): OutRow[] => groups.flatMap((g) => g.rows.map((row) => ({ row, label: g.label })))

const GROUP_ORDER = ['DNF', 'DNS', 'DSQ']

/** Cars that are not classified finishers, grouped under their label, DNF first, then DNS, DSQ, then any other status. */
export function statusGroups(rows: ResultRow[]): StatusGroup[] {
  const m = new Map<string, ResultRow[]>()
  for (const r of rows) m.set(outCode(r), [...(m.get(outCode(r)) ?? []), r])
  const rank = (l: string) => (GROUP_ORDER.includes(l) ? GROUP_ORDER.indexOf(l) : GROUP_ORDER.length)
  return [...m.entries()].sort((a, b) => rank(a[0]) - rank(b[0]) || a[0].localeCompare(b[0])).map(([label, rs]) => ({ label, rows: rs }))
}

export const isClassified = (r: ResultRow): boolean => ['finished', 'lapped'].includes(norm(r.status))
export const isOut = (r: ResultRow): boolean => !!norm(r.status) && !isClassified(r)

/** Places view: classified finishers with a served number are drawn. Cars started from the pit lane (not a slot) and
 * classified finishers with no start at all are named in a block, labelled PL / "No grid"; cars that did not finish
 * are the DNF/DNS/DSQ groups. Nothing is drawn without an honest number. */
export function splitGains(rows: ResultRow[]): { listed: ResultRow[]; blocks: StatusGroup[] } {
  const listed = rows.filter((r) => r.places_gained != null)
  const blocks: StatusGroup[] = statusGroups(rows.filter(isOut))
  const pl = rows.filter((r) => isClassified(r) && r.places_gained == null && r.pit_lane)
  const none = rows.filter((r) => isClassified(r) && r.places_gained == null && !r.pit_lane)
  if (pl.length) blocks.push({ label: 'PL', rows: pl })
  if (none.length) blocks.push({ label: 'No grid', rows: none })
  return { listed, blocks }
}

/** Largest move either way, at least 1 so a field with no movement still has an axis. */
export const gainReach = (listed: ResultRow[]): number =>
  Math.max(1, ...listed.map((r) => Math.abs(r.places_gained ?? 0)))

export const signed = (n: number): string => (n > 0 ? `+${n}` : n < 0 ? `-${Math.abs(n)}` : '0')

/** Why a car is in the Out band, in the API's own words, for display ("Retired", "Did not start"). */
export const outLabel = (r: ResultRow): string => (r.status ?? '').trim() || 'No classification'

/** Race length for the strategy axis: the furthest lap any stint reaches. */
export function raceLaps(rows: ResultRow[]): number {
  let max = 0
  for (const r of rows) for (const s of r.stints ?? []) max = Math.max(max, s.lap_end)
  return max
}

export interface GapAxis {
  max: number
  step: number
  ticks: number[]
}

/** Seconds-behind-winner axis for the lead lap: 0 .. the slowest gap, ticked at a readable step. `maxIntervals` caps the
 * number of tick intervals (a narrow column fits fewer labels than a full-width band). */
export function gapAxis(maxGap: number, maxIntervals = 7): GapAxis {
  const steps = [1, 2, 5, 10, 15, 20, 30, 60]
  const step = steps.find((s) => maxGap / s <= maxIntervals) ?? 120
  const max = Math.max(step, Math.ceil(maxGap / step) * step)
  const ticks: number[] = []
  for (let t = 0; t <= max; t += step) ticks.push(t)
  return { max, step, ticks }
}

// Tyre colours live in CSS tokens (`--tyre-*`, light and a muted night set in index.css), not here, so night mode
// can be low-key. The letter in each segment carries the meaning too, so colour is never the only signal.
const TYRE: Record<string, { fill: string; letter: string; ink: string }> = {
  SOFT: { fill: 'var(--tyre-soft)', letter: 'S', ink: 'var(--tyre-soft-ink)' },
  MEDIUM: { fill: 'var(--tyre-medium)', letter: 'M', ink: 'var(--tyre-medium-ink)' },
  HARD: { fill: 'var(--tyre-hard)', letter: 'H', ink: 'var(--tyre-hard-ink)' },
  INTERMEDIATE: { fill: 'var(--tyre-inter)', letter: 'I', ink: 'var(--tyre-inter-ink)' },
  WET: { fill: 'var(--tyre-wet)', letter: 'W', ink: 'var(--tyre-wet-ink)' },
}

export const tyreStyle = (compound: string | null) => (compound ? TYRE[compound.toUpperCase()] ?? null : null)

export const tyreName = (compound: string | null): string =>
  compound ? compound.charAt(0) + compound.slice(1).toLowerCase() : 'No tyre data'

/** Laps in a stint, inclusive of both ends (stint 1-20 is 20 laps). */
export const stintLaps = (s: ResultStint): number => s.lap_end - s.lap_start + 1

/** Strategy view: classified finishers and retirees keep their bars (a retiree's stints before stopping are real data);
 * did-not-start, disqualified and any other status are names only. */
export function strategySplit(rows: ResultRow[]): { bars: ResultRow[]; blocks: StatusGroup[] } {
  const keeps = (r: ResultRow) => !isOut(r) || norm(r.status) === 'retired'
  return { bars: rows.filter(keeps), blocks: statusGroups(rows.filter((r) => !keeps(r))) }
}

/** The race tooltip, in a fixed compact shape:
 *   1. "Max Verstappen, Red Bull Racing"
 *   2. "Started P20, Finished P6" | "Started PL, Finished P6" | "Started P5, Finished DNF"
 *      (DNS, DSQ and any other status are just that status: no Started / Finished)
 *   3. the winner's total time | "+10.768s" | "+2 Laps" | "+1 Lap, +95.167s" (finishers only)
 *   4. "Gained 3 places" | "Lost 2 places" | "Held position" (only when there is a number)
 * Strategy adds one line per stint. Anything unknown is omitted, never guessed. */
export function raceTip(r: ResultRow, view: RaceView): { title: string; lines: string[] } {
  const title = `${driverName(r.driver)}${r.constructor ? `, ${r.constructor}` : ''}`
  const s = norm(r.status)
  const lines: string[] = []

  if (s === 'did not start') lines.push('Did not start')
  else if (s === 'disqualified') lines.push('Disqualified')
  else if (s && s !== 'retired' && !isClassified(r)) lines.push((r.status ?? '').trim())
  else {
    const start = r.pit_lane ? 'PL' : r.grid != null ? `P${r.grid}` : null
    const finish = s === 'retired' ? 'DNF' : r.position != null ? `P${r.position}` : null
    const parts = [start && `Started ${start}`, finish && `Finished ${finish}`].filter(Boolean)
    if (parts.length) lines.push(parts.join(', '))
    if (isClassified(r)) {
      // a lapped car: laps down, then its gap to the leader ("+1 Lap, +95.167s")
      const gap = [gapText(r, 'leader'), lappedGapText(r)].filter(Boolean).join(', ')
      if (gap) lines.push(gap)
    }
    const g = r.places_gained
    if (g != null) lines.push(g > 0 ? `Gained ${g} place${g > 1 ? 's' : ''}` : g < 0 ? `Lost ${-g} place${g < -1 ? 's' : ''}` : 'Held position')
  }
  if (view === 'strategy') for (const st of r.stints ?? []) lines.push(`${tyreName(st.compound)}: laps ${st.lap_start}-${st.lap_end} (${stintLaps(st)})`)
  return { title, lines }
}
