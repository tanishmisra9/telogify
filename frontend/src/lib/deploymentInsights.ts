import { binBySpeed } from '@/lib/seasonAccel'
import type { PuGroup, SeasonDeploymentScatter } from '@/lib/api'

// Bite-sized per-PU-manufacturer verdicts for the season Deployment section: the deterministic
// FALLBACK rendered only until `telogify run-season-deployment` has written the LLM verdicts
// (SeasonPage.tsx prefers the served `insights`, and falls back to this templated read of
// `scatter` when that list is empty, so the section is never blank). Templated, not generated:
// the model has no role here. Every number in a verdict is a median the reader could
// recompute from the dots on screen.
//
// Metric design is grounded in the real data shape (2026 R1-9): full-throttle no-brake samples
// live almost entirely above ~220 km/h, and no PU group's binned median actually crosses zero
// mid-range, so a naive "clipping onset speed" detector would stay silent. What separates the
// groups instead is (a) how hard they accelerate through the 250-290 km/h meat of the range
// ("punch": more deployment vs more harvesting), (b) what's left past 290 km/h ("hold": the
// clipping story, quantified as residual acceleration), and (c) how far each falls from punch
// to hold ("fade"). The fade templates always cite both numbers so a flat-but-weak profile
// reads as weak, never as "most constant" praise.

export interface PuVerdict {
  pu: string
  works_team: string
  teams: string[] // members actually present in the data
  header: string
  explanation_web: string
}

const MIN_BIN_N = 5 // a bin's median is meaningless on fewer samples
const MIN_BINS_PER_BAND = 2 // and a band needs at least two solid bins to be a read
const MID_LO = 250 // "punch" band: the shared meat of every group's coverage
const MID_HI = 290
// "hold" band: everything past MID_HI, where deployment running out shows as accel ~0
const RANK_EPSILON = 0.05 // m/s2; below this spread a metric distinguishes nobody

const median = (xs: number[]): number => {
  const s = [...xs].sort((a, b) => a - b)
  const mid = s.length / 2
  return s.length % 2 === 0 ? (s[mid - 1] + s[mid]) / 2 : s[Math.floor(mid)]
}

