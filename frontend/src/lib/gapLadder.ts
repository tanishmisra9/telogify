// Pure helpers for the Season Ranking panel's pace gap ladder: one bar per team, length
// proportional to its gap behind the season's best.

// Re-anchor a column to its own best: the best (smallest) team shows "best", every other
// team shows its gap to that best. Moved from SeasonPage.tsx so it's independently testable.
export function gapCells(values: (number | null)[], fmtGap: (d: number) => string): (string | null)[] {
  const present = values.filter((v): v is number => v != null)
  if (present.length === 0) return values.map(() => null)
  const best = Math.min(...present)
  return values.map((v) => (v == null ? null : v === best ? 'best' : fmtGap(v - best)))
}

// Each value's gap-to-best as a fraction (0..1) of the largest gap in the field, for the bar's
// width. The leader is exactly 0 (an honest zero-length bar). Raw fractions only — a non-zero
// gap that would round to an invisible sliver is a rendering concern, handled by a CSS
// min-width on the bar element, not by inflating the number here.
export function barFractions(values: (number | null)[]): (number | null)[] {
  const present = values.filter((v): v is number => v != null)
  if (present.length === 0) return values.map(() => null)
  const best = Math.min(...present)
  const worst = Math.max(...present)
  const span = worst - best
  if (span === 0) return values.map((v) => (v == null ? null : 0))
  return values.map((v) => (v == null ? null : (v - best) / span))
}

// Whole-second tick marks for the header axis. Floored, not ceiled: a bar's width is always a
// fraction of the field's actual worst gap (barFractions above), so the axis has to share that
// same [0, maxGap] domain or its last tick would sit past where any bar actually reaches.
export function axisTicks(maxGap: number): number[] {
  const top = Math.max(0, Math.floor(maxGap))
  return Array.from({ length: top + 1 }, (_, i) => i)
}
