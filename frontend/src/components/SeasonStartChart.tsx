import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, m, useReducedMotion } from 'framer-motion'
import { ChartTabs } from '@/components/ChartTabs'
import { PointPopup } from '@/components/PointPopup'
import { ScrollFadeEdge } from '@/components/ScrollFadeEdge'
import { HEIGHT, INNER_H, MARGIN, MIN_ROUND_SLOT } from '@/components/SeasonTrendChart'
import { TeamSelectLegend } from '@/components/TeamSelectLegend'
import { drawTransition, spring } from '@/lib/motion'
import { formSentence, formatGap, legendValue, niceAxis, pointCopy } from '@/lib/seasonStart'
import { monotonePath } from '@/lib/svgPath'
import { resolveTeamColor, teamShortName } from '@/lib/teamColors'
import { useIsMobile } from '@/lib/useIsMobile'
import { useChartPointHover } from '@/lib/useChartPointHover'
import { useScrollFade } from '@/lib/useScrollFade'
import type { SeasonStartData, SeasonStartRow } from '@/lib/api'

type View = 'teams' | 'pu'

// Who has had the best race starts all season: one line per team or power unit, its gap to each
// round's best start (0 at the top, so a line hugging the top has launched best round after
// round). Same layout as Gap by round and the same click-to-isolate legend. Drivers are left out
// on purpose: a season of them is unreadable.
export function SeasonStartChart({ data }: { data: SeasonStartData }) {
  const reduce = useReducedMotion()
  const isMobile = useIsMobile()
  const [view, setView] = useState<View>('teams')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const containerRef = useRef<HTMLDivElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const [containerWidth, setContainerWidth] = useState(0)
  const { hovered, setHovered, isScrolling, pointHandlers } = useChartPointHover(containerRef, wrapRef)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    // width 0 = inside a collapsed section (display:none): keep the last real width so re-opening doesn't re-lay out
    const observer = new ResizeObserver(([entry]) => entry.contentRect.width > 0 && setContainerWidth(entry.contentRect.width))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  const canScrollRight = useScrollFade(containerRef)

  const hasPu = !!data.views.pu
  const activeView: View = view === 'pu' && hasPu ? 'pu' : 'teams'
  const rows: SeasonStartRow[] = data.views[activeView]?.rows ?? []
  // Teams: the team. Power units: the works team's colour, keyed by it (like the deployment chart).
  const colorKey = (r: SeasonStartRow) => (activeView === 'pu' ? r.color_team : r.key)

  const changeView = (v: View) => {
    setView(v)
    setSelected(new Set()) // the two row sets are disjoint
    setHovered(null)
  }
  const toggle = (team: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(team)) next.delete(team)
      else next.add(team)
      return next
    })

  const roundNums = data.rounds.map((r) => r.round)
  const eventOf = new Map(data.rounds.map((r) => [r.round, r.event_name]))
  const allGaps = rows.flatMap((r) => r.points.map((p) => p.gap_pct))
  if (rows.length === 0 || allGaps.length === 0 || roundNums.length === 0) return null

  const xMin = Math.min(...roundNums)
  const xMax = Math.max(...roundNums)
  const innerW = Math.max(containerWidth - MARGIN.right, Math.max(1, roundNums.length - 1) * MIN_ROUND_SLOT)
  const width = innerW + MARGIN.right
  const { max: yMax, ticks: yTicks } = niceAxis(Math.max(...allGaps))
  const x = (v: number) => (xMax === xMin ? innerW / 2 : ((v - xMin) / (xMax - xMin)) * innerW)
  const y = (v: number) => INNER_H * (v / yMax) // 0 at the top: the round's best start

  const isFiltering = selected.size > 0 && rows.some((r) => selected.has(colorKey(r)))
  const visible = isFiltering ? rows.filter((r) => selected.has(colorKey(r))) : rows
  // Best drawn last so the leaders sit on top where lines cross.
  const drawOrder = [...visible].reverse()

  const legendRows = rows.map((r) => ({
    team: colorKey(r),
    // Power units show the manufacturer; on phones a long team name ("Red Bull Racing") is
    // shortened so it isn't cut off beside the stacked figures.
    label: activeView === 'pu' ? r.label : isMobile && r.label.length > 13 ? teamShortName(r.label) : undefined,
    value: legendValue(r),
    title: formSentence(r) ?? undefined,
  }))

  const hoveredRow = hovered ? rows.find((r) => r.key === hovered.key) : undefined
  const hoveredPoint = hoveredRow?.points.find((p) => p.round === hovered?.round)
  const tip = hoveredRow && hoveredPoint ? pointCopy(hoveredRow.label, eventOf.get(hoveredPoint.round), hoveredPoint) : null

  return (
    <m.div
      className="glass w-full rounded-panel p-5"
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={spring}
    >
      {hasPu && (
        <div className="mb-4 flex flex-wrap items-center justify-end gap-3">
          <ChartTabs
            ariaLabel="Group race starts by team or power unit"
            active={activeView}
            onChange={changeView}
            tabs={[
              { value: 'teams', label: 'Teams', hint: 'Median of each team’s cars' },
              { value: 'pu', label: 'Power units', hint: 'Median of every car a power unit supplies' },
            ]}
          />
        </div>
      )}

      <div className="flex">
        {/* Frozen y-axis, as in Gap by round: only the round axis and the lines scroll. */}
        <svg width={MARGIN.left} height={HEIGHT} className="shrink-0" aria-hidden>
          <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
            {yTicks.map((t) => (
              <text key={t} x={-9} y={y(t)} textAnchor="end" dominantBaseline="middle" fill="var(--color-muted)" fontSize={13}>
                {t === 0 ? '0' : formatGap(t).replace('.0', '')}
              </text>
            ))}
          </g>
        </svg>
        <div ref={wrapRef} className="relative min-w-0 flex-1">
          <div ref={containerRef} className="overflow-x-auto overscroll-x-contain">
            <svg
              width={width}
              height={HEIGHT}
              viewBox={`0 0 ${width} ${HEIGHT}`}
              className="max-w-none"
              role="img"
              aria-label="Race start gap to the round's best, by round"
            >
              <g transform={`translate(0,${MARGIN.top})`}>
                {yTicks.map((t) => (
                  <line key={t} x1={0} x2={innerW} y1={y(t)} y2={y(t)} stroke="var(--color-muted)" strokeOpacity={0.35} strokeWidth={1.25} strokeDasharray="4 4" />
                ))}
                {roundNums.map((r) => (
                  <text key={r} x={x(r)} y={INNER_H + 22} textAnchor="middle" fill="var(--color-muted)" fontSize={12}>
                    {r}
                  </text>
                ))}

                <AnimatePresence>
                  {drawOrder.map((row) => (
                    <m.path
                      key={`${activeView}-${row.key}`}
                      fill="none"
                      stroke={resolveTeamColor(row.color_team)}
                      strokeWidth={2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d={monotonePath(row.points.map((p) => ({ x: x(p.round), y: y(p.gap_pct) })))}
                      initial={reduce ? false : { pathLength: 0, opacity: 0 }}
                      animate={{ pathLength: 1, opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={reduce ? { duration: 0 } : drawTransition}
                    />
                  ))}
                </AnimatePresence>

                {/* Points: filled = the full 0-200 run, hollow = only 0-100 was readable that
                    round. A wide transparent circle is the hit target; pointer events are off while
                    the chart is scrolling so a still cursor can't swap the readout. */}
                <g className={isScrolling ? 'pointer-events-none' : undefined}>
                  {drawOrder.map((row) =>
                    row.points.map((p) => {
                      const cx = x(p.round)
                      const cy = y(p.gap_pct)
                      const color = resolveTeamColor(row.color_team)
                      return (
                        <g key={`${activeView}-${row.key}-${p.round}`} {...pointHandlers(row.key, p.round)}>
                          <circle cx={cx} cy={cy} r={12} fill="transparent" />
                          <circle
                            cx={cx}
                            cy={cy}
                            r={p.metric === 200 ? 3.5 : 4}
                            fill={p.metric === 200 ? color : 'var(--color-surface)'}
                            stroke={color}
                            strokeWidth={p.metric === 200 ? 0 : 1.75}
                          />
                        </g>
                      )
                    }),
                  )}
                </g>
              </g>
            </svg>
          </div>
          <ScrollFadeEdge visible={canScrollRight} />
          <p
            className="pointer-events-none absolute inset-x-0 text-center text-xs text-muted"
            style={{ top: MARGIN.top + INNER_H + 36 }}
          >
            Round
          </p>
          <PointPopup hovered={hovered} tip={tip} wrapRef={wrapRef} />
        </div>
      </div>

      <div className="mt-6 border-t border-border pt-5">
        <TeamSelectLegend rows={legendRows} selected={selected} onToggle={toggle} isFiltering={isFiltering} stackValue={isMobile} />
      </div>
      <p className="mt-4 text-sm text-muted">
        Each point is how far a {activeView === 'pu' ? 'power unit' : 'team'}&apos;s start was from that
        round&apos;s best start: the median of its cars over the full 0 to 200 km/h run, as a percentage
        slower than the best. Hollow points are rounds where only 0 to 100 km/h could be read (the first
        braking zone comes before 200 km/h); they are drawn, but left out of the season figures because
        the two scales differ. The legend shows the season gap with recent rounds weighted more (a
        round&apos;s weight halves every 6 rounds), and the arrow is places gained or lost on that recent
        form against the whole season, so it is relative to the rest of the field.
        {activeView === 'pu' &&
          ' A power unit pools every team it supplies, so customer cars differ in chassis, grid slot and traffic: a gap is not purely the engine.'}{' '}
        Click a {activeView === 'pu' ? 'power unit' : 'team'} to isolate its line, click again to bring it back.
      </p>
    </m.div>
  )
}
