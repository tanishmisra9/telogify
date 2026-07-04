import { useState } from 'react'
import { m, useReducedMotion } from 'framer-motion'
import { resolveTeamColor, teamCode } from '@/lib/teamColors'
import { spring } from '@/lib/motion'
import type { SeasonConstructorRow, SeasonRound } from '@/lib/api'

const WIDTH = 1100
const HEIGHT = 440
const MARGIN = { top: 16, right: 16, bottom: 52, left: 56 }
const INNER_W = WIDTH - MARGIN.left - MARGIN.right
const INNER_H = HEIGHT - MARGIN.top - MARGIN.bottom

type Metric = 'pace' | 'quali' | 'cumulative'
const METRIC_LABEL: Record<Metric, string> = { pace: 'Race pace', quali: 'Qualifying', cumulative: 'Cumulative' }
const UNIT: Record<Metric, (v: number) => string> = {
  pace: (v) => `+${v.toFixed(1)}s`,
  quali: (v) => `${(100 + v).toFixed(1)}%`,
  cumulative: (v) => v.toFixed(2),
}

// One line per constructor: gap to the round's fastest team, round by round. Lower is
// better and the y-axis is inverted (0 at top), so a line hugging the top is a season-long
// front-runner and a line dropping away is a team losing ground. Copies DegradationChart's scaffold.
export function SeasonTrendChart({ rows, rounds }: { rows: SeasonConstructorRow[]; rounds: SeasonRound[] }) {
  const reduce = useReducedMotion()
  const [metric, setMetric] = useState<Metric>('pace')

  const series = rows
    .map((r) => ({ team: r.constructor, points: r.trend[metric] }))
    .filter((s) => s.points.length > 0)

  const roundNums = rounds.map((r) => r.round)
  const xMin = Math.min(...roundNums)
  const xMax = Math.max(...roundNums)
  const values = series.flatMap((s) => s.points.map((p) => p.value))

  if (series.length === 0 || values.length === 0) {
    return <p className="text-sm text-muted">No trend data yet.</p>
  }

  const yMax = Math.max(...values) * 1.05 || 1
  const x = (v: number) => (xMax === xMin ? INNER_W / 2 : ((v - xMin) / (xMax - xMin)) * INNER_W)
  const y = (v: number) => INNER_H * (v / yMax) // 0 at the top (fastest team on top)

  const yTicks = Array.from({ length: 5 }, (_, i) => (yMax * i) / 4)

  return (
    <m.div
      className="glass w-full rounded-[--radius-panel] p-5"
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={spring}
    >
      <div className="mb-4 flex flex-wrap items-center justify-end gap-3">
        <div className="inline-flex rounded-full border border-border bg-surface/60 p-0.5" role="group" aria-label="Metric">
          {(['pace', 'quali', 'cumulative'] as Metric[]).map((mkey) => (
            <button
              key={mkey}
              type="button"
              onClick={() => setMetric(mkey)}
              className={`rounded-full px-3 py-1 text-sm transition-colors ${
                metric === mkey ? 'bg-accent/15 text-accent' : 'text-muted hover:text-ink'
              }`}
            >
              {METRIC_LABEL[mkey]}
            </button>
          ))}
        </div>
      </div>

      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full max-w-full" role="img" aria-label={`${METRIC_LABEL[metric]} gap by round`}>
        <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
          {yTicks.map((t) => (
            <g key={t}>
              <line x1={0} x2={INNER_W} y1={y(t)} y2={y(t)} stroke="var(--color-border)" strokeDasharray="4 4" />
              <text x={-9} y={y(t)} textAnchor="end" dominantBaseline="middle" fill="var(--color-muted)" fontSize={13}>
                {UNIT[metric](t)}
              </text>
            </g>
          ))}
          {roundNums.map((r) => (
            <text key={r} x={x(r)} y={INNER_H + 22} textAnchor="middle" fill="var(--color-muted)" fontSize={12}>
              {r}
            </text>
          ))}
          <text x={INNER_W / 2} y={INNER_H + 42} textAnchor="middle" fill="var(--color-muted)" fontSize={12}>
            Round
          </text>

          {series.map((s) => {
            const color = resolveTeamColor(s.team)
            const pts = [...s.points].sort((a, b) => a.round - b.round)
            return (
              <g key={s.team}>
                <polyline
                  points={pts.map((p) => `${x(p.round)},${y(p.value)}`).join(' ')}
                  fill="none"
                  stroke={color}
                  strokeWidth={2}
                />
                {pts.map((p) => (
                  <circle key={p.round} cx={x(p.round)} cy={y(p.value)} r={2} fill={color} />
                ))}
              </g>
            )
          })}
        </g>
      </svg>

      <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5">
        {series.map((s) => (
          <span key={s.team} className="inline-flex items-center gap-1.5 text-xs text-muted">
            <span aria-hidden className="h-[3px] w-4 rounded-[2px]" style={{ backgroundColor: resolveTeamColor(s.team) }} />
            {teamCode(s.team)}
          </span>
        ))}
      </div>
      <p className="mt-3 text-xs text-muted">
        Gap to each round's fastest team, round by round. Lower is better, so a line near the
        top ran at the front all season and a line dropping away lost ground as the season went on.
      </p>
    </m.div>
  )
}
