import { TeamMark } from '@/components/TeamMark'
import { teamColorWithAlpha } from '@/lib/teamColors'

export interface TeamSelectRow {
  team: string
  value?: string
}

// Click-to-isolate chart legend, shared by every chart that lets you click a team to isolate
// its line/series (Tyre degradation, Gap by round): clicking toggles that team into `selected`;
// the chart filters to just the selected teams (or everyone, when nothing's selected).
//
// Native CSS multi-column, not a grid: a grid with sm:grid-cols-2/xl:grid-cols-3 fills row-major
// (rank 1, 2, 3 across the top, then 4, 5, 6), so the eye zigzags instead of reading straight
// down the ranking. Columns fill top-to-bottom automatically, which is both the correct reading
// order and the compact, space-efficient shape a single top-down list can't give an 11-team
// field. Fixed at 2 columns (not width-driven): a min-width-per-column rule collapsed to one
// column -- and a lot of empty space beside it -- on anything narrower than ~30rem, which is
// most phones. TeamMark already truncates a name that doesn't fit a narrower column.
export function TeamSelectLegend({
  rows,
  selected,
  onToggle,
  isFiltering,
}: {
  rows: TeamSelectRow[]
  selected: Set<string>
  onToggle: (team: string) => void
  isFiltering: boolean
}) {
  return (
    <ol className="[column-count:2] gap-x-6">
      {rows.map((r, i) => {
        const isSelected = selected.has(r.team)
        const isDimmed = isFiltering && !isSelected
        return (
          <li key={r.team}>
            <button
              type="button"
              onClick={() => onToggle(r.team)}
              aria-pressed={isSelected}
              aria-label={isSelected ? 'Show every team again' : `Isolate ${r.team}'s line`}
              className={`grid min-h-11 w-full cursor-pointer [break-inside:avoid] grid-cols-[1.25rem_minmax(0,1fr)_auto] items-center gap-x-3 px-2 py-1 text-left text-sm shadow-[inset_0_0_0_1.5px_transparent] transition-[opacity,box-shadow] duration-150 hover:shadow-[inset_0_0_0_1.5px_var(--color-ink)] ${
                isDimmed ? 'opacity-40' : ''
              }`}
              style={{ backgroundColor: teamColorWithAlpha(r.team, isSelected ? 0.2 : 0.09) }}
            >
              <span className="num text-xs text-muted">{i + 1}</span>
              <TeamMark team={r.team} className={isSelected ? 'font-semibold' : 'font-medium'} />
              {r.value && <span className="num text-xs text-ink">{r.value}</span>}
            </button>
          </li>
        )
      })}
    </ol>
  )
}
