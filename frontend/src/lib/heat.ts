// Restrained single-accent heatmap: rank each column, then shade with the accent color
// at an opacity proportional to rank, so the eye finds the extremes without introducing
// a second hue (the design system holds to one amber accent).

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

export function heatBg(rank: number, total: number, opacityMax = 0.5): string {
  if (total <= 1) return 'transparent'
  const t = 1 - (rank - 1) / (total - 1)
  const pct = Math.round(t * opacityMax * 100)
  return `color-mix(in oklch, var(--color-accent) ${pct}%, transparent)`
}
