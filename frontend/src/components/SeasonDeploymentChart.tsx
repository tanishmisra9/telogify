import { useState } from 'react'
import { AnimatePresence, m, useReducedMotion } from 'framer-motion'
import { TeamRule } from '@/components/TeamMark'
import { TeamSelectLegend } from '@/components/TeamSelectLegend'
import { resolveTeamColor, teamColorWithAlpha } from '@/lib/teamColors'
import { binBySpeed } from '@/lib/seasonAccel'
import { deploymentInsights } from '@/lib/deploymentInsights'
import { emphasize } from '@/lib/emphasize'
import { drawTransition } from '@/lib/motion'
import { smoothPath } from '@/lib/svgPath'
import type { SeasonDeploymentScatter } from '@/lib/api'

const WIDTH = 1100
const HEIGHT = 460
const MARGIN = { top: 24, right: 24, bottom: 52, left: 56 }
const INNER_W = WIDTH - MARGIN.left - MARGIN.right
const INNER_H = HEIGHT - MARGIN.top - MARGIN.bottom

/** Season-wide ERS deployment/harvesting: longitudinal acceleration vs speed, full-throttle and
 * no-brake laps only. Raw points (a few hundred per team, pooled across the season) sit as a
 * faint texture; each team's binned-median trend line is the actual story. Team identity comes
 * from the same click-to-isolate legend used by Gap by round and Tyre degradation: click a team
 * to isolate its line, multi-select, click again to bring it back. */
export function SeasonDeploymentChart({ scatter }: { scatter: SeasonDeploymentScatter }) {
  const reduce = useReducedMotion()
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const toggleTeam = (team: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(team)) next.delete(team)
      else next.add(team)
      return next
    })

  const teams = Object.keys(scatter)
    .filter((t) => scatter[t].length > 0)
    .sort((a, b) => a.localeCompare(b))
  if (teams.length === 0) return <p className="text-sm text-muted">No deployment data yet.</p>

  const isFiltering = selected.size > 0 && teams.some((t) => selected.has(t))
  const visibleTeams = isFiltering ? teams.filter((t) => selected.has(t)) : teams

  const allPoints = teams.flatMap((t) => scatter[t])
  const speeds = allPoints.map((p) => p[0])
  const accels = allPoints.map((p) => p[1])
  const xMin = Math.min(...speeds)
  const xMax = Math.max(...speeds)
  const yLo = Math.min(...accels)
  const yHi = Math.max(...accels)
  const yPad = (yHi - yLo) * 0.08 || 0.5
  const yMin = yLo - yPad
  const yMax = yHi + yPad

  const x = (v: number) => ((v - xMin) / (xMax - xMin || 1)) * INNER_W
  const y = (v: number) => INNER_H * (1 - (v - yMin) / (yMax - yMin || 1))

  const trends = teams
    .map((team) => ({ team, bins: binBySpeed(scatter[team]) }))
    .filter((t) => t.bins.length >= 2)
  const visibleTrends = isFiltering ? trends.filter((t) => selected.has(t.team)) : trends

  const yTicks = Array.from({ length: 5 }, (_, i) => yMin + ((yMax - yMin) * i) / 4)
  const xTicks = Array.from({ length: 6 }, (_, i) => Math.round(xMin + ((xMax - xMin) * i) / 5))

  // The chart is mute without a read; these are deterministic per-power-unit verdicts computed
  // from the exact scatter below (lib/deploymentInsights.ts), so a reader gets the story before
  // the picture. Empty when fewer than 3 PU groups have rankable data.
  const verdicts = deploymentInsights(scatter)

  return (
    <div className="glass w-full rounded-[--radius-panel] p-5">
      {verdicts.length > 0 && (
        <ol className="mb-5 border-b border-border pb-2">
          {verdicts.map((v, i) => (
            <li
              key={v.name}
              className={`grid gap-x-6 gap-y-1 py-3 sm:grid-cols-[11.5rem_minmax(0,1fr)] ${i > 0 ? 'border-t border-border' : ''}`}
            >
              <span className="min-w-0">
                <span className="flex items-center gap-2 font-display font-semibold text-ink">
                  <TeamRule team={v.worksTeam} />
                  {v.name} power
                </span>
                {/* Full names, not teamShortName: its AM/RB codes exist for the cramped
                    pace-chart axis and read as ciphers in a row with this much width. */}
                <span className="mt-0.5 block pl-[11px] text-xs text-muted">{v.teams.join(' · ')}</span>
              </span>
              <span className="text-sm leading-relaxed text-ink">{emphasize(v.text)}</span>
            </li>
          ))}
        </ol>
      )}

      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full max-w-full" role="img" aria-label="Season ERS deployment: longitudinal acceleration vs speed">
        <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
          {yTicks.map((t) => (
            <g key={t}>
              <line x1={0} x2={INNER_W} y1={y(t)} y2={y(t)} stroke="var(--color-border)" strokeDasharray="4 4" />
              <text x={-9} y={y(t)} textAnchor="end" dominantBaseline="middle" fill="var(--color-muted)" fontSize={13}>
                {t.toFixed(0)}
              </text>
            </g>
          ))}
          {xTicks.map((t) => (
            <text key={t} x={x(t)} y={INNER_H + 22} textAnchor="middle" fill="var(--color-muted)" fontSize={12}>
              {t}
            </text>
          ))}
          <text x={INNER_W / 2} y={INNER_H + 42} textAnchor="middle" fill="var(--color-muted)" fontSize={12}>
            Speed (km/h)
          </text>
          <text x={0} y={-8} textAnchor="start" fill="var(--color-muted)" fontSize={12}>
            Longitudinal acceleration (m/s²)
          </text>

          {visibleTeams.flatMap((team) =>
            scatter[team].map((p, i) => (
              <circle key={`${team}-${i}`} cx={x(p[0])} cy={y(p[1])} r={1.3} fill={teamColorWithAlpha(team, 0.1)} />
            )),
          )}

          <AnimatePresence>
            {visibleTrends.map(({ team, bins }) => {
              const stroke = resolveTeamColor(team)
              const pathD = smoothPath(bins.map((b) => ({ x: x(b.speedMid), y: y(b.medianAccel) })))
              return (
                <m.path
                  key={team}
                  fill="none"
                  stroke={stroke}
                  strokeWidth={2.5}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  initial={reduce ? false : { pathLength: 0, opacity: 0, d: pathD }}
                  animate={{ pathLength: 1, opacity: 1, d: pathD }}
                  exit={{ opacity: 0 }}
                  transition={reduce ? { duration: 0 } : drawTransition}
                />
              )
            })}
          </AnimatePresence>
        </g>
      </svg>

      <div className="mt-6 border-t border-border pt-5">
        <TeamSelectLegend
          rows={teams.map((team) => ({ team }))}
          selected={selected}
          onToggle={toggleTeam}
          isFiltering={isFiltering}
        />
      </div>

      <p className="mt-4 text-xs text-muted">
        Every point is a full-throttle, no-braking sample from one representative race lap per driver per
        weekend, pooled across the season; cornering samples (lateral acceleration at or above 2 m/s²) are
        excluded so only straight-line deployment and harvesting show. Each line is that team's median
        acceleration at each speed. A line that drops toward or below zero at high speed shows the car's
        electrical deployment running out (clipping); a lower full-throttle acceleration at low-to-mid
        speed shows energy being harvested rather than deployed there. Click a team to isolate its line,
        click again to bring it back.
      </p>
    </div>
  )
}
