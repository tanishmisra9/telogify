import { resolveTeamColor, teamColorWithAlpha } from '@/lib/teamColors'

export interface BarChartRow {
  id: string
  label: string
  value: number
  /** Shown above the bar instead of `value` when set (e.g. an absolute time while `value`
   * drives bar height as a gap-to-fastest). */
  displayValue?: number
  team?: string | null
}

const MARGIN = { top: 26, right: 12, bottom: 34, left: 12 }
const WIDTH = 1200
const HEIGHT = 260
const INNER_W = WIDTH - MARGIN.left - MARGIN.right
const INNER_H = HEIGHT - MARGIN.top - MARGIN.bottom

/** Shared vertical bar chart: one bar per row, team-colored, value labeled above the
 * bar, row label below. Used for practice best sectors and top speeds. */
export function BarChart({
  rows,
  formatValue = (v) => v.toFixed(3),
  domainMin = 0,
}: {
  rows: BarChartRow[]
  formatValue?: (v: number, row: BarChartRow) => string
  domainMin?: number
}) {
  if (rows.length === 0) return null

  const lo = Math.min(domainMin, ...rows.map((r) => r.value))
  const hi = Math.max(...rows.map((r) => r.value)) || 1
  const span = hi - lo || 1
  const y = (v: number) => INNER_H * (1 - (v - lo) / span)

  const step = INNER_W / rows.length
  const bw = Math.min(30, step * 0.6)
  const center = (i: number) => step * i + step / 2
  const baseline = y(lo)
  // A wide field (e.g. a ~20-driver practice session) doesn't leave enough horizontal room for
  // centered value labels without them overlapping their neighbours; angle them instead.
  const dense = rows.length > 10

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" role="img" aria-label="Bar chart">
      <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
        <line x1={0} x2={INNER_W} y1={baseline} y2={baseline} stroke="var(--color-border)" />
        {rows.map((r, i) => {
          const cx = center(i)
          const top = y(r.value)
          const stroke = resolveTeamColor(r.team ?? null)
          const fill = teamColorWithAlpha(r.team ?? null, 0.55)
          return (
            <g key={r.id}>
              <rect
                x={cx - bw / 2}
                y={top}
                width={bw}
                height={Math.max(1.5, baseline - top)}
                fill={fill}
                stroke={stroke}
                strokeWidth={1}
                rx={2}
              />
              <text
                x={cx}
                y={top - 6}
                textAnchor={dense ? 'start' : 'middle'}
                transform={dense ? `rotate(-60 ${cx} ${top - 6})` : undefined}
                fill="var(--color-ink)"
                fontSize={dense ? 11 : 13}
                fontWeight={600}
                className="num"
              >
                {formatValue(r.displayValue ?? r.value, r)}
              </text>
              <text x={cx} y={INNER_H + 21} textAnchor="middle" fill="var(--color-ink)" fontSize={13.5} fontWeight={600}>
                {r.label}
              </text>
            </g>
          )
        })}
      </g>
    </svg>
  )
}
