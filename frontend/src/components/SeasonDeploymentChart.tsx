import { useRef, useState } from 'react'
import { AnimatePresence, m, useReducedMotion } from 'framer-motion'
import { ChartTabs } from '@/components/ChartTabs'
import { DesktopOnlyNote } from '@/components/DesktopOnlyNote'
import { PointPopup } from '@/components/PointPopup'
import { TeamSelectLegend } from '@/components/TeamSelectLegend'
import { resolveTeamColor, teamColorWithAlpha } from '@/lib/teamColors'
import { BIN_WIDTH_KMH, binBySpeed } from '@/lib/seasonAccel'
import { drawTransition } from '@/lib/motion'
import { smoothPath } from '@/lib/svgPath'
import { formArrow, formMoveSentence } from '@/lib/seasonStart'
import { useChartPointHover } from '@/lib/useChartPointHover'
import { useSvgTextScale } from '@/lib/useSvgTextScale'
import type { DeploymentRankingRow, PuGroup, SeasonDeploymentScatter } from '@/lib/api'

const WIDTH = 1100
const HEIGHT = 460
const MARGIN = { top: 24, right: 24, bottom: 52, left: 56 }
const INNER_W = WIDTH - MARGIN.left - MARGIN.right
const INNER_H = HEIGHT - MARGIN.top - MARGIN.bottom

type View = 'teams' | 'pu'

/** Pool each PU group's member teams' scatter into one series per manufacturer, keyed by the
 * manufacturer name (display) but colored by its works team. */
function poolByPu(scatter: SeasonDeploymentScatter, groups: PuGroup[]): SeasonDeploymentScatter {
  const out: SeasonDeploymentScatter = {}
  for (const g of groups) {
    const pooled = g.teams.flatMap((t) => scatter[t] ?? [])
    if (pooled.length > 0) out[g.name] = pooled
  }
  return out
}

/** Season-wide deployment: longitudinal acceleration vs speed, full-throttle and no-brake laps
 * only. Raw points (thousands per team, pooled across the season, server-capped per team in
 * analysis/season.py) sit as a faint texture; each series' binned-median trend line is the
 * actual story (the LLM-written verdicts render above this chart as Insight panels, see
 * SeasonPage.tsx). The Teams/Power units toggle switches between one line per constructor and
 * one line per power-unit manufacturer (teams pooled under their works team's color). Team
 * identity comes from the same click-to-isolate legend used by Gap by round and Tyre
 * degradation: click a row to isolate its line, multi-select, click again to bring it back;
 * the selection resets when the view switches, since the two views' row sets are disjoint. */
