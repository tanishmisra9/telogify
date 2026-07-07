import { TeamRule } from '@/components/TeamMark'
import type { ResultRow } from '@/lib/api'

const GRID = 'grid grid-cols-[2rem_4.5rem_1fr_6.5rem_2.5rem_6rem] items-center gap-x-4'
const HEAD = 'border-b border-border pb-2 text-sm font-semibold text-ink'

export function Results({ rows }: { rows: ResultRow[] }) {
  if (rows.length === 0) return <p className="text-sm text-muted">No results.</p>

  return (
    <ol className={GRID} aria-label="Finishing order">
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
            <span className={`num py-3 text-sm text-muted ${b}`}>{r.position ?? '–'}</span>
            <span className={`flex items-center gap-2 py-3 font-medium text-ink ${b}`}>
              <TeamRule team={r.constructor} />
              {r.driver}
            </span>
            <span className={`py-3 text-sm text-ink ${b}`}>{r.constructor}</span>
            <span className={`num py-3 text-sm tracking-wide text-ink ${b}`}>{r.strategy}</span>
            <span className={`num py-3 text-right text-sm font-medium text-ink ${b}`}>{r.points > 0 ? r.points : ''}</span>
            <span className={`num py-3 text-right text-sm text-ink ${b}`}>{r.gap_label}</span>
          </li>
        )
      })}
    </ol>
  )
}
