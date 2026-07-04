import type { CarCharacterRow } from '@/lib/api'

// Deterministic, quantified qualifying reads derived from each team's best clean lap (the only
// laps stored, so a driver who crashed or never set a representative lap simply isn't here — the
// crash guardrail is structural). No model, no fabricated result: we never claim "pole" or a grid
// position, only what the telemetry of the compared laps shows. Cross-channel trades (downforce vs
// straight-line, throttle commitment) are preferred over the obvious raw one-lap gap.

export interface QualiInsight {
  kicker: string
  team: string
  text: string // numbers get reddened by emphasize() at render
}

const pct = (v: number) => Math.round(v * 100)
const kmh = (v: number) => Math.round(v)
const ordinal = (n: number) => {
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`
}

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b)
  const m = Math.floor(s.length / 2)
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}

// rank 1 = best; returns a map team -> rank over the given accessor (higher is better)
function rankByDesc(rows: CarCharacterRow[], get: (r: CarCharacterRow) => number | null) {
  const present = rows
    .map((r) => ({ team: r.constructor, v: get(r) }))
    .filter((x): x is { team: string; v: number } => x.v != null)
    .sort((a, b) => b.v - a.v)
  const out: Record<string, number> = {}
  present.forEach((x, i) => (out[x.team] = i + 1))
  return out
}

export function qualiInsights(rows: CarCharacterRow[], fastestCornerNumber: number | null): QualiInsight[] {
  if (rows.length < 3) return []

  const maxTop = Math.max(...rows.map((r) => r.top_speed_kmh))
  const corners = rows.filter((r) => r.fastest_corner_kmh != null)
  const maxCorner = corners.length ? Math.max(...corners.map((r) => r.fastest_corner_kmh!)) : null
  const cornerLabel = fastestCornerNumber != null ? `turn ${fastestCornerNumber}` : 'the quickest corner'

  const topRank = rankByDesc(rows, (r) => r.top_speed_kmh)
  const cornerRank = rankByDesc(rows, (r) => r.fastest_corner_kmh)

  // priority-ordered candidates; the first two valid ones (about different teams) win, so
  // cross-channel trades outrank the raw gap.
  const candidates: (QualiInsight & { priority: number })[] = []

  // 1. Aero trade: the team whose corner-speed rank most outstrips its straight-line rank (or vice
  //    versa). A genuine cross-channel read a fan can't get from the timing screen.
  if (maxCorner != null) {
    let pick: { team: string; trade: number; r: CarCharacterRow } | null = null
    for (const r of corners) {
      const trade = topRank[r.constructor] - cornerRank[r.constructor] // + => corners >> straights
      if (!pick || Math.abs(trade) > Math.abs(pick.trade)) pick = { team: r.constructor, trade, r }
    }
    if (pick && Math.abs(pick.trade) >= 3) {
      const r = pick.r
      if (pick.trade > 0) {
        const topDef = kmh(maxTop - r.top_speed_kmh)
        candidates.push({
          priority: 1,
          kicker: 'Aero trade',
          team: r.constructor,
          text: `${r.constructor} leaned hardest on downforce in qualifying: ${kmh(r.fastest_corner_kmh!)} km/h through ${cornerLabel}, ${ordinal(cornerRank[r.constructor])}-quickest in the field, but ${topDef} km/h down the straight.`,
        })
      } else {
        const cornerDef = kmh(maxCorner - r.fastest_corner_kmh!)
        candidates.push({
          priority: 1,
          kicker: 'Aero trade',
          team: r.constructor,
          text: `${r.constructor} ran the skinniest wing of the field: ${ordinal(topRank[r.constructor])}-fastest in a straight line, but ${cornerDef} km/h slower than the best through ${cornerLabel}.`,
        })
      }
    }
  }

  // 2. Throttle commitment: who kept the throttle pinned longest (or shortest) vs the field median.
  const ftMed = median(rows.map((r) => r.full_throttle_pct))
  const ftSorted = [...rows].sort((a, b) => b.full_throttle_pct - a.full_throttle_pct)
  const ftHigh = ftSorted[0]
  const ftLow = ftSorted[ftSorted.length - 1]
  const highDev = ftHigh.full_throttle_pct - ftMed
  const lowDev = ftMed - ftLow.full_throttle_pct
  if (Math.max(highDev, lowDev) >= 0.03) {
    if (highDev >= lowDev) {
      candidates.push({
        priority: 2,
        kicker: 'Full throttle',
        team: ftHigh.constructor,
        text: `${ftHigh.constructor} held full throttle for ${pct(ftHigh.full_throttle_pct)}% of the lap, the most of any car, the lowest-drag lap in the field.`,
      })
    } else {
      candidates.push({
        priority: 2,
        kicker: 'Full throttle',
        team: ftLow.constructor,
        text: `${ftLow.constructor} spent the least time at full throttle, just ${pct(ftLow.full_throttle_pct)}% of the lap, the draggiest car or the one least able to put its power down.`,
      })
    }
  }

  // 3. Slow-corner grip: the highest minimum speed, by a clear margin over the next car.
  const gripSorted = [...rows].sort((a, b) => b.min_speed_kmh - a.min_speed_kmh)
  if (gripSorted.length >= 2 && gripSorted[0].min_speed_kmh - gripSorted[1].min_speed_kmh >= 2) {
    const g = gripSorted[0]
    candidates.push({
      priority: 3,
      kicker: 'Slow-corner grip',
      team: g.constructor,
      text: `${g.constructor} carried ${kmh(g.min_speed_kmh)} km/h through the slowest point of the lap, the highest minimum speed in the field, a read on mechanical grip.`,
    })
  }

  // 4. Raw one-lap gap: always available, lowest priority (a fan can half-read this off the times).
  const lapSorted = [...rows].sort((a, b) => a.lap_time_s - b.lap_time_s)
  const gap = lapSorted[lapSorted.length - 1].lap_time_s - lapSorted[0].lap_time_s
  if (gap >= 0.05) {
    candidates.push({
      priority: 4,
      kicker: 'One-lap gap',
      team: lapSorted[lapSorted.length - 1].constructor,
      text: `${lapSorted[lapSorted.length - 1].constructor}'s best lap was ${gap.toFixed(3)}s off the quickest of the compared teams, the widest one-lap gap in the field.`,
    })
  }

  // Two insights, but never both about the same car: take the top-priority one, then the best
  // remaining that features a different team (a high-downforce car otherwise lands both the aero
  // trade AND the low-throttle read, which is one story told twice).
  const sorted = candidates.sort((a, b) => a.priority - b.priority)
  const picked: typeof sorted = []
  for (const c of sorted) {
    if (picked.length === 2) break
    if (picked.some((p) => p.team === c.team)) continue
    picked.push(c)
  }
  return picked.map(({ kicker, team, text }) => ({ kicker, team, text }))
}