export function SeasonDeploymentChart({
  scatter,
  puGroups,
  ranking = [],
}: {
  scatter: SeasonDeploymentScatter
  puGroups: PuGroup[]
  ranking?: DeploymentRankingRow[]
}) {
  const reduce = useReducedMotion()
  const { ref, textPx } = useSvgTextScale(WIDTH)
  const [view, setView] = useState<View>('teams')
  // Keyed by the SAME identity TeamSelectLegend uses for its rows: the color key (colorKeyFor
  // below), not the row label. In "teams" mode the two coincide; in "pu" mode the color key is
  // the works team (e.g. "Aston Martin" for the "Honda" row), since only real team names
  // resolve to a color.
  const [selected, setSelected] = useState<Set<string>>(new Set())
  // A dot per binned median on each trend line, with a readout (same hook and popup as the by-round charts).
  const plotRef = useRef<HTMLDivElement>(null)
  const { hovered, setHovered, pointHandlers } = useChartPointHover(plotRef)

  const toggleRow = (colorKey: string) => {
    setHovered(null) // touch has no mouseleave: an open readout must not outlive its hidden line
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(colorKey)) next.delete(colorKey)
      else next.add(colorKey)
      return next
    })
  }

  const changeView = (next: View) => {
    setView(next)
    setSelected(new Set())
    setHovered(null)
  }

  const puScatter = poolByPu(scatter, puGroups)
  const active = view === 'pu' ? puScatter : scatter
  // In PU mode, color/selection key comes from the works team; the row's own key/label is the
  // PU name.
  const colorKeyFor = (row: string): string =>
    view === 'pu' ? puGroups.find((g) => g.name === row)?.works_team ?? row : row

  const rows = Object.keys(active)
    .filter((r) => active[r].length > 0)
    .sort((a, b) => a.localeCompare(b))
  if (rows.length === 0) return <p className="text-sm text-muted">No deployment data yet.</p>

  const isFiltering = selected.size > 0 && rows.some((r) => selected.has(colorKeyFor(r)))
  const visibleRows = isFiltering ? rows.filter((r) => selected.has(colorKeyFor(r))) : rows

  const allPoints = rows.flatMap((r) => active[r])
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

  const trends = rows
    .map((row) => ({ row, bins: binBySpeed(active[row]) }))
    .filter((t) => t.bins.length >= 2)
  const visibleTrends = isFiltering ? trends.filter((t) => selected.has(colorKeyFor(t.row))) : trends

  const hoveredBin = hovered ? trends.find((t) => t.row === hovered.key)?.bins[hovered.round] : undefined
  const tip =
    hovered && hoveredBin
      ? {
          title: hovered.key,
          lines: [
            `${hoveredBin.speedMid - BIN_WIDTH_KMH / 2} to ${hoveredBin.speedMid + BIN_WIDTH_KMH / 2} km/h`,
            `Median acceleration ${hoveredBin.medianAccel >= 0 ? '+' : ''}${hoveredBin.medianAccel.toFixed(2)} m/s²`,
            `${hoveredBin.n} samples${hoveredBin.n < 30 ? ' (few: read with care)' : ''}`,
          ],
        }
      : null

  const yTicks = Array.from({ length: 5 }, (_, i) => yMin + ((yMax - yMin) * i) / 4)
  const xTicks = Array.from({ length: 6 }, (_, i) => Math.round(xMin + ((xMax - xMin) * i) / 5))

  return (
    <>
    {/* Mobile only gets the plain desktop-only note below (no tab selector, no outer panel
        chrome around an interactive chart that isn't there) -- this whole panel, tabs
        included, is desktop-only. */}
    <div className="glass hidden w-full rounded-panel p-5 md:block">
      {/* Right-aligned, no title beside it: same shape as SeasonTrendChart's tab row (the
          other title-less chart on this page), not the title+tabs justify-between pairing
          DegradationChart/FightToPoleChart/PaceSpreadChart use. */}
      <div className="mb-5 flex items-center justify-end gap-4">
        <ChartTabs
          ariaLabel="Group by teams or power units"
          active={view}
          onChange={changeView}
          tabs={[
            { value: 'teams', label: 'Teams' },
            { value: 'pu', label: 'Power units' },
          ]}
        />
      </div>

      <div ref={plotRef}>
        <svg ref={ref} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full max-w-full" role="img" aria-label="Season deployment: longitudinal acceleration vs speed">
          <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
            {yTicks.map((t) => (
              <g key={t}>
                <line x1={0} x2={INNER_W} y1={y(t)} y2={y(t)} stroke="var(--color-border)" strokeDasharray="4 4" />
                <text x={-9} y={y(t)} textAnchor="end" dominantBaseline="middle" fill="var(--color-muted)" fontSize={textPx(13)}>
                  {t.toFixed(0)}
                </text>
              </g>
            ))}
            {xTicks.map((t) => (
              <text key={t} x={x(t)} y={INNER_H + 22} textAnchor="middle" fill="var(--color-muted)" fontSize={textPx(12)}>
                {t}
              </text>
            ))}
            <text x={INNER_W / 2} y={INNER_H + 42} textAnchor="middle" fill="var(--color-muted)" fontSize={textPx(12)}>
              Speed (km/h)
            </text>
            <text x={0} y={-8} textAnchor="start" fill="var(--color-muted)" fontSize={textPx(12)}>
              Longitudinal acceleration (m/s²)
            </text>

            {/* One path per row instead of one <circle> per point: with several representative
                laps per driver now sampled at ingest, a row's cloud can run into the thousands
                of points, and a `<circle>` per point becomes real DOM weight at that count. Each
                `M x,y h0.01` draws an imperceptible sliver that the round linecap renders as a
                dot, so the same look costs one path node per row instead of one node per point. */}
            {visibleRows.map((row) => (
              <path
                key={`dots-${row}`}
                d={active[row].map(([sp, ac]) => `M${x(sp)},${y(ac)}h0.01`).join('')}
                stroke={teamColorWithAlpha(colorKeyFor(row), 0.2)}
                strokeWidth={2.6}
                strokeLinecap="round"
                fill="none"
              />
            ))}

            <AnimatePresence>
              {visibleTrends.map(({ row, bins }) => {
                const stroke = resolveTeamColor(colorKeyFor(row))
                const pathD = smoothPath(bins.map((b) => ({ x: x(b.speedMid), y: y(b.medianAccel) })))
                return (
                  <m.path
                    key={row}
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

            {/* One dot per binned median on each visible trend line: hover or tap for the speed band, the median
                acceleration and how many samples it rests on. */}
            {visibleTrends.map(({ row, bins }) => {
              const color = resolveTeamColor(colorKeyFor(row))
              return bins.map((b, bi) => (
                <g key={`${view}-${row}-${bi}`} {...pointHandlers(row, bi)}>
                  <circle cx={x(b.speedMid)} cy={y(b.medianAccel)} r={10} fill="transparent" />
                  <circle cx={x(b.speedMid)} cy={y(b.medianAccel)} r={3.5} fill={color} />
                </g>
              ))
            })}
          </g>
        </svg>
        <PointPopup hovered={hovered} tip={tip} />

        <div className="mt-6 border-t border-border pt-5">
          <TeamSelectLegend
            rows={rows.map((row) => {
              // Power units carry their ranking's form arrow (teams have no per-team ranking here).
              const rk = view === 'pu' ? ranking.find((r) => r.pu === row) : undefined
              return {
                team: colorKeyFor(row),
                label: view === 'pu' ? row : undefined,
                value: rk ? formArrow(rk.form_places) || undefined : undefined,
                title: rk ? formMoveSentence(rk.form_places) ?? undefined : undefined,
              }
            })}
            selected={selected}
            onToggle={toggleRow}
            isFiltering={isFiltering}
          />
        </div>

        <p className="mt-4 text-sm text-muted">
          The faint points are full-throttle, no-braking samples from up to five of each driver&apos;s
          fastest race laps per weekend, pooled across the season; cornering samples (lateral acceleration
          of 2 m/s² or more) are excluded, so only straight-line deployment and harvesting show. Click a
          row to isolate its line, click again to bring it back.
        </p>
      </div>
    </div>

    <DesktopOnlyNote>
      The acceleration-by-speed chart behind these verdicts needs a larger screen.
    </DesktopOnlyNote>
    </>
  )
}
