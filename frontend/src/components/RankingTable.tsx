import { m, useReducedMotion } from 'framer-motion'
import { Tooltip } from '@/components/Tooltip'
import { TeamRule } from '@/components/TeamMark'
import { axisTicks, barFractions, gapCells } from '@/lib/gapLadder'
import { formArrow, formMoveSentence } from '@/lib/seasonStart'
import { resolveTeamColor, teamColorWithAlpha, teamShortName } from '@/lib/teamColors'

export interface RankingRow {
  key: string
  // Team whose colour marks the row (a power unit passes its works team).
  colorTeam: string
  label: string
  rank: number | null
  // Lower is better; null = no data (renders the rule with no bar). Every bar is its gap to the best row.
  gap: number | null
  // REQUIRED on purpose (null = too few rounds to say): every ranking on the Trends page shows form
  // movement, so a new table can't be built without deciding what its arrow is. See CLAUDE.md "Trends standard".
  formPlaces: number | null
  confidence?: 'low' | 'med' | 'high'
}

const CONF_LABEL: Record<string, string> = { low: 'low data', med: 'partial data' }

function ConfidenceChip({ confidence }: { confidence: string }) {
  if (confidence === 'high') return null
  return (
    <span className="whitespace-nowrap rounded-panel border border-border px-2 py-0.5 text-xs text-muted">
      {CONF_LABEL[confidence] ?? confidence}
    </span>
  )
}

// Fixed column widths shared by the header and every row so the axis ticks land directly above
// the bars they describe, and a bar always starts at the same x regardless of name length. One row shape
// at every width; only the widths shrink (the name truncates rather than wrapping).
const RANK_W = 'w-6 sm:w-9'
const TEAM_W = 'w-24 sm:w-44'
const FIGURE_W = 'w-16 sm:w-32'

// One ranked list: rank, name, a bar for the gap to the best, the figure, and the form arrow (places gained or
// lost on recent form versus the whole season). Shared by Pace ranking, Race start ranking and Deployment ranking.
export function RankingTable({
  rows,
  fmtGap,
  ticks: ticksProp,
  tickLabel,
  nameHeader = 'Team',
}: {
  rows: RankingRow[]
  fmtGap: (d: number) => string
  // Header axis ticks (in the gap's own unit); default whole units from 0.
  ticks?: number[]
  tickLabel: (t: number) => string
  nameHeader?: string
}) {
  const reduce = useReducedMotion()
  const values = rows.map((r) => r.gap)
  const present = values.filter((v): v is number => v != null)
  const maxGap = present.length > 0 ? Math.max(...present) - Math.min(...present) : 0
  const ticks = ticksProp ?? axisTicks(maxGap)
  const cells = gapCells(values, fmtGap)
  const fractions = barFractions(values)

  return (
    <div>
      {/* Header mirrors each row's columns so its axis ticks sit directly above the bars. Desktop only:
          "Team" doesn't fit the mobile widths, and the per-row figure already carries the exact number. */}
      <div className="hidden items-center gap-3 border-b border-border pb-2 sm:flex">
        <span className={`${RANK_W} shrink-0`} aria-hidden />
        <span className={`${TEAM_W} shrink-0 text-lg font-semibold text-ink`}>{nameHeader}</span>
        <span className="relative h-4 flex-1">
          {/* Ticks share the bars' domain [0, maxGap] (a bar is gap / maxGap of the track). They once scaled to the
              last whole tick instead, so "+3s" sat right of where a 3 s bar actually ends. */}
          {ticks.map((t, i) => {
            const frac = maxGap > 0 ? Math.min(1, t / maxGap) : 0
            return (
              <span
                key={t}
                className="absolute top-0 whitespace-nowrap text-xs text-muted"
                style={{
                  left: `${frac * 100}%`,
                  transform: i === 0 ? 'translateX(0)' : frac > 0.92 ? 'translateX(-100%)' : 'translateX(-50%)',
                }}
              >
                {tickLabel(t)}
              </span>
            )
          })}
        </span>
        <span className={`${FIGURE_W} shrink-0`} aria-hidden />
      </div>

      <ol>
        {rows.map((r, i) => {
          const fraction = fractions[i]
          const cell = cells[i]
          const figure =
            cell == null ? '–' : cell === 'best' ? <span className="font-sans font-semibold text-ink">leader</span> : cell
          const arrow = formArrow(r.formPlaces)
          const hint = formMoveSentence(r.formPlaces)
          const arrowEl = arrow && (
            <span
              className={`text-xs ${r.formPlaces != null && r.formPlaces > 0 ? 'text-ink' : 'text-muted'}`}
              aria-label={hint ?? undefined}
            >
              {arrow}
            </span>
          )

          // Mobile uses the short team names ("Red Bull Racing" -> "Red Bull"); a real name that fits
          // beats a clipped one. The confidence chip only fits on wider rows.
          const name = (
            <span className="flex min-w-0 items-center gap-2">
              <TeamRule team={r.colorTeam} />
              <span className="truncate font-medium text-ink">
                <span className="hidden sm:inline">{r.label}</span>
                <span className="sm:hidden">{r.label.length > 13 ? teamShortName(r.label) : r.label}</span>
              </span>
              {r.confidence && (
                <span className="hidden shrink-0 sm:inline-flex">
                  <ConfidenceChip confidence={r.confidence} />
                </span>
              )}
            </span>
          )

          // The zero rule marks every row's baseline (the best) as one continuous line. A row with no data
          // (fraction null) shows the rule with no fill, not a zero-length bar that would read as tied for
          // best. The leader's own row has no bar, so its rule is thickened and team-coloured instead.
          const isLeaderRow = fraction === 0
          const track = (
            <span
              className="relative h-[1.375rem] flex-1 border-l-[1.5px] border-ink/25"
              style={isLeaderRow ? { borderLeftWidth: '2px', borderLeftColor: resolveTeamColor(r.colorTeam) } : undefined}
            >
              {fraction != null && (
                <m.span
                  className={`absolute inset-y-0 left-0 block rounded-r-[1px] ${fraction > 0 ? 'min-w-[3px]' : ''}`}
                  style={{
                    width: `${fraction * 100}%`,
                    backgroundColor: teamColorWithAlpha(r.colorTeam, 0.55),
                    transformOrigin: 'left',
                  }}
                  initial={reduce ? false : { scaleX: 0 }}
                  animate={{ scaleX: 1 }}
                  transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: reduce ? 0 : i * 0.03 }}
                />
              )}
            </span>
          )

          return (
            <li key={r.key} className={`flex items-center gap-2 py-3 sm:gap-3 ${i > 0 ? 'border-t border-border' : ''}`}>
              <span className={`num ${RANK_W} shrink-0 text-sm text-muted`}>{r.rank ?? '–'}</span>
              <span className={`${TEAM_W} shrink-0`}>{name}</span>
              {track}
              {/* Figure and arrow share one cell: stacked on a phone (no fifth column to squeeze), side by side from sm. */}
              <span className={`num ${FIGURE_W} flex shrink-0 flex-col items-end text-sm text-ink sm:flex-row sm:justify-end sm:gap-2`}>
                <span>{figure}</span>
                {arrowEl && hint ? (
                  <Tooltip label={hint} align="end" wrap>
                    <span tabIndex={0} className="cursor-default">
                      {arrowEl}
                    </span>
                  </Tooltip>
                ) : (
                  arrowEl
                )}
              </span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