const fmt = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}`

interface GroupMetrics {
  group: PuGroup
  teams: string[]
  punch: number | null // median of bin medians, 250-290 km/h
  hold: number | null // median of bin medians, past 290 km/h
  fade: number | null // punch - hold
}

function measureGroup(group: PuGroup, scatter: SeasonDeploymentScatter): GroupMetrics {
  const teams = group.teams.filter((t) => (scatter[t] ?? []).length > 0)
  const pooled = teams.flatMap((t) => scatter[t])
  const bins = binBySpeed(pooled).filter((b) => b.n >= MIN_BIN_N)
  const mid = bins.filter((b) => b.speedMid >= MID_LO && b.speedMid < MID_HI).map((b) => b.medianAccel)
  const top = bins.filter((b) => b.speedMid >= MID_HI).map((b) => b.medianAccel)
  const punch = mid.length >= MIN_BINS_PER_BAND ? median(mid) : null
  const hold = top.length >= MIN_BINS_PER_BAND ? median(top) : null
  return { group, teams, punch, hold, fade: punch != null && hold != null ? punch - hold : null }
}

// rank 1 = best. Only when >= 3 groups have the value and it has real spread.
function rankGroups(ms: GroupMetrics[], get: (m: GroupMetrics) => number | null, better: 'low' | 'high') {
  const present = ms
    .map((m) => ({ name: m.group.name, v: get(m) }))
    .filter((x): x is { name: string; v: number } => x.v != null)
  if (present.length < 3) return null
  if (Math.max(...present.map((x) => x.v)) - Math.min(...present.map((x) => x.v)) < RANK_EPSILON) return null
  present.sort((a, b) => (better === 'low' ? a.v - b.v : b.v - a.v))
  const out: Record<string, { rank: number; total: number }> = {}
  present.forEach((x, i) => (out[x.name] = { rank: i + 1, total: present.length }))
  return out
}

interface Candidate {
  order: number // metric priority: punch, hold, fade
  extremity: number // 1 = outright first/last, 0.5 = a rank-2 silver
  headline: string // short, number-free phrase for the panel header
  clause: string // full clause with the number, for the body
}

export function deploymentInsights(scatter: SeasonDeploymentScatter, groups: PuGroup[]): PuVerdict[] {
  const ms = groups.map((g) => measureGroup(g, scatter)).filter((m) => m.teams.length > 0)

  const punchRanks = rankGroups(ms, (m) => m.punch, 'high')
  const holdRanks = rankGroups(ms, (m) => m.hold, 'high')
  const fadeRanks = rankGroups(ms, (m) => m.fade, 'low') // small fade = most constant
  // Nothing rankable at all (fewer than 3 groups with data): silence beats unanchored claims.
  if (!punchRanks && !holdRanks && !fadeRanks) return []

  // Best to worst, matching the backend's rank_groups_best_to_worst: punch (250-290 km/h,
  // the band every group covers) descending, hold as tiebreak, no-punch groups last.
  const ranked = [...ms].sort((a, b) => {
    if ((a.punch == null) !== (b.punch == null)) return a.punch == null ? 1 : -1
    if (a.punch != null && b.punch != null && a.punch !== b.punch) return b.punch - a.punch
    return (b.hold ?? -Infinity) - (a.hold ?? -Infinity)
  })

  return ranked
    .filter((m) => m.punch != null || m.hold != null)
    .map((m) => {
      const cands: Candidate[] = []

      const p = punchRanks?.[m.group.name]
      if (p && m.punch != null) {
        if (p.rank === 1)
          cands.push({ order: 0, extremity: 1, headline: 'holds its acceleration best through the mid-range', clause: `strongest mid-range deployment (${fmt(m.punch)} m/s² through ${MID_LO}-${MID_HI} km/h)` })
        else if (p.rank === p.total)
          cands.push({ order: 0, extremity: 1, headline: 'sheds acceleration earliest through the mid-range', clause: `leanest mid-range deployment (${fmt(m.punch)} m/s² through ${MID_LO}-${MID_HI} km/h), consistent with heavier harvesting there` })
        else if (p.rank === 2)
          cands.push({ order: 0, extremity: 0.5, headline: 'is the second-strongest through the mid-range', clause: `2nd-strongest mid-range deployment (${fmt(m.punch)} m/s²)` })
      }

      const h = holdRanks?.[m.group.name]
      if (h && m.hold != null) {
        if (h.rank === 1)
          cands.push({ order: 1, extremity: 1, headline: 'keeps pulling hardest at top speed', clause: `holds its deployment best at top speed (${fmt(m.hold)} m/s² past ${MID_HI} km/h)` })
        else if (h.rank === h.total)
          cands.push({
            order: 1,
            extremity: 1,
            headline: m.hold <= 0 ? 'runs out of shove first at top speed' : 'has the weakest top-speed hold',
            clause:
              m.hold <= 0
                ? `first to run dry up top (${fmt(m.hold)} m/s² past ${MID_HI} km/h)`
                : `weakest top-speed hold (${fmt(m.hold)} m/s² past ${MID_HI} km/h)`,
          })
        else if (h.rank === 2)
          cands.push({ order: 1, extremity: 0.5, headline: 'has the second-best top-speed hold', clause: `2nd-best top-speed hold (${fmt(m.hold)} m/s²)` })
      }

      const f = fadeRanks?.[m.group.name]
      if (f && m.punch != null && m.hold != null) {
        // Both fade templates cite punch AND hold, so "most constant" can never dress up a
        // profile that is simply weak everywhere; the low numbers are right there.
        if (f.rank === f.total)
          cands.push({ order: 2, extremity: 1, headline: 'sheds the most once deployment runs out', clause: `sheds the most once deployment runs out (${fmt(m.punch)} mid-range down to ${fmt(m.hold)} m/s² past ${MID_HI} km/h)` })
        else if (f.rank === 1)
          cands.push({ order: 2, extremity: 1, headline: 'stays the most constant across the range', clause: `most constant deployment across the range (${fmt(m.punch)} mid-range vs ${fmt(m.hold)} up top)` })
      }

      cands.sort((a, b) => b.extremity - a.extremity || a.order - b.order)
      const picked = cands.slice(0, 2)
      const header =
        picked.length === 0
          ? `${m.group.name} power sits mid-pack on deployment`
          : `${m.group.name} power ${picked[0].headline}`
      const explanation_web =
        picked.length === 0
          ? 'Sits between the extremes on every deployment measure here.'
          : `${picked
              .map((c) => c.clause)
              .join('; ')
              .replace(/^./, (c) => c.toUpperCase())}.`

      return { pu: m.group.name, works_team: m.group.works_team, teams: m.teams, header, explanation_web }
    })
}
