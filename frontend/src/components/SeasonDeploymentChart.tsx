import { TeamMark } from '@/components/TeamMark'
import { resolveTeamColor, teamColorWithAlpha } from '@/lib/teamColors'
import { binBySpeed } from '@/lib/seasonAccel'
import type { SeasonDeploymentScatter } from '@/lib/api'

const WIDTH = 1100
const HEIGHT = 460
const MARGIN = { top: 24, right: 24, bottom: 52, left: 56 }
const INNER_W = WIDTH - MARGIN.left - MARGIN.right
const INNER_H = HEIGHT - MARGIN.top - MARGIN.bottom

/** Season-wide ERS deployment/harvesting: longitudinal acceleration vs speed, full-throttle and
 * no-brake laps only. Raw points (a few hundred per team, pooled across the season) sit as a
 * faint texture; each team's binned-median trend line is the actual story. Team identity comes
 * from a legend below the chart (color swatch + name, same TeamMark used elsewhere in the app),
 * not on-chart text: direct end-of-line labels broke down once several teams' lines converged to
 * a similar value at top speed. */
export function SeasonDeploymentChart({ scatter }: { scatter: SeasonDeploymentScatter }) {
  const teams = Object.keys(scatter)
    .filter((t) => scatter[t].length > 0)
    .sort((a, b) => a.localeCompare(b))
  if (teams.length === 0) return <p className="text-sm text-muted">No deployment data yet.</p>

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

  const yTicks = Array.from({ length: 5 }, (_, i) => yMin + ((yMax - yMin) * i) / 4)
  const xTicks = Array.from({ length: 6 }, (_, i) => Math.round(xMin + ((xMax - xMin) * i) / 5))

  return (
    <div className="glass w-full rounded-[--radius-panel] p-5">
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

          {teams.flatMap((team) =>
            scatter[team].map((p, i) => (
              <circle key={`${team}-${i}`} cx={x(p[0])} cy={y(p[1])} r={1.3} fill={teamColorWithAlpha(team, 0.1)} />
            )),
          )}

          {trends.map(({ team, bins }) => {
            const stroke = resolveTeamColor(team)
            const path = bins.map((b, j) => `${j === 0 ? 'M' : 'L'}${x(b.speedMid)},${y(b.medianAccel)}`).join(' ')
            return <path key={team} d={path} fill="none" stroke={stroke} strokeWidth={2.5} />
          })}
        </g>
      </svg>

      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 border-t border-border pt-4">
        {teams.map((team) => (
          <TeamMark key={team} team={team} className="text-sm" />
        ))}
      </div>

      <p className="mt-4 text-xs text-muted">
        Every point is a full-throttle, no-braking sample from one representative race lap per driver per
        weekend, pooled across the season; cornering samples (lateral acceleration at or above 2 m/s²) are
        excluded so only straight-line deployment and harvesting show. Each line is that team's median
        acceleration at each speed. A line that drops toward or below zero at high speed shows the car's
        electrical deployment running out (clipping); a flatter, higher line at low-to-mid speed shows
        stronger harvesting there instead.
      </p>
    </div>
  )
}
