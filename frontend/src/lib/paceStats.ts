import type { PaceStint } from '@/lib/api'

export interface BoxStats {
  mean: number
  median: number
  q1: number
  q3: number
  whisker_low: number
  whisker_high: number
  outliers: number[]
  n_laps: number
  compounds: string[]
}

export interface PaceRow {
  id: string
  label: string
  team: string | null
  stats: BoxStats
  gap_to_fastest_s: number
}

const COMPOUND_TAG: Record<string, string> = {
  SOFT: 'S',
  MEDIUM: 'M',
  HARD: 'H',
  INTERMEDIATE: 'I',
  WET: 'W',
}

function quantile(sorted: number[], p: number): number {
  const idx = (sorted.length - 1) * p
  const lo = Math.floor(idx)
  const hi = Math.ceil(idx)
  if (lo === hi) return sorted[lo]
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo)
}

function boxStats(values: number[], compounds: string[]): BoxStats {
  const sorted = [...values].sort((a, b) => a - b)
  const q1 = quantile(sorted, 0.25)
  const median = quantile(sorted, 0.5)
  const q3 = quantile(sorted, 0.75)
  const iqr = q3 - q1
  const fenceLo = q1 - 1.5 * iqr
  const fenceHi = q3 + 1.5 * iqr

  const inFence = sorted.filter((v) => v >= fenceLo && v <= fenceHi)
  const whisker_low = inFence.length ? inFence[0] : sorted[0]
  const whisker_high = inFence.length ? inFence[inFence.length - 1] : sorted[sorted.length - 1]
  const outliers = sorted.filter((v) => v < fenceLo || v > fenceHi)

  return {
    mean: sorted.reduce((a, b) => a + b, 0) / sorted.length,
    median,
    q1,
    q3,
    whisker_low,
    whisker_high,
    outliers,
    n_laps: sorted.length,
    compounds,
  }
}

function compoundTags(compounds: Array<string | null>): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const c of compounds) {
    const tag = c ? COMPOUND_TAG[c] : undefined
    if (tag && !seen.has(tag)) {
      seen.add(tag)
      out.push(tag)
    }
  }
  return out
}

function buildRows(
  groups: Map<string, { team: string | null; laps: number[]; compounds: Array<string | null> }>,
): PaceRow[] {
  const rows: PaceRow[] = []
  for (const [id, g] of groups) {
    if (g.laps.length === 0) continue
    rows.push({
      id,
      label: id,
      team: g.team,
      stats: boxStats(g.laps, compoundTags(g.compounds)),
      gap_to_fastest_s: 0,
    })
  }
  rows.sort((a, b) => a.stats.median - b.stats.median)
  if (rows.length) {
    const fastest = rows[0].stats.median
    for (const r of rows) r.gap_to_fastest_s = r.stats.median - fastest
  }
  return rows
}

export function driverRows(stints: PaceStint[]): PaceRow[] {
  const groups = new Map<string, { team: string | null; laps: number[]; compounds: Array<string | null> }>()
  for (const st of stints) {
    const g = groups.get(st.driver) ?? { team: st.constructor, laps: [], compounds: [] }
    g.laps.push(...(st.lap_times ?? []))
    g.compounds.push(st.compound)
    groups.set(st.driver, g)
  }
  return buildRows(groups)
}

export function constructorRows(stints: PaceStint[]): PaceRow[] {
  const groups = new Map<string, { team: string | null; laps: number[]; compounds: Array<string | null> }>()
  for (const st of stints) {
    const key = st.constructor ?? '?'
    const g = groups.get(key) ?? { team: st.constructor, laps: [], compounds: [] }
    g.laps.push(...(st.lap_times ?? []))
    g.compounds.push(st.compound)
    groups.set(key, g)
  }
  return buildRows(groups)
}
