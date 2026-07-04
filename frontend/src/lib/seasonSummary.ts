import type { SeasonConstructorRow } from '@/lib/api'

// Every car gets ONE strength and ONE weakness, both field-relative and quantified. For each
// season metric we rank all teams; a team's strength is the metric it ranks best on, its
// weakness the metric it ranks worst on, phrased with its actual position and number. No team is
// left "midfield" and no strength is invented: a dominant car's weakness is simply its weakest
// relative area ("only 3rd-quickest in a straight line"), which is honest, not misleading.
// Templated, not generated: the model has no role here, same register as qualiInsights.ts.

export interface Trait {
  text: string // the headline, e.g. "2nd-fastest race pace"
  detail: string // the number, e.g. "+0.21s" (may be empty)
}
export interface TeamSummary {
  strength: Trait | null
  weakness: Trait | null
}

const ordinal = (n: number) => {
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`
}

interface Metric {
  get: (r: SeasonConstructorRow) => number | null
  better: 'low' | 'high'
  noun: string // "race pace"
  adj: string // superlative stem: "quickest", "fastest", "kindest"...
  best: string // rank-1 headline
  worst: string // last-place headline
  detail: (v: number) => string // the number shown alongside
}

const METRICS: Metric[] = [
  {
    get: (r) => r.pace_gap.mean,
    better: 'low',
    noun: 'race pace',
    adj: 'quickest',
    best: 'Sets the race-pace benchmark',
    worst: 'Slowest race pace in the field',
    detail: (v) => (v <= 0.0005 ? '' : `+${v.toFixed(2)}s`),
  },
  {
    get: (r) => r.quali_gap_pct.mean,
    better: 'low',
    noun: 'one-lap pace',
    adj: 'sharpest',
    best: 'Sharpest one-lap pace in qualifying',
    worst: 'Weakest one-lap pace in qualifying',
    detail: (v) => (v <= 0.0005 ? '' : `+${v.toFixed(2)}%`),
  },
  {
    get: (r) => r.top_speed_deficit_kmh,
    better: 'low',
    noun: 'straight-line speed',
    adj: 'fastest',
    best: 'Fastest in a straight line',
    worst: 'Slowest in a straight line',
    detail: (v) => (v < 0.5 ? '' : `-${Math.round(v)} km/h`),
  },
  {
    get: (r) => r.tyre_deg_s_per_lap,
    better: 'low',
    noun: 'tyre wear',
    adj: 'kindest',
    best: 'Kindest on its tyres',
    worst: 'Heaviest tyre wear in the field',
    detail: (v) => (v <= 0 ? '' : `${v.toFixed(3)}s/lap`),
  },
  {
    get: (r) => r.sector_dominance_count,
    better: 'high',
    noun: 'qualifying sectors',
    adj: 'most',
    best: 'Most qualifying sectors won',
    worst: 'Fewest qualifying sectors won',
    detail: (v) => `${v} won`,
  },
  {
    get: (r) => (r.pace_gap.n >= 3 ? r.pace_gap.spread : null),
    better: 'low',
    noun: 'weekend-to-weekend form',
    adj: 'steadiest',
    best: 'Steadiest race pace, weekend to weekend',
    worst: 'Swingiest race pace by circuit',
    detail: (v) => `±${v.toFixed(2)}s`,
  },
]

// Rank each team on a metric (1 = best). Returns a map constructor -> {rank, total, value}, only
// for teams that have a value, and only when >= 3 teams have data (so a rank means something).
function rankMetric(rows: SeasonConstructorRow[], m: Metric) {
  const present = rows
    .map((r) => ({ team: r.constructor, v: m.get(r) }))
    .filter((x): x is { team: string; v: number } => x.v != null)
  if (present.length < 3) return null
  // No spread => the metric doesn't distinguish anyone; don't let it decide a strength/weakness.
  if (Math.min(...present.map((x) => x.v)) === Math.max(...present.map((x) => x.v))) return null
  present.sort((a, b) => (m.better === 'low' ? a.v - b.v : b.v - a.v))
  const out: Record<string, { rank: number; total: number; value: number; norm: number }> = {}
  present.forEach((x, i) => {
    out[x.team] = { rank: i + 1, total: present.length, value: x.v, norm: i / (present.length - 1) }
  })
  return out
}

function traitFor(m: Metric, rank: number, total: number, value: number, kind: 'strength' | 'weakness'): Trait {
  const detail = m.detail(value)
  if (kind === 'strength') {
    // the field leader is the reference; a gap next to "benchmark/best" reads as a contradiction
    if (rank === 1) return { text: m.best, detail: '' }
    return { text: `${ordinal(rank)}-${m.adj} ${m.noun}`, detail }
  }
  if (rank === total) return { text: m.worst, detail }
  // a soft weakness for a strong car: "Only 3rd-quickest in a straight line"
  return { text: `Only ${ordinal(rank)}-${m.adj} ${m.noun}`, detail }
}

export function seasonSummary(rows: SeasonConstructorRow[]): Record<string, TeamSummary> {
  const ranked = METRICS.map((m) => ({ m, r: rankMetric(rows, m) })).filter((x) => x.r)

  const out: Record<string, TeamSummary> = {}
  for (const row of rows) {
    const team = row.constructor
    // this team's position on every metric it has data for
    const positions = ranked
      .map(({ m, r }) => ({ m, ...r![team] }))
      .filter((p) => p.rank != null)
    if (positions.length === 0) {
      out[team] = { strength: null, weakness: null }
      continue
    }
    // strength = best relative position (lowest norm); weakness = worst (highest norm)
    const best = positions.reduce((a, b) => (b.norm < a.norm ? b : a))
    const worst = positions.reduce((a, b) => (b.norm > a.norm ? b : a))
    out[team] = {
      strength: traitFor(best.m, best.rank, best.total, best.value, 'strength'),
      // if a team's best and worst metric collapse to the same one (only one metric), skip weakness
      weakness: worst.m === best.m ? null : traitFor(worst.m, worst.rank, worst.total, worst.value, 'weakness'),
    }
  }
  return out
}
