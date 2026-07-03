import type { SeasonConstructorRow } from '@/lib/api'

// Templated, not generated. For each season metric we find the leader and the laggard
// across all teams; the leading team gets that metric's strength template, the trailing
// team gets its weakness template, each with the real number filled in. The model has no
// role here, exactly like qualiSummary.ts one register up. Mid-pack teams that neither lead
// nor trail any metric get a neutral fallback rather than invented copy.

export interface TeamSummary {
  strengths: string[]
  weaknesses: string[]
}

interface Metric {
  get: (r: SeasonConstructorRow) => number | null
  better: 'low' | 'high'
  minRounds?: number // require this many rounds of data before the metric can lead/trail
  strength: (v: number) => string | null
  weakness: (v: number) => string | null
}

const METRICS: Metric[] = [
  {
    get: (r) => r.pace_gap.mean,
    better: 'low',
    strength: () => 'Sets the race-pace benchmark of the field',
    weakness: (v) => `Slowest race pace, ${v.toFixed(3)}s off the field's best on average`,
  },
  {
    get: (r) => r.quali_gap_pct.mean,
    better: 'low',
    strength: () => 'Sharpest one-lap pace in qualifying',
    weakness: (v) => `Weakest qualifying, +${v.toFixed(2)}% off the fastest`,
  },
  {
    get: (r) => r.top_speed_deficit_kmh,
    better: 'low',
    strength: () => 'Quickest in a straight line',
    weakness: (v) => `Down ${v.toFixed(0)} km/h in a straight line`,
  },
  {
    get: (r) => r.sector_dominance_count,
    better: 'high',
    strength: (v) => `Led ${v} qualifying sector${v === 1 ? '' : 's'} across the season`,
    weakness: () => null, // a low sector count is not a distinct weakness worth stating
  },
  {
    get: (r) => r.tyre_deg_s_per_lap,
    better: 'low',
    // A near-zero or negative slope is not a quantifiable "amount of wear", so only cite the
    // number when it is a real positive rate.
    strength: (v) => (v > 0 ? `Kindest on its tyres, ${v.toFixed(3)}s/lap of wear` : 'Kindest on its tyres across the season'),
    weakness: (v) => `Heaviest tyre wear, ${v.toFixed(3)}s/lap`,
  },
  {
    get: (r) => (r.pace_gap.n >= 3 ? r.pace_gap.spread : null),
    better: 'low',
    minRounds: 3,
    strength: () => 'Most consistent race pace weekend to weekend',
    weakness: (v) => `Race pace swings widely by circuit (±${v.toFixed(2)}s)`,
  },
]

export function seasonSummary(rows: SeasonConstructorRow[]): Record<string, TeamSummary> {
  const out: Record<string, TeamSummary> = {}
  for (const r of rows) out[r.constructor] = { strengths: [], weaknesses: [] }

  for (const metric of METRICS) {
    const present = rows
      .map((r) => ({ team: r.constructor, v: metric.get(r) }))
      .filter((x): x is { team: string; v: number } => x.v != null)
    if (present.length < 2) continue

    const best = metric.better === 'low' ? Math.min(...present.map((x) => x.v)) : Math.max(...present.map((x) => x.v))
    const worst = metric.better === 'low' ? Math.max(...present.map((x) => x.v)) : Math.min(...present.map((x) => x.v))
    if (best === worst) continue

    const leader = present.find((x) => x.v === best)!
    const laggard = present.find((x) => x.v === worst)!
    const s = metric.strength(best)
    const w = metric.weakness(worst)
    if (s) out[leader.team].strengths.push(s)
    if (w) out[laggard.team].weaknesses.push(w)
  }

  for (const r of rows) {
    const t = out[r.constructor]
    if (t.strengths.length === 0 && t.weaknesses.length === 0) {
      t.strengths.push('Solid midfield runner with no standout trait this season')
    }
  }
  return out
}
