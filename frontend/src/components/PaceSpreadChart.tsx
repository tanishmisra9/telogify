import { useEffect, useRef, useState } from 'react'
import { m, useReducedMotion } from 'framer-motion'
import { ChartTabs } from '@/components/ChartTabs'
import { FollowTip } from '@/components/FollowTip'
import { ScrollFadeEdge } from '@/components/ScrollFadeEdge'
import { driverName } from '@/lib/drivers'
import { resolveTeamColor, teamShortName, teamColorWithAlpha } from '@/lib/teamColors'
import { paceAxis, splitOutliers } from '@/lib/paceAxis'
import { useFollowTip } from '@/lib/useFollowTip'
import { useScrollFade } from '@/lib/useScrollFade'
import type { PaceData, PaceRow } from '@/lib/api'

type ViewMode = 'drivers' | 'constructors'

const MARGIN = { top: 24, right: 16, bottom: 110, left: 54 }
const HEIGHT = 480
const INNER_H = HEIGHT - MARGIN.top - MARGIN.bottom
// Structural, not fluid: each column (box plot + its 4 stacked label lines -- code/mean/gap/
// tyre string) gets this many real pixels no matter the container size. A wide desktop card
// fits the whole field for free; a narrow phone card only fits a handful, so the chart scrolls
// horizontally instead of shrinking a fluid-scaled column until the longest label line (the
// tyre-compound string, sometimes 2-3x wider than a driver code) overlaps its neighbor.
// A floor, not a target: slots only compress to this when the container is tight, where the
// alternative is a horizontal scrollbar for a handful of px. 52px still clears the widest
// bottom label stack (driver code / mean / gap / tyre string); a full 21-driver field fits a
// 1280px viewport without scrolling.
const MIN_SLOT = 52
// The label stack under a column (code, median, gap, tyres) ends ~74px below the plot. The hover catcher covers it too, or a
// column whose marks sit low had its middle on uncovered labels and showed no readout there.
const LABEL_H = 74

// Inline d3-scaleBand (paddingInner 0.35, paddingOuter 0.12) so we don't pull in d3-scale.
function bandLayout(innerW: number, n: number) {
  const step = innerW / Math.max(1, n - 0.35 + 2 * 0.12)
  const bandwidth = step * (1 - 0.35)
  const x0 = step * 0.12
  return {
    step,
    bandwidth,
    center: (i: number) => x0 + step * i + bandwidth / 2,
  }
}

// "2 laps slower than 79.8s, off the scale": the readout line for laps the axis had to clip (see lib/paceAxis).
function clippedLines(outliers: number[], axis: ReturnType<typeof paceAxis>): string[] {
  const { slower, faster } = splitOutliers(outliers, axis)
  const lines: string[] = []
  if (slower > 0) lines.push(`${slower} lap${slower > 1 ? 's' : ''} slower than ${axis.capHi.toFixed(1)}s, off the scale`)
  if (faster > 0) lines.push(`${faster} lap${faster > 1 ? 's' : ''} faster than ${axis.capLo.toFixed(1)}s, off the scale`)
  return lines
}

