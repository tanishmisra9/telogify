import { TeamMark } from '@/components/TeamMark'
import { teamColorWithAlpha } from '@/lib/teamColors'

export interface TeamSelectRow {
  team: string
  value?: string
  // A row with no data for the current filter (e.g. a team that never ran the selected tyre
  // compound): rendered greyed, non-interactive, and unranked. Consumers that never have this
  // case (SeasonTrendChart, SeasonDeploymentChart) simply omit it.
  disabled?: boolean
  // Display text override: `team` still drives the color, `label` overrides what's shown
  // (e.g. SeasonDeploymentChart's power-unit toggle: color from the works team, label from
  // the manufacturer name).
  label?: string
}

const COL_SIZE = 5

function Row({
  row,
  rank,
  selected,
  isFiltering,
  onToggle,
}: {
  row: TeamSelectRow
  // Absolute 1-based rank across the whole (pre-split) list, not the position within whichever
  // column/row this renders in -- so the split into columns below doesn't restart the numbering.
  rank: number
  selected: Set<string>
  isFiltering: boolean
  onToggle: (team: string) => void
}) {
  if (row.disabled) {
    return (
      <li>
        <div className="grid min-h-11 w-full grid-cols-[1.25rem_minmax(0,1fr)_auto] items-center gap-x-3 px-2 py-1 text-sm opacity-40">
          <span aria-hidden />
          <TeamMark team={row.team} label={row.label} className="font-medium" />
          {row.value && <span className="num text-xs text-muted">{row.value}</span>}
        </div>
      </li>
    )
  }
  const isSelected = selected.has(row.team)
  const isDimmed = isFiltering && !isSelected
  return (
    <li>
      <button
        type="button"
        onClick={() => onToggle(row.team)}
        aria-pressed={isSelected}
        aria-label={isSelected ? 'Show every team again' : `Isolate ${row.label ?? row.team}'s line`}
        className={`grid min-h-11 w-full cursor-pointer grid-cols-[1.25rem_minmax(0,1fr)_auto] items-center gap-x-3 px-2 py-1 text-left text-sm shadow-[inset_0_0_0_1.5px_transparent] transition-[opacity,box-shadow] duration-150 hover:shadow-[inset_0_0_0_1.5px_var(--color-ink)] ${
          isDimmed ? 'opacity-40' : ''
        }`}
        style={{ backgroundColor: teamColorWithAlpha(row.team, isSelected ? 0.2 : 0.09) }}
      >
        <span className="num text-xs text-muted">{rank}</span>
        <TeamMark team={row.team} label={row.label} className={isSelected ? 'font-semibold' : 'font-medium'} />
        {row.value && <span className="num text-xs text-ink">{row.value}</span>}
      </button>
    </li>
  )
}

// Click-to-isolate chart legend, shared by every chart that lets you click a team to isolate
// its line/series (Tyre degradation, Gap by round): clicking toggles that team into `selected`;
// the chart filters to just the selected teams (or everyone, when nothing's selected).
//
// Explicit two-column split (ranks 1-5, then 6-10), not native CSS multi-column: multi-column's
// auto-balance gives an uneven split (e.g. 6/5) with no control over it, and can't express "any
// remainder gets its own centered row" at all. Columns fill top-to-bottom (rank 1-5 reads straight
// down column 1, not zigzagging row-major across both), which is both the correct reading order
// and the compact, space-efficient shape a single top-down list can't give an 11-team field.
// Fixed at 2 columns of 5 (not width-driven): a min-width-per-column rule collapsed to one column
// -- and a lot of empty space beside it -- on anything narrower than ~30rem, which is most phones.
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
  const col1 = rows.slice(0, COL_SIZE)
  const col2 = rows.slice(COL_SIZE, COL_SIZE * 2)
  const rest = rows.slice(COL_SIZE * 2)

  return (
    <div>
      <div className="grid grid-cols-2 gap-x-4">
        <ol>
          {col1.map((r, i) => (
            <Row key={r.team} row={r} rank={i + 1} selected={selected} isFiltering={isFiltering} onToggle={onToggle} />
          ))}
        </ol>
        <ol>
          {col2.map((r, i) => (
            <Row key={r.team} row={r} rank={i + 1 + COL_SIZE} selected={selected} isFiltering={isFiltering} onToggle={onToggle} />
          ))}
        </ol>
      </div>
      {rest.length > 0 && (
        <ol className="mx-auto mt-0 w-1/2 min-w-[12rem]">
          {rest.map((r, i) => (
            <Row
              key={r.team}
              row={r}
              rank={i + 1 + COL_SIZE * 2}
              selected={selected}
              isFiltering={isFiltering}
              onToggle={onToggle}
            />
          ))}
        </ol>
      )}
    </div>
  )
}
