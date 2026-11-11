// Pure helpers for the Race start ladder: one stacked bar per driver, 0-100 km/h in the solid
// segment and 100-200 km/h in the lighter one. Bar lengths are absolute seconds on one shared
// axis (0 .. the slowest time), so two bars always compare honestly.
//
// A round either has 0-200 km/h times (`toKmh` 200: two segments) or only 0-100 (`toKmh` 100:
// one segment), because at Monaco/Baku-style circuits most cars brake for turn 1 before 200.

export interface StartRow {
  driver: string
  constructor: string | null
  t_0_100_s: number
  t_100_200_s: number | null
  t_0_200_s: number | null
  // Speed after the round's fixed distance, from the car's own launch; null when it lifted first
  // or the round lacks enough cars with a reading.
  v_75m_kmh: number | null
  compound: string | null
}

// Just the time fields, so drivers and aggregated groups share the bar maths.
export type Timed = Pick<StartRow, 't_0_100_s' | 't_100_200_s' | 't_0_200_s'>

// The time the round is ranked and drawn on.
export function rowTotal(row: Timed, toKmh: number): number {
  return toKmh === 200 && row.t_0_200_s != null ? row.t_0_200_s : row.t_0_100_s
}

// Width of each segment as a fraction (0..1) of the shared axis, so first + second is the
// bar's full length. A degenerate axis (no rows, or all zero) yields zero-width segments, and a
// 100-only row has no second segment.
export function segmentFractions(row: Timed, axisEnd: number): { first: number; second: number } {
  if (!(axisEnd > 0)) return { first: 0, second: 0 }
  return { first: row.t_0_100_s / axisEnd, second: (row.t_100_200_s ?? 0) / axisEnd }
}

// The shared axis ends at the slowest time on the round's metric.
export function axisMax(rows: Timed[], toKmh: number): number {
  return rows.reduce((m, r) => Math.max(m, rowTotal(r, toKmh)), 0)
}

// Whole-second tick marks up to (and never past) the axis end, so no tick sits beyond where any
// bar can reach.
export function secondTicks(max: number): number[] {
  const top = Math.max(0, Math.floor(max))
  return Array.from({ length: top + 1 }, (_, i) => i)
}

export const fmtSeconds = (s: number): string => s.toFixed(2)

// ---- Teams / power units -------------------------------------------------------------------

export type StartView = 'drivers' | 'teams' | 'pu'

export interface PuGroupDef {
  name: string
  works_team: string
  teams: string[]
}

// One aggregated row: a team or a power unit, summarised by the MEDIAN of its cars on each metric
// (the pace chart's anchor too; for a two-car team it equals the mean, and one stall can't drag a
// pool of eight). The 100-200 segment is median(0-200) minus median(0-100), so the bar always ends
// at the group's median total.
export interface GroupRow extends Timed {
  key: string
  label: string
  // Team whose colour marks the row: the team itself, or a power unit's works team.
  colorTeam: string
  n: number
  v_75m_kmh: number | null
}

export function median(values: number[]): number | null {
  if (values.length === 0) return null
  const v = [...values].sort((a, b) => a - b)
  const mid = Math.floor(v.length / 2)
  return v.length % 2 ? v[mid] : (v[mid - 1] + v[mid]) / 2
}

const present = (xs: (number | null)[]): number[] => xs.filter((x): x is number => x != null)

export function aggregateRows(
  rows: StartRow[],
  view: 'teams' | 'pu',
  puGroups: PuGroupDef[],
  toKmh: number,
): GroupRow[] {
  const groups = new Map<string, { label: string; colorTeam: string; cars: StartRow[] }>()
  const puOf = new Map<string, PuGroupDef>()
  for (const g of puGroups) for (const t of g.teams) puOf.set(t, g)

  for (const r of rows) {
    if (!r.constructor) continue
    let key: string, label: string, colorTeam: string
    if (view === 'teams') {
      key = label = colorTeam = r.constructor
    } else {
      const g = puOf.get(r.constructor)
      if (!g) continue // not in the supply map: left out of the power-unit view, never guessed
      key = label = g.name
      colorTeam = g.works_team
    }
    const entry = groups.get(key) ?? { label, colorTeam, cars: [] }
    entry.cars.push(r)
    groups.set(key, entry)
  }

  const out: GroupRow[] = []
  for (const [key, g] of groups) {
    const t100 = median(present(g.cars.map((c) => c.t_0_100_s)))
    if (t100 == null) continue
    const t200 = toKmh === 200 ? median(present(g.cars.map((c) => c.t_0_200_s))) : null
    out.push({
      key,
      label: g.label,
      colorTeam: g.colorTeam,
      n: g.cars.length,
      t_0_100_s: t100,
      t_0_200_s: t200,
      t_100_200_s: t200 == null ? null : t200 - t100,
      v_75m_kmh: median(present(g.cars.map((c) => c.v_75m_kmh))),
    })
  }
  return out.sort((a, b) => rowTotal(a, toKmh) - rowTotal(b, toKmh))
}

// ---- Sorting -------------------------------------------------------------------------------

export type StartSort = 'total' | 'first' | 'second'

// Fastest first on the chosen metric: the whole run (to 200, or to 100 on a 100-only round), the
// 0-100 leg, or the 100-200 leg. A row without the metric goes last; ties fall back to the total
// so the order never depends on input order.
export function sortRows<T extends Timed>(rows: T[], by: StartSort, toKmh: number): T[] {
  const key = (r: T): number | null =>
    by === 'first' ? r.t_0_100_s : by === 'second' ? r.t_100_200_s : rowTotal(r, toKmh)
  return [...rows].sort((a, b) => {
    const ka = key(a)
    const kb = key(b)
    if (ka == null || kb == null) return ka == null && kb == null ? 0 : ka == null ? 1 : -1
    return ka - kb || rowTotal(a, toKmh) - rowTotal(b, toKmh)
  })
}
