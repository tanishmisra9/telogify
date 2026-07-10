import { useState } from 'react'
import { m, useReducedMotion } from 'framer-motion'
import { TeamMark } from '@/components/TeamMark'
import { Tooltip } from '@/components/Tooltip'
import { resolveTeamColor, teamColorWithAlpha } from '@/lib/teamColors'
import { spring } from '@/lib/motion'
import type { DegradationData } from '@/lib/api'

const WIDTH = 1100
const HEIGHT = 420
const MARGIN = { top: 16, right: 24, bottom: 52, left: 56 }
const INNER_W = WIDTH - MARGIN.left - MARGIN.right
const INNER_H = HEIGHT - MARGIN.top - MARGIN.bottom

export function DegradationChart({ data }: { data: DegradationData }) {
  const reduce = useReducedMotion()
  const compounds = Array.from(new Set(data.fits.map((f) => f.compound))).sort()
  const [compound, setCompound] = useState<string | null>(compounds[0] ?? null)

  if (!compound) {
    return <p className="text-sm text-muted">No race tyre data yet.</p>
  }

  const fits = data.fits.filter((f) => f.compound === compound)
  const points = data.points.filter((p) => p.compound === compound)

  const ages = points.map((p) => p.tyre_age)
  const times = points.map((p) => p.lap_time_s)
  const xMax = Math.max(1, ...ages)
  const yLo = Math.min(...times)
  const yHi = Math.max(...times)
  const yPad = (yHi - yLo) * 0.08 || 0.5
  const yMin = yLo - yPad
  const yMax = yHi + yPad

  const x = (v: number) => (v / xMax) * INNER_W
  const y = (v: number) => INNER_H * (1 - (v - yMin) / (yMax - yMin))

  const ageRangeByConstructor: Record<string, [number, number]> = {}
  for (const p of points) {
    const cur = ageRangeByConstructor[p.constructor]
    ageRangeByConstructor[p.constructor] = cur
      ? [Math.min(cur[0], p.tyre_age), Math.max(cur[1], p.tyre_age)]
      : [p.tyre_age, p.tyre_age]
  }

  // Ranked worst-wear-first (steepest slope first) so the chart's most-flagged line and the
  // list's top row are the same story read two ways, not two columns whose order is ambiguous.
  const rankedFits = [...fits].sort((a, b) => b.slope_s_per_lap - a.slope_s_per_lap)
  const yTicks = Array.from({ length: 5 }, (_, i) => yMin + ((yMax - yMin) * i) / 4)
  const xTickCount = Math.min(6, xMax + 1)
  const xTicks = Array.from({ length: xTickCount }, (_, i) => Math.round((xMax * i) / (xTickCount - 1 || 1)))

  return (
    <m.div
      className="glass w-full rounded-[--radius-panel] p-5"
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={spring}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-[2.025rem] font-semibold tracking-tight sm:text-[2.7rem]">Tyre degradation</h2>
        <div className="inline-flex rounded-full border border-border bg-surface/60 p-0.5" role="group" aria-label="Compound">
          {compounds.map((c) => (
            <Tooltip key={c} label={`${c.toLowerCase()} tyre degradation`}>
              <button
                type="button"
                onClick={() => setCompound(c)}
                aria-label={`Show ${c.toLowerCase()} tyre degradation`}
                aria-pressed={compound === c}
                className={`rounded-full px-3 py-1 text-sm transition-colors ${
                  compound === c ? 'bg-accent/15 text-accent' : 'text-muted hover:text-ink'
                }`}
              >
                {c}
              </button>
            </Tooltip>
          ))}
        </div>
      </div>

      {points.length === 0 ? (
        <p className="text-sm text-muted">No {compound.toLowerCase()} laps this race.</p>
      ) : (
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full max-w-full" role="img" aria-label="Fuel-corrected lap time vs tyre age">
          <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
            {yTicks.map((t) => (
              <g key={t}>
                <line x1={0} x2={INNER_W} y1={y(t)} y2={y(t)} stroke="var(--color-border)" strokeDasharray="4 4" />
                <text x={-9} y={y(t)} textAnchor="end" dominantBaseline="middle" fill="var(--color-muted)" fontSize={13}>
                  {t.toFixed(1)}s
                </text>
              </g>
            ))}
            {xTicks.map((t) => (
              <text key={t} x={x(t)} y={INNER_H + 22} textAnchor="middle" fill="var(--color-muted)" fontSize={12}>
                {t}
              </text>
            ))}
            <text x={INNER_W / 2} y={INNER_H + 42} textAnchor="middle" fill="var(--color-muted)" fontSize={12}>
              Tyre age (laps)
            </text>

            {/* Raw laps sit as a faint texture; the labeled fit line is the actual finding. */}
            {points.map((p, i) => (
              <circle key={i} cx={x(p.tyre_age)} cy={y(p.lap_time_s)} r={1.5} fill={teamColorWithAlpha(p.constructor, 0.16)} />
            ))}

            {fits.map((f) => {
              const range = ageRangeByConstructor[f.constructor]
              if (!range) return null
              const [lo, hi] = range
              const stroke = resolveTeamColor(f.constructor)
              return (
                <line
                  key={f.constructor}
                  x1={x(lo)}
                  y1={y(f.slope_s_per_lap * lo + f.intercept_s)}
                  x2={x(hi)}
                  y2={y(f.slope_s_per_lap * hi + f.intercept_s)}
                  stroke={stroke}
                  strokeWidth={f.flagged ? 3.5 : 2}
                />
              )
            })}
          </g>
        </svg>
      )}

      {/* Compact ranked block, worst wear first, in the same kicker-labeled grammar as the
          Car character panel's sector dominance. The reference-lap context is stated once in
          the label instead of being repeated in every row. */}
      <div className="mt-6 border-t border-border pt-5">
        <p className="kicker text-muted">
          Wear rate, worst first
          {data.reference_age_laps != null && ` · cost over ${data.reference_age_laps} laps`}
        </p>
        <ol className="mt-3 grid gap-x-10 gap-y-2 sm:grid-cols-2 xl:grid-cols-3">
          {rankedFits.map((f, i) => (
            <li key={f.constructor} className="grid grid-cols-[1.25rem_minmax(0,1fr)_auto_auto] items-center gap-x-3 text-sm">
              <span className="num text-xs text-muted">{i + 1}</span>
              <TeamMark team={f.constructor} className="font-medium" />
              <span className="num text-xs text-ink">
                {f.slope_s_per_lap >= 0 ? '+' : ''}
                {f.slope_s_per_lap.toFixed(3)}s/lap
              </span>
              {data.reference_age_laps != null ? (
                <span className="num text-xs text-muted">
                  {f.cost_at_reference_s >= 0 ? '+' : ''}
                  {f.cost_at_reference_s.toFixed(2)}s
                </span>
              ) : (
                <span />
              )}
            </li>
          ))}
        </ol>
      </div>
      <p className="mt-4 text-xs text-muted">
        Fuel-corrected lap time against tyre age. The slope is the wear rate; a bold line marks
        wear well above the field on that compound.
      </p>
    </m.div>
  )
}
