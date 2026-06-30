import { teamLogo } from '@/lib/assets'
import type { ResultRow } from '@/lib/api'

function gapLabel(r: ResultRow): string {
  if (r.position === 1) return 'leader'
  if (r.gap_to_leader != null) return `+${r.gap_to_leader.toFixed(1)}s`
  return r.status ?? ''
}

export function Results({ rows }: { rows: ResultRow[] }) {
  if (rows.length === 0) return <p className="text-sm text-muted">No results.</p>
  return (
    <ol className="divide-y divide-border">
      {rows.map((r) => {
        const logo = teamLogo(r.constructor)
        return (
          <li key={`${r.position}-${r.driver}`} className="flex items-center gap-4 py-3">
            <span className="num w-7 text-sm text-muted">{r.position ?? '–'}</span>
            <span className="flex-1 font-medium">{r.driver}</span>
            <span className="flex flex-1 items-center gap-2 text-sm text-muted">
              {logo && (
                <img
                  src={logo}
                  alt=""
                  className="h-5 w-5 shrink-0 object-contain"
                  onError={(e) => (e.currentTarget.style.display = 'none')}
                />
              )}
              {r.constructor}
            </span>
            <span className="num text-sm text-muted">{gapLabel(r)}</span>
          </li>
        )
      })}
    </ol>
  )
}
