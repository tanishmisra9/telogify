import { useState } from 'react'
import { AnimatePresence, m, useReducedMotion } from 'framer-motion'
import { TeamSelectLegend } from '@/components/TeamSelectLegend'
import { Tooltip } from '@/components/Tooltip'
import { resolveTeamColor, teamColorWithAlpha } from '@/lib/teamColors'
import { drawTransition, morphTransition, spring } from '@/lib/motion'
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
  // Empty = show every team (today's default). Not reset on compound switch,
  // so a comparison survives moving between Hard/Medium/Soft.
  const [selected, setSelected] = useState<Set<string>>(new Set())

  if (!compound) {
    return <p className="text-sm text-muted">No race tyre data yet.</p>
  }

  const toggleTeam = (team: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(team)) next.delete(team)
      else next.add(team)
      return next
    })

  const fits = data.fits.filter((f) => f.compound === compound)
  const points = data.points.filter((p) => p.compound === compound)
  // Selection persists across compound tabs, but a team's selection can be meaningless for a
  // compound it never ran (no entry in `fits`). If every selected team is absent here, fall back
  // to showing the full field for this compound rather than an empty chart — the established
  // "nothing selected = show everyone" behavior, just reached a different way. The selection
  // itself is untouched, so it resumes if the user switches back to a compound it does apply to.
  const isFiltering = selected.size > 0 && fits.some((f) => selected.has(f.constructor))
  const visibleFits = isFiltering ? fits.filter((f) => selected.has(f.constructor)) : fits
  const visiblePoints = isFiltering ? points.filter((p) => selected.has(p.constructor)) : points

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
            {visiblePoints.map((p, i) => (
              <circle key={i} cx={x(p.tyre_age)} cy={y(p.lap_time_s)} r={1.5} fill={teamColorWithAlpha(p.constructor, 0.16)} />
            ))}

            <AnimatePresence>
              {visibleFits.map((f) => {
                const range = ageRangeByConstructor[f.constructor]
                if (!range) return null
                const [lo, hi] = range
                const stroke = resolveTeamColor(f.constructor)
                // Same key across a compound switch (a team present in both compounds keeps its
                // line mounted), so x1/y1/x2/y2 in `animate` morph smoothly into the new
                // compound's fit instead of snapping. A team missing from the newly-selected
                // compound isn't in visibleFits at all, so it just exits/re-enters via
                // AnimatePresence as before — no morph attempted when there's nothing to morph to.
                const coords = { x1: x(lo), y1: y(f.slope_s_per_lap * lo + f.intercept_s), x2: x(hi), y2: y(f.slope_s_per_lap * hi + f.intercept_s) }
                return (
                  <m.line
                    key={f.constructor}
                    stroke={stroke}
                    strokeWidth={f.flagged ? 3.5 : 2}
                    initial={reduce ? false : { pathLength: 0, opacity: 0, ...coords }}
                    animate={{ pathLength: 1, opacity: 1, ...coords }}
                    exit={{ opacity: 0 }}
                    transition={reduce ? { duration: 0 } : { ...drawTransition, x1: morphTransition, y1: morphTransition, x2: morphTransition, y2: morphTransition }}
                  />
                )
              })}
            </AnimatePresence>
          </g>
        </svg>
      )}

      {/* Ranked worst wear first — also the click-to-isolate control for the chart above (see
          TeamSelectLegend). */}
      <div className="mt-6 border-t border-border pt-5">
        <TeamSelectLegend
          rows={rankedFits.map((f) => ({
            team: f.constructor,
            value: `${f.slope_s_per_lap >= 0 ? '+' : ''}${f.slope_s_per_lap.toFixed(3)}s/lap`,
          }))}
          selected={selected}
          onToggle={toggleTeam}
          isFiltering={isFiltering}
        />
      </div>
      <p className="mt-4 text-xs text-muted">
        Fuel-corrected lap time against tyre age; a bold line marks wear well above the field.
        Ranked worst wear first below — click a team to isolate its line, click again to bring it
        back.
      </p>
    </m.div>
  )
}