export function PaceSpreadChart({ pace }: { pace: PaceData }) {
  const [viewMode, setViewMode] = useState<ViewMode>('drivers')
  const reduce = useReducedMotion()
  const containerRef = useRef<HTMLDivElement>(null)
  const [containerWidth, setContainerWidth] = useState(0)
  // Hover/tap state, the scroll guard (a wheel scroll under a still cursor must not swap the readout) and the tap-vs-drag touch
  // handling all live in the shared hook, so a fix there reaches every chart. The readout FOLLOWS the pointer (FollowTip).
  const { at, setAt, isScrolling, handlers, pointer } = useFollowTip(containerRef)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    // Floored: contentRect.width is fractional, and the SVG (max-w-none) sized from it can come
    // out a sub-pixel wider than the container's integer layout box -- which reads as a phantom
    // 1px horizontal scrollbar even when the whole field fits.
    // width 0 = inside a collapsed section (display:none): keep the last real width so re-opening doesn't re-lay out
    const observer = new ResizeObserver(([entry]) => entry.contentRect.width > 0 && setContainerWidth(Math.floor(entry.contentRect.width)))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const canScrollRight = useScrollFade(containerRef)

  const rows: PaceRow[] = viewMode === 'drivers' ? pace.drivers : pace.constructors

  // The axis is the whiskers plus a margin: one far outlier (a safety-car lap) no longer squashes every box into the bottom of the
  // plot. A lap beyond it is clipped to the edge as a marker and counted in the readout, never dropped.
  const axis = paceAxis(rows.map((r) => r.stats))
  const { yMin, yMax } = axis
  const anyClipped = rows.some((r) => {
    const c = splitOutliers(r.stats.outliers, axis)
    return c.slower > 0 || c.faster > 0
  })

  // Constructor names run longer than driver codes (e.g. "ALPHATAURI"), but the field is also
  // much smaller (~10 teams vs ~22 drivers), so a wider slot here doesn't cost desktop a scroll.
  const minSlot = viewMode === 'constructors' ? 92 : MIN_SLOT
  const innerWNeeded = rows.length * minSlot
  const innerW = Math.max(containerWidth - MARGIN.left - MARGIN.right, innerWNeeded)
  const width = innerW + MARGIN.left + MARGIN.right
  const band = bandLayout(innerW, rows.length)
  const y = (v: number) => INNER_H * (1 - (v - yMin) / (yMax - yMin))
  const yTicks = Array.from({ length: 6 }, (_, i) => yMin + ((yMax - yMin) * i) / 5)
  const hoveredRow = at ? rows.find((r) => r.id === at.key) : undefined
  const tip = hoveredRow
    ? {
        // "Name, Team" like every other readout on the page (a constructor row is just its team)
        title: hoveredRow.team && hoveredRow.team !== hoveredRow.label ? `${driverName(hoveredRow.label)}, ${hoveredRow.team}` : driverName(hoveredRow.label),
        lines: [
          `Mean ${hoveredRow.stats.mean.toFixed(3)}s`,
          `Median ${hoveredRow.stats.median.toFixed(3)}s`,
          `Q1-Q3 ${hoveredRow.stats.q1.toFixed(3)}-${hoveredRow.stats.q3.toFixed(3)}s`,
          `Ceiling ${hoveredRow.stats.pace_ceiling.toFixed(3)}s`,
          `${hoveredRow.stats.n_laps} laps of data`,
          ...clippedLines(hoveredRow.stats.outliers, axis),
        ],
      }
    : null

  return (
    <m.div
      className="glass w-full rounded-panel p-5"
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 120, damping: 20 }}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-[2.025rem] font-semibold tracking-tight sm:text-[2.7rem]">Pace spread</h2>
        <ChartTabs
          ariaLabel="Chart view"
          active={viewMode}
          onChange={(v) => {
            setAt(null) // the rows change under an open readout
            setViewMode(v)
          }}
          tabs={[
            { value: 'drivers', label: 'Drivers', hint: 'Pace per driver' },
            { value: 'constructors', label: 'Constructors', hint: 'Pace per team' },
          ]}
        />
      </div>

      {rows.length === 0 ? (
        <p className="text-sm text-muted">No pace data.</p>
      ) : (
        <div className="relative">
        <div ref={containerRef} className="relative overflow-x-auto overscroll-x-contain">
        <svg width={width} height={HEIGHT} viewBox={`0 0 ${width} ${HEIGHT}`} className="max-w-none" role="img" aria-label="Pace spread box plot">
          <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
            {yTicks.map((tick) => (
              <g key={tick}>
                <line x1={0} x2={innerW} y1={y(tick)} y2={y(tick)} stroke="var(--color-border)" strokeDasharray="4 4" />
                <text x={-9} y={y(tick)} textAnchor="end" dominantBaseline="middle" fill="var(--color-muted)" fontSize={14}>
                  {tick.toFixed(1)}s
                </text>
              </g>
            ))}

            <g className={isScrolling ? 'pointer-events-none' : ''}>
            {rows.map((row, i) => {
              const cx = band.center(i)
              const bw = Math.min(band.bandwidth * 0.6, 34)
              const s = row.stats
              const stroke = resolveTeamColor(row.team)
              const fill = teamColorWithAlpha(row.team, 0.28)
              const yQ1 = y(s.q1)
              const yQ3 = y(s.q3)
              const boxTop = Math.min(yQ1, yQ3)
              const boxH = Math.abs(yQ3 - yQ1) || 1

              return (
                <g key={row.id} {...handlers(row.id)}>
                  {/* Full-height (plot AND labels), full-band-width invisible catcher so hover doesn't flicker
                      when the cursor moves through the gaps between marks or onto the labels. */}
                  <rect x={cx - band.step / 2} y={0} width={band.step} height={INNER_H + LABEL_H} fill="transparent" />
                  {/* The readout keeps clear of THIS group (the marks + labels), not the catcher above: the catcher spans the
                      plot top, which one car's slow outlier stretches, so the "own" box would reach up to it. */}
                  <g data-row={row.id}>
                  <line x1={cx} x2={cx} y1={y(s.whisker_high)} y2={yQ3} stroke={stroke} strokeWidth={1.5} />
                  <line x1={cx} x2={cx} y1={yQ1} y2={y(s.whisker_low)} stroke={stroke} strokeWidth={1.5} />
                  <line x1={cx - bw / 2} x2={cx + bw / 2} y1={y(s.whisker_high)} y2={y(s.whisker_high)} stroke={stroke} strokeWidth={1.5} />
                  <line x1={cx - bw / 2} x2={cx + bw / 2} y1={y(s.whisker_low)} y2={y(s.whisker_low)} stroke={stroke} strokeWidth={1.5} />
                  <rect x={cx - bw / 2} y={boxTop} width={bw} height={boxH} fill={fill} stroke={stroke} strokeWidth={1} rx={3} />
                  <line x1={cx - bw / 2} x2={cx + bw / 2} y1={y(s.median)} y2={y(s.median)} stroke={stroke} strokeWidth={2.5} />
                  <line x1={cx - bw / 2} x2={cx + bw / 2} y1={y(s.mean)} y2={y(s.mean)} stroke={stroke} strokeWidth={1.5} strokeDasharray="5 4" />
                  {/* Pace ceiling (fast-end quantile): the pace the car showed when pushing. */}
                  <line x1={cx - bw / 2} x2={cx + bw / 2} y1={y(s.pace_ceiling)} y2={y(s.pace_ceiling)} stroke={stroke} strokeWidth={1.25} strokeDasharray="1 3" opacity={0.9} />
                  {splitOutliers(s.outliers, axis).inside.map((o, oi) => (
                    <circle key={`${row.id}-o-${oi}`} cx={cx} cy={y(o)} r={4} fill="none" stroke={stroke} strokeWidth={1.25} />
                  ))}
                  {/* Laps beyond the scale: a triangle on the edge (one per column, the count is in the readout). */}
                  {splitOutliers(s.outliers, axis).slower > 0 && (
                    <path d={`M${cx - 5} 9 L${cx} 1 L${cx + 5} 9 Z`} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinejoin="round" />
                  )}
                  {splitOutliers(s.outliers, axis).faster > 0 && (
                    <path d={`M${cx - 5} ${INNER_H - 9} L${cx} ${INNER_H - 1} L${cx + 5} ${INNER_H - 9} Z`} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinejoin="round" />
                  )}

                  {viewMode === 'drivers' ? (
                    <>
                      <text x={cx} y={INNER_H + 20} textAnchor="middle" fill="var(--color-ink)" fontSize={14} fontWeight={500} className="font-display">
                        {row.label}
                      </text>
                      <text x={cx} y={INNER_H + 36} textAnchor="middle" fill="var(--color-muted)" fontSize={12} className="num">
                        {s.median.toFixed(2)}
                      </text>
                      {row.gap_to_fastest_s > 0 && (
                        <text x={cx} y={INNER_H + 52} textAnchor="middle" fill="var(--color-muted)" fontSize={12} className="num">
                          +{row.gap_to_fastest_s.toFixed(2)}s
                        </text>
                      )}
                      <text x={cx} y={INNER_H + 68} textAnchor="middle" fill="var(--color-muted)" fontSize={12}>
                        {s.compounds.length ? s.compounds.join('-') : 'N/A'}
                      </text>
                    </>
                  ) : (
                    <>
                      <text x={cx} y={INNER_H + 20} textAnchor="middle" fill="var(--color-ink)" fontSize={14} fontWeight={600} className="font-display uppercase tracking-wide">
                        {teamShortName(row.team)}
                      </text>
                      <text x={cx} y={INNER_H + 36} textAnchor="middle" fill="var(--color-muted)" fontSize={12} className="num">
                        {s.median.toFixed(2)}
                      </text>
                      {row.gap_to_fastest_s > 0 && (
                        <text x={cx} y={INNER_H + 52} textAnchor="middle" fill="var(--color-muted)" fontSize={12} className="num">
                          +{row.gap_to_fastest_s.toFixed(2)}s
                        </text>
                      )}
                      <text x={cx} y={INNER_H + 68} textAnchor="middle" fill="var(--color-muted)" fontSize={12}>
                        {s.compounds.length ? s.compounds.join('-') : 'N/A'}
                      </text>
                    </>
                  )}
                  </g>
                </g>
              )
            })}
            </g>

          </g>
        </svg>
        </div>
        <ScrollFadeEdge visible={canScrollRight} />
        </div>
      )}
      {/* The readout follows the pointer and never covers the hovered column's own marks and labels (`data-row`: its highest mark
          down to its bottom labels, NOT the plot top). It renders on the page surface (portal), so it may leave the card. */}
      <FollowTip at={at} tip={tip} pointer={pointer} container={containerRef} />

      {rows.length > 0 && (
        <>
          <p className="mt-4 text-sm text-muted">
            Sorted by median lap; the figure under each name is that median and the gap is the median
            delta to the fastest. Green-flag laps only, lap 1 excluded, fuel-corrected. The box is the
            middle 50 percent of laps, with a solid line at the median, a dashed line at the mean and a
            dotted line at the pace ceiling (a time only the fastest tenth of laps beat). Whiskers reach
            the furthest lap within 1.5 box heights; circles are laps beyond that.{anyClipped && ' A triangle on a column marks laps so far off the scale that the axis stops short of them; hover for how many.'}
          </p>
          {pace.stop_count_spread >= 2 && (
            <p className="mt-2 text-sm text-muted">
              Stop counts vary by up to {pace.stop_count_spread} across the field, so treat these gaps
              as an estimate.
            </p>
          )}
        </>
      )}
    </m.div>
  )
}
