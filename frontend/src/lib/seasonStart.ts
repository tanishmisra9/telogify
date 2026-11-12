// Pure helpers for the season Race starts chart, so no maths lives in the component.
import type { SeasonStartRow } from '@/lib/api'

// "+3.4%": % slower than the round's best start. The best group on a round is "+0.0%".
export const formatGap = (pct: number): string => `+${pct.toFixed(1)}%`

// Rank movement on recent form vs the whole season, as a short legend suffix: up/down places, a
// dash for no movement, nothing at all when there are too few rounds to say.
export function formArrow(places: number | null): string {
  if (places == null) return ''
  if (places > 0) return `▲${places}`
  if (places < 0) return `▼${-places}`
  return '–'
}

// Legend value: the recency-weighted season gap and the form arrow.
export function legendValue(row: SeasonStartRow): string {
  if (row.weighted_gap_pct == null) return ''
  return [formatGap(row.weighted_gap_pct), formArrow(row.form_places)].filter(Boolean).join('  ')
}

// A whole-percent axis that always reaches the data, in steps that stay readable: 0 at the top.
export function niceAxis(maxPct: number): { max: number; ticks: number[] } {
  const step = maxPct <= 12 ? 2 : maxPct <= 30 ? 5 : 10
  const max = Math.max(step, Math.ceil(maxPct / step) * step)
  return { max, ticks: Array.from({ length: max / step + 1 }, (_, i) => i * step) }
}

// What a hovered point says.
export function pointCopy(
  label: string,
  eventName: string | undefined,
  p: SeasonStartRow['points'][number],
): { title: string; lines: string[] } {
  const lines = [
    p.gap_pct === 0 ? 'Best start of the round' : `${p.gap_pct.toFixed(1)}% behind the best (+${p.gap_s.toFixed(2)} s)`,
    p.metric === 100 ? '0 to 100 km/h only this round' : 'Full run, 0 to 200 km/h',
  ]
  if (p.n_cars === 1) lines.push('1 car')
  return { title: `${label}, ${eventName ?? `round ${p.round}`}`, lines }
}

// Explains the arrow in words, for the legend row's tooltip / aria text.
export function formSentence(row: {
  form_places: number | null
  rank_weighted: number | null
  rank_flat: number | null
}): string | null {
  if (row.form_places == null || row.rank_weighted == null || row.rank_flat == null) return null
  const move =
    row.form_places === 0
      ? 'Holds the same place'
      : `${row.form_places > 0 ? 'Gains' : 'Loses'} ${Math.abs(row.form_places)} place${Math.abs(row.form_places) === 1 ? '' : 's'}`
  return `${move} on recent form: #${row.rank_weighted} recently, #${row.rank_flat} over the season`
}
