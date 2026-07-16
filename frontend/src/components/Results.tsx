import { driverName } from '@/lib/drivers'
import { resolveTeamColor, teamColorWithAlpha } from '@/lib/teamColors'
import type { ResultRow } from '@/lib/api'

// No items-center: a cell with genuinely empty content (no points scored) would then get a
// shorter box than its text-bearing row-mates, leaving a gap in the team-color wash. Default
// stretch fills every cell to the row's full height instead; the shared py-3 padding already
// centers content visually.
// First column is the full-height team-color bar (the F1 timing-graphics idiom) — a real grid
// cell, not a border-left, so cell-stretch gives it the row's full height for free.
// Driver shows the full name on sm+ and just the 3-letter code on mobile, so the column is
// narrow there. On sm+ driver and team split the slack (1.2fr/1fr) instead of team hoarding it.
const GRID = 'grid grid-cols-[6px_2.75rem_3.5rem_1fr_7.5rem_3.5rem_6.5rem] sm:grid-cols-[6px_3.5rem_1.2fr_1fr_8.5rem_4rem_7.5rem]'
const HEAD = 'border-b border-border px-2 pb-2 text-sm font-semibold text-ink'

// Cells touch (no grid gap) with matching horizontal padding instead, so a row's border-top
// reads as one continuous line rather than breaking across the column gutters.
//
// Team color: a low, capped-opacity wash across the whole row (not just the TeamRule tick),
// the same restrained recipe as the Ranking heatmap. Text stays ink/muted throughout, never
// the raw team hex — several team colors (Mercedes cyan, Williams/Racing Bulls light blue,
// Haas light gray) fail body-text contrast on this site's cream/espresso backgrounds, so the
// hue lives in the background wash where a low alpha can't break readability.
export function Results({ rows }: { rows: ResultRow[] }) {
  if (rows.length === 0) return <p className="text-sm text-muted">No results.</p>

  return (
    <div className="overflow-x-auto">
      <ol className={`${GRID} min-w-[440px] sm:min-w-[560px]`} aria-label="Finishing order">
        <li className="contents" aria-hidden>
          <span className={HEAD} />
          <span className={HEAD} />
          <span className={HEAD}>Driver</span>
          <span className={HEAD}>Team</span>
          <span className={HEAD}>Tyres</span>
          <span className={`${HEAD} text-right`}>Pts</span>
          <span className={`${HEAD} text-right`}>Time</span>
        </li>
        {rows.map((r, i) => {
          const b = i > 0 ? 'border-t border-border' : ''
          const cell = { backgroundColor: teamColorWithAlpha(r.constructor, 0.09) }
          return (
            <li key={`${r.position}-${r.driver}`} className="contents">
              {/* No border-t here: the bars stay contiguous down the table's left edge, and the
                  row separators read as belonging to the content columns. */}
              <span aria-hidden style={{ backgroundColor: resolveTeamColor(r.constructor) }} />
              <span className={`num px-2 py-3 text-sm text-muted ${b}`} style={cell}>{r.position ?? '–'}</span>
              <span className={`px-2 py-3 ${b}`} style={cell}>
                <span className="hidden font-display font-medium text-ink sm:block">{driverName(r.driver)}</span>
                <span className="block font-display text-sm font-medium text-ink sm:hidden">{r.driver}</span>
              </span>
              <span className={`px-2 py-3 text-sm text-ink ${b}`} style={cell}>{r.constructor}</span>
              <span className={`num px-2 py-3 text-sm tracking-wide text-ink ${b}`} style={cell}>{r.strategy}</span>
              <span className={`num px-2 py-3 text-right text-sm font-medium text-ink ${b}`} style={cell}>{r.points > 0 ? r.points : ''}</span>
              <span className={`num px-2 py-3 text-right text-sm text-ink ${b}`} style={cell}>{r.gap_label}</span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
