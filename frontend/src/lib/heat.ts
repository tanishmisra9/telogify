// Restrained single-accent heatmap: rank each column, then shade with the accent color
// at an opacity proportional to rank, so the eye finds the extremes without introducing
// a second hue (the design system holds to one amber accent).
//
// The falloff is cubic, not linear: a linear ramp puts visible color on nearly every cell
// in an 11-row table (2nd place reads almost as strong as 1st), which turns the table into
// a wash of pink instead of a scan aid. Cubing `t` keeps only the real standouts (top 2-3)
// legible and lets the rest fade toward transparent almost immediately.

export function rankDesc(values: (number | null)[]): number[] {
  const indexed = values.map((v, i) => ({ v: v ?? -Infinity, i }))
  indexed.sort((a, b) => b.v - a.v)
  const ranks = new Array(values.length).fill(0)
  indexed.forEach(({ i }, position) => (ranks[i] = position + 1))
  return ranks
}

/** Rank where the lowest value is best (e.g. lap time). */
export function rankAsc(values: (number | null)[]): number[] {
  return rankDesc(values.map((v) => (v == null ? null : -v)))
}

export function heatBg(rank: number, total: number, opacityMax = 0.22): string {
  if (total <= 1) return 'transparent'
  const t = 1 - (rank - 1) / (total - 1)
  const pct = Math.round(t * t * t * opacityMax * 100)
  return `color-mix(in oklch, var(--color-accent) ${pct}%, transparent)`
}
