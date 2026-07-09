import type { SeasonConstructorRow } from '@/lib/api'

// Every car gets a field-relative read: up to its 3 strongest areas and 3 weakest, each quantified
// as a GAP to the field leader on that metric, so the numbers agree exactly with the ranking table
// above it (which is anchored to the leader too). A genuinely poor car keeps its weaknesses but
// shows no strength rather than dressing up a bottom-third rank with an up-mark. Templated, not
// generated: the model has no role here, same register as qualiInsights.ts.

export interface Trait {
  text: string // the headline, e.g. "2nd-quickest race pace"
  detail: string // the gap to the leader, e.g. "+0.21s" (may be empty)
}
export interface TeamSummary {
  strengths: Trait[] // best-first, up to MAX_TRAITS_PER_SIDE; empty when nothing qualifies
  weaknesses: Trait[] // worst-first, up to MAX_TRAITS_PER_SIDE
}

// A car can legitimately show more than one real strength/weakness (6 metrics are ranked below),
// so this isn't capped at a token single line per side; 3 is a ceiling to keep the card scannable,
// not a target every team is expected to fill.
const MAX_TRAITS_PER_SIDE = 3

const ordinal = (n: number) => {
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`
}

// a best metric this far down the field is not a real strength (bottom ~third of 11 teams)
const STRENGTH_CEILING = 0.65

interface Metric {
  get: (r: SeasonConstructorRow) => number | null
  better: 'low' | 'high'
  noun: string // "race pace"
  adj: string // superlative stem: "quickest", "fastest", "kindest"...
  best: string // rank-1 headline
  worst: string // last-place headline
  fmtGap: (gap: number) => string // gap to the field leader, '' when negligible
}

const METRICS: Metric[] = [
  {
    get: (r) => r.pace_gap.mean,
    better: 'low',
    noun: 'race pace',
    adj: 'quickest',
    best: 'Sets the race-pace benchmark',
    worst: 'Slowest race pace in the field',
    fmtGap: (g) => (g < 0.005 ? '' : `+${g.toFixed(2)}s`),
  },
  {
    get: (r) => r.quali_gap_pct.mean,
    better: 'low',
    noun: 'one-lap pace',
    adj: 'sharpest',
    best: 'Sharpest one-lap pace in qualifying',
    worst: 'Weakest one-lap pace in qualifying',
    fmtGap: (g) => (g < 0.005 ? '' : `+${g.toFixed(2)}%`),
  },
  {
    get: (r) => r.top_speed_deficit_kmh,
    better: 'low',
    noun: 'straight-line speed',
    adj: 'fastest',
    best: 'Fastest in a straight line',
    worst: 'Slowest in a straight line',
    fmtGap: (g) => (g < 0.5 ? '' : `-${Math.round(g)} km/h`),
  },
  {
    get: (r) => r.tyre_deg_s_per_lap,
    better: 'low',
    noun: 'tyre wear',
    adj: 'kindest',
    best: 'Kindest on its tyres',
    worst: 'Heaviest tyre wear in the field',
    fmtGap: (g) => (g < 0.0005 ? '' : `+${g.toFixed(3)}s/lap`),
  },
  {
    get: (r) => r.sector_dominance_count,
    better: 'high',
    noun: 'qualifying sectors',
    adj: 'most',
    best: 'Most qualifying sectors won',
    worst: 'Fewest qualifying sectors won',
    // count is cumulative over the season, so a gap-to-leader ("11 fewer") reads as a put-down
    // next to a top-3 rank; the ordinal headline already carries the meaning.
    fmtGap: () => '',
  },
  {
    get: (r) => (r.pace_gap.n >= 3 ? r.pace_gap.spread : null),
    better: 'low',
    noun: 'weekend-to-weekend form',
    adj: 'steadiest',
    best: 'Steadiest race pace, weekend to weekend',
    worst: 'Swingiest race pace by circuit',
    fmtGap: (g) => (g < 0.005 ? '' : `±${g.toFixed(2)}s`),
  },
]

interface Pos {
  m: Metric
  order: number
  rank: number
  total: number
  value: number
  leader: number
  norm: number
}

// Rank each team on a metric (1 = best). Returns constructor -> {rank, total, value, leader, norm},
// only for teams with a value, and only when >= 3 teams have data AND the metric has spread (a
// tied metric distinguishes no one). `leader` is the best team's value, for gap-to-leader details.
function rankMetric(rows: SeasonConstructorRow[], m: Metric) {
  const present = rows
    .map((r) => ({ team: r.constructor, v: m.get(r) }))
    .filter((x): x is { team: string; v: number } => x.v != null)
  if (present.length < 3) return null
  if (Math.min(...present.map((x) => x.v)) === Math.max(...present.map((x) => x.v))) return null
  present.sort((a, b) => (m.better === 'low' ? a.v - b.v : b.v - a.v))
  const leader = present[0].v
  const out: Record<string, { rank: number; total: number; value: number; leader: number; norm: number }> = {}
  present.forEach((x, i) => {
    out[x.team] = { rank: i + 1, total: present.length, value: x.v, leader, norm: i / (present.length - 1) }
  })
  return out
}

function traitFor(p: Pos, kind: 'strength' | 'weakness'): Trait {
  const gap = p.m.better === 'low' ? p.value - p.leader : p.leader - p.value
  if (kind === 'strength') {
    if (p.rank === 1) return { text: p.m.best, detail: '' }
    return { text: `${ordinal(p.rank)}-${p.m.adj} ${p.m.noun}`, detail: p.m.fmtGap(gap) }
  }
  if (p.rank === p.total) return { text: p.m.worst, detail: p.m.fmtGap(gap) }
  // a soft weakness for a strong car: "Only 3rd-quickest in a straight line"
  return { text: `Only ${ordinal(p.rank)}-${p.m.adj} ${p.m.noun}`, detail: p.m.fmtGap(gap) }
}

export function seasonSummary(rows: SeasonConstructorRow[]): Record<string, TeamSummary> {
  const ranked = METRICS.map((m, order) => ({ m, order, r: rankMetric(rows, m) })).filter((x) => x.r)

  const out: Record<string, TeamSummary> = {}
  for (const row of rows) {
    const team = row.constructor
    const positions: Pos[] = ranked
      .filter(({ r }) => r![team])
      .map(({ m, order, r }) => ({ m, order, ...r![team] }))
    // best relative area first, worst last; tie-break by metric order so the same metric never
    // gets picked for both sides when a team ranks identically across several channels.
    positions.sort((a, b) => a.norm - b.norm || a.order - b.order)

    // Split without overlap: a front slice for strengths, a back slice for weaknesses. A team with
    // only 1-2 ranked metrics can't fill three deep on both sides, and any metric left in the
    // middle (neither clearly a strength nor a weakness) is dropped rather than forced onto a side.
    const perSide = Math.min(MAX_TRAITS_PER_SIDE, Math.floor(positions.length / 2))
    out[team] = {
      // don't dress up a bottom-third best as a strength; a genuinely poor car shows none
      strengths: positions
        .slice(0, perSide)
        .filter((p) => p.norm <= STRENGTH_CEILING)
        .map((p) => traitFor(p, 'strength')),
      // a team leading on more metrics than fit in the strength slice can have surplus rank-1
      // metrics tie-broken into this back slice (rank 1 always normalizes to 0); "Only 1st-X"
      // would be a contradiction, so an outright #1 never counts as a weakness
      weaknesses: positions
        .slice(positions.length - perSide)
        .reverse()
        .filter((p) => p.rank > 1)
        .map((p) => traitFor(p, 'weakness')),
    }
  }
  return out
}
