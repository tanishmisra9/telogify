import { TeamRule } from '@/components/TeamMark'
import type { ResultRow } from '@/lib/api'

const GRID = 'grid grid-cols-[3rem_5.5rem_1fr_7.5rem_3.5rem_7rem] items-center'
const HEAD = 'border-b border-border px-2 pb-2 text-sm font-semibold text-ink'

// Cells touch (no grid gap) with matching horizontal padding instead, so a row's border-top
// reads as one continuous line rather than breaking across the column gutters.
export function Results({ rows }: { rows: ResultRow[] }) {
  if (rows.length === 0) return <p className="text-sm text-muted">No results.</p>

  return (
    <div className="overflow-x-auto">
      <ol className={`${GRID} min-w-[480px]`} aria-label="Finishing order">
        <li className="contents" aria-hidden>
          <span className={HEAD} />
          <span className={HEAD}>Driver</span>
          <span className={HEAD}>Team</span>
          <span className={HEAD}>Tyres</span>
          <span className={`${HEAD} text-right`}>Pts</span>
          <span className={`${HEAD} text-right`}>Time</span>
        </li>
        {rows.map((r, i) => {
          const b = i > 0 ? 'border-t border-border' : ''
          return (
            <li key={`${r.position}-${r.driver}`} className="contents">
              <span className={`num px-2 py-3 text-sm text-muted ${b}`}>{r.position ?? '–'}</span>
              <span className={`flex items-center gap-2 px-2 py-3 font-medium text-ink ${b}`}>
                <TeamRule team={r.constructor} />
                {r.driver}
              </span>
              <span className={`px-2 py-3 text-sm text-ink ${b}`}>{r.constructor}</span>
              <span className={`num px-2 py-3 text-sm tracking-wide text-ink ${b}`}>{r.strategy}</span>
              <span className={`num px-2 py-3 text-right text-sm font-medium text-ink ${b}`}>{r.points > 0 ? r.points : ''}</span>
              <span className={`num px-2 py-3 text-right text-sm text-ink ${b}`}>{r.gap_label}</span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
