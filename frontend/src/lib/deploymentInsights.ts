import { binBySpeed } from '@/lib/seasonAccel'
import type { SeasonDeploymentScatter } from '@/lib/api'

// Bite-sized per-PU-manufacturer verdicts for the season Deployment chart, computed from the
// exact scatter payload the chart renders. Templated, not generated: the model has no role here,
// same register as seasonSummary.ts. Every number in a verdict is a median the reader could
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

export interface PuGroup {
  name: string // 'Mercedes' (the PU manufacturer)
  worksTeam: string // team whose color marks the row
  teams: string[] // constructors running this PU, 2026
}

// 2026 power unit supply map. Season-specific by nature (like the hardcoded team colors).
export const PU_GROUPS: PuGroup[] = [
  { name: 'Mercedes', worksTeam: 'Mercedes', teams: ['Mercedes', 'Alpine', 'McLaren', 'Williams'] },
  { name: 'Ferrari', worksTeam: 'Ferrari', teams: ['Ferrari', 'Haas F1 Team', 'Cadillac'] },
  { name: 'Red Bull', worksTeam: 'Red Bull Racing', teams: ['Red Bull Racing', 'Racing Bulls'] },
  { name: 'Honda', worksTeam: 'Aston Martin', teams: ['Aston Martin'] },
  { name: 'Audi', worksTeam: 'Audi', teams: ['Audi'] },
]

export interface PuVerdict {
  name: string
  worksTeam: string
  teams: string[] // members actually present in the data
  text: string // 1-2 clause verdict, real numbers inline
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
  clause: string
}

export function deploymentInsights(scatter: SeasonDeploymentScatter): PuVerdict[] {
  const ms = PU_GROUPS.map((g) => measureGroup(g, scatter)).filter((m) => m.teams.length > 0)

  const punchRanks = rankGroups(ms, (m) => m.punch, 'high')
  const holdRanks = rankGroups(ms, (m) => m.hold, 'high')
  const fadeRanks = rankGroups(ms, (m) => m.fade, 'low') // small fade = most constant
  // Nothing rankable at all (fewer than 3 groups with data): silence beats unanchored claims.
  if (!punchRanks && !holdRanks && !fadeRanks) return []

  return ms
    .filter((m) => m.punch != null || m.hold != null)
    .map((m) => {
      const cands: Candidate[] = []

      const p = punchRanks?.[m.group.name]
      if (p && m.punch != null) {
        if (p.rank === 1)
          cands.push({ order: 0, extremity: 1, clause: `strongest mid-range deployment (${fmt(m.punch)} m/s² through ${MID_LO}-${MID_HI} km/h)` })
        else if (p.rank === p.total)
          cands.push({ order: 0, extremity: 1, clause: `leanest mid-range deployment (${fmt(m.punch)} m/s² through ${MID_LO}-${MID_HI} km/h), consistent with heavier harvesting there` })
        else if (p.rank === 2)
          cands.push({ order: 0, extremity: 0.5, clause: `2nd-strongest mid-range deployment (${fmt(m.punch)} m/s²)` })
      }

      const h = holdRanks?.[m.group.name]
      if (h && m.hold != null) {
        if (h.rank === 1)
          cands.push({ order: 1, extremity: 1, clause: `holds its deployment best at top speed (${fmt(m.hold)} m/s² past ${MID_HI} km/h)` })
        else if (h.rank === h.total)
          cands.push({
            order: 1,
            extremity: 1,
            clause:
              m.hold <= 0
                ? `first to run dry up top (${fmt(m.hold)} m/s² past ${MID_HI} km/h)`
                : `weakest top-speed hold (${fmt(m.hold)} m/s² past ${MID_HI} km/h)`,
          })
        else if (h.rank === 2)
          cands.push({ order: 1, extremity: 0.5, clause: `2nd-best top-speed hold (${fmt(m.hold)} m/s²)` })
      }

      const f = fadeRanks?.[m.group.name]
      if (f && m.punch != null && m.hold != null) {
        // Both fade templates cite punch AND hold, so "most constant" can never dress up a
        // profile that is simply weak everywhere; the low numbers are right there.
        if (f.rank === f.total)
          cands.push({ order: 2, extremity: 1, clause: `sheds the most once deployment runs out (${fmt(m.punch)} mid-range down to ${fmt(m.hold)} m/s² past ${MID_HI})` })
        else if (f.rank === 1)
          cands.push({ order: 2, extremity: 1, clause: `most constant deployment across the range (${fmt(m.punch)} mid-range vs ${fmt(m.hold)} up top)` })
      }

      cands.sort((a, b) => b.extremity - a.extremity || a.order - b.order)
      const picked = cands.slice(0, 2)
      const text =
        picked.length === 0
          ? 'Sits between the extremes on every deployment measure here.'
          : `${picked
              .map((c) => c.clause)
              .join('; ')
              .replace(/^./, (c) => c.toUpperCase())}.`

      return { name: m.group.name, worksTeam: m.group.worksTeam, teams: m.teams, text }
    })
}
