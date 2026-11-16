import { useState } from 'react'
import { ChartTabs } from '@/components/ChartTabs'
import { driverName } from '@/lib/drivers'
import { canSwitchGap, gapText, type GapTo } from '@/lib/finishing'
import { teamColorWithAlpha } from '@/lib/teamColors'
import type { ResultRow } from '@/lib/api'

// No items-center: a cell with genuinely empty content (no points scored) would then get a
// shorter box than its text-bearing row-mates, leaving a gap in the team-color wash. Default
// stretch fills every cell to the row's full height instead; the shared py-3 padding already
// centers content visually.
// Driver shows the full name on sm+ and just the 3-letter code on mobile, so the column is
// narrow there. On sm+ driver and team split the slack (1.2fr/1fr) instead of team hoarding it.
const GRID = 'grid grid-cols-[2.75rem_3.5rem_1fr_7.5rem_4.5rem_6.5rem] sm:grid-cols-[3.5rem_1.2fr_1fr_8.5rem_6rem_7.5rem]'
const HEAD = 'border-b border-border px-2 pb-2 text-sm font-semibold text-ink'

// Cells touch (no grid gap) with matching horizontal padding instead, so a row's border-top
// reads as one continuous line rather than breaking across the column gutters.
//
// Team color: a low, capped-opacity wash across the whole row, the same restrained recipe as
// the Ranking heatmap. Text stays ink/muted throughout, never the raw team hex — several team
// colors (Mercedes cyan, Williams/Racing Bulls light blue, Haas light gray) fail body-text
// contrast on this site's cream/espresso backgrounds, so the hue lives in the background wash
// where a low alpha can't break readability.
export function Results({ rows }: { rows: ResultRow[] }) {
  const [gapTo, setGapTo] = useState<GapTo>('leader')
  if (rows.length === 0) return <p className="text-sm text-muted">No results.</p>
  const switchable = canSwitchGap(rows)

  return (
    <div>
      {switchable && (
        // Same labelled-switcher shape as the Race start chart's control bar.
        <div className="mb-5 flex flex-col gap-1.5 sm:flex-row sm:items-baseline sm:gap-7">
          <span className="shrink-0 whitespace-nowrap font-display text-sm font-medium tracking-tight text-muted sm:w-[4.25rem] sm:text-base">Gap to</span>
          <ChartTabs
            ariaLabel="Gap to the leader or to the car ahead"
            active={gapTo}
            onChange={setGapTo}
            tabs={[
              { value: 'leader', label: 'Leader', hint: 'Seconds behind the winner' },
              { value: 'ahead', label: 'Car ahead', hint: 'Seconds behind the car directly in front' },
            ]}
          />
        </div>
      )}
    <div className="overflow-x-auto">
      <ol className={`${GRID} min-w-[450px] sm:min-w-[586px]`} aria-label="Finishing order">
        <li className="contents" aria-hidden>
          <span className={HEAD} />
          <span className={HEAD} />
          <span className={HEAD} />
          <span className={`${HEAD} text-center`}>Tyres</span>
          <span className={`${HEAD} text-center`}>Pts</span>
          <span className={`${HEAD} text-center`}>Time</span>
        </li>
        {rows.map((r, i) => {
          // Strategy comes back empty when there is no tyre data to show (every stint unknown, or
          // no stints at all, e.g. a DNS); grey the row out so the blank Tyres cell reads as
          // missing, not as a bug.
          const b = `${i > 0 ? 'border-t border-border' : ''}${r.strategy === '' ? ' opacity-50' : ''}`
          const cell = { backgroundColor: teamColorWithAlpha(r.constructor, 0.09) }
          return (
            <li key={`${r.position}-${r.driver}`} className="contents">
              <span className={`num px-2 py-3 text-sm text-muted ${b}`} style={cell}>{r.position ?? '–'}</span>
              <span className={`px-2 py-3 ${b}`} style={cell}>
                <span className="hidden font-display font-medium text-ink sm:block">{driverName(r.driver)}</span>
                <span className="block font-display text-sm font-medium text-ink sm:hidden">{r.driver}</span>
              </span>
              <span className={`px-2 py-3 text-sm text-ink ${b}`} style={cell}>{r.constructor}</span>
              <span className={`num px-2 py-3 text-center text-sm tracking-wide text-ink ${b}`} style={cell}>{r.strategy}</span>
              <span className={`num px-2 py-3 text-center text-sm font-medium text-ink ${b}`} style={cell}>{r.points > 0 ? r.points : ''}</span>
              <span className={`num px-2 py-3 text-center text-sm text-ink ${b}`} style={cell}>{gapText(r, gapTo)}</span>
            </li>
          )
        })}
      </ol>
    </div>
    </div>
  )
}
