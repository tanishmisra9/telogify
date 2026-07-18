import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, m, useReducedMotion } from 'framer-motion'
import { ChartTabs } from '@/components/ChartTabs'
import { ScrollFadeEdge } from '@/components/ScrollFadeEdge'
import { driverName } from '@/lib/drivers'
import { resolveTeamColor, teamShortName, teamColorWithAlpha } from '@/lib/teamColors'
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

export function PaceSpreadChart({ pace }: { pace: PaceData }) {
  const [viewMode, setViewMode] = useState<ViewMode>('drivers')
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const reduce = useReducedMotion()
  const containerRef = useRef<HTMLDivElement>(null)
  const [containerWidth, setContainerWidth] = useState(0)
  // Same touch-scroll-rejection as BarChart: a finger dragging across box plots to scroll the
  // chart horizontally shouldn't also toggle whichever one it passed over.
  const touchStartRef = useRef<{ x: number; y: number } | null>(null)
  // Mouse-specific gotcha: scrolling via wheel/trackpad while the cursor stays put doesn't move
  // the pointer, but the box plot underneath it changes as the content scrolls past -- and the
  // browser fires a real mouseenter for whatever ends up there, silently swapping the selection
  // out from under the reader. A JS timestamp guard on the handler isn't reliable here (the
  // browser's hit-test recalculation and the scroll event aren't guaranteed to fire in a fixed
  // order), so this disables pointer events on the rows at the CSS level for a beat after any
  // scroll -- the browser then can't dispatch mouseenter to them at all, regardless of ordering.
  const [isScrolling, setIsScrolling] = useState(false)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    // Floored: contentRect.width is fractional, and the SVG (max-w-none) sized from it can come
    // out a sub-pixel wider than the container's integer layout box -- which reads as a phantom
    // 1px horizontal scrollbar even when the whole field fits.
    const observer = new ResizeObserver(([entry]) => setContainerWidth(Math.floor(entry.contentRect.width)))
    observer.observe(el)
    let scrollEndTimeout: ReturnType<typeof setTimeout>
    const onScroll = () => {
      setIsScrolling(true)
      clearTimeout(scrollEndTimeout)
      scrollEndTimeout = setTimeout(() => setIsScrolling(false), 200)
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      observer.disconnect()
      el.removeEventListener('scroll', onScroll)
      clearTimeout(scrollEndTimeout)
    }
  }, [])

  const canScrollRight = useScrollFade(containerRef)

  const rows: PaceRow[] = viewMode === 'drivers' ? pace.drivers : pace.constructors

  const { yMin, yMax } = (() => {
    let lo = Infinity
    let hi = -Infinity
    for (const r of rows) {
      const s = r.stats
      lo = Math.min(lo, s.whisker_low, ...s.outliers)
      hi = Math.max(hi, s.whisker_high, ...s.outliers)
    }
    if (!isFinite(lo)) return { yMin: 0, yMax: 1 }
    const pad = (hi - lo) * 0.06 || 0.5
    return { yMin: lo - pad, yMax: hi + pad }
  })()

  // Constructor names run longer than driver codes (e.g. "ALPHATAURI"), but the field is also
  // much smaller (~10 teams vs ~22 drivers), so a wider slot here doesn't cost desktop a scroll.
  const minSlot = viewMode === 'constructors' ? 92 : MIN_SLOT
  const innerWNeeded = rows.length * minSlot
  const innerW = Math.max(containerWidth - MARGIN.left - MARGIN.right, innerWNeeded)
  const width = innerW + MARGIN.left + MARGIN.right
  const band = bandLayout(innerW, rows.length)
  const y = (v: number) => INNER_H * (1 - (v - yMin) / (yMax - yMin))
  const yTicks = Array.from({ length: 6 }, (_, i) => yMin + ((yMax - yMin) * i) / 5)
  const hovered = rows.find((r) => r.id === hoveredId) ?? null

  // Frozen in place, not tracked against scroll: computed fresh whenever the selected row
  // changes (from the container's scroll offset at that exact moment), then left alone. A
  // popup that re-centered itself on every scroll event dragged along with the chart underneath
  // it, which read as the panel itself moving; it should only move when you pick a new column.
  const [popupPos, setPopupPos] = useState<{ left: number; top: number } | null>(null)
  useEffect(() => {
    const el = containerRef.current
    const idx = rows.findIndex((r) => r.id === hoveredId)
    if (!el || idx === -1) {
      setPopupPos(null)
      return
    }
    const viewportX = MARGIN.left + band.center(idx) - el.scrollLeft
    setPopupPos({
      left: Math.min(Math.max(viewportX - 100, 0), el.clientWidth - 200),
      top: MARGIN.top + 4,
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hoveredId])

  return (
    <m.div
      className="glass w-full rounded-[--radius-panel] p-5"
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 120, damping: 20 }}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-[2.025rem] font-semibold tracking-tight sm:text-[2.7rem]">Pace spread</h2>
        <ChartTabs
          ariaLabel="Chart view"
          active={viewMode}
          onChange={setViewMode}
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
                <g
                  key={row.id}
                  onMouseEnter={() => setHoveredId(row.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  onTouchStart={(e) => {
                    const t = e.touches[0]
                    touchStartRef.current = { x: t.clientX, y: t.clientY }
                  }}
                  onTouchEnd={(e) => {
                    e.preventDefault()
                    const start = touchStartRef.current
                    const t = e.changedTouches[0]
                    const moved = start ? Math.hypot(t.clientX - start.x, t.clientY - start.y) : 0
                    if (moved > 10) return
                    setHoveredId((h) => (h === row.id ? null : row.id))
                  }}
                >
                  {/* Full-height, full-band-width invisible catcher so hover doesn't flicker
                      when the cursor moves through the gaps between marks. */}
                  <rect x={cx - band.step / 2} y={0} width={band.step} height={INNER_H} fill="transparent" />
                  <line x1={cx} x2={cx} y1={y(s.whisker_high)} y2={yQ3} stroke={stroke} strokeWidth={1.5} />
                  <line x1={cx} x2={cx} y1={yQ1} y2={y(s.whisker_low)} stroke={stroke} strokeWidth={1.5} />
                  <line x1={cx - bw / 2} x2={cx + bw / 2} y1={y(s.whisker_high)} y2={y(s.whisker_high)} stroke={stroke} strokeWidth={1.5} />
                  <line x1={cx - bw / 2} x2={cx + bw / 2} y1={y(s.whisker_low)} y2={y(s.whisker_low)} stroke={stroke} strokeWidth={1.5} />
                  <rect x={cx - bw / 2} y={boxTop} width={bw} height={boxH} fill={fill} stroke={stroke} strokeWidth={1} rx={3} />
                  <line x1={cx - bw / 2} x2={cx + bw / 2} y1={y(s.median)} y2={y(s.median)} stroke={stroke} strokeWidth={2.5} />
                  <line x1={cx - bw / 2} x2={cx + bw / 2} y1={y(s.mean)} y2={y(s.mean)} stroke={stroke} strokeWidth={1.5} strokeDasharray="5 4" />
                  {/* Pace ceiling (fast-end quantile): the pace the car showed when pushing. */}
                  <line x1={cx - bw / 2} x2={cx + bw / 2} y1={y(s.pace_ceiling)} y2={y(s.pace_ceiling)} stroke={stroke} strokeWidth={1.25} strokeDasharray="1 3" opacity={0.9} />
                  {s.outliers.map((o, oi) => (
                    <circle key={`${row.id}-o-${oi}`} cx={cx} cy={y(o)} r={4} fill="none" stroke={stroke} strokeWidth={1.25} />
                  ))}

                  {viewMode === 'drivers' ? (
                    <>
                      <text x={cx} y={INNER_H + 20} textAnchor="middle" fill="var(--color-ink)" fontSize={14} fontWeight={500} className="font-display">
                        {row.label}
                      </text>
                      <text x={cx} y={INNER_H + 36} textAnchor="middle" fill="var(--color-muted)" fontSize={12} className="num">
                        {s.mean.toFixed(2)}
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
                        {s.mean.toFixed(2)}
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
              )
            })}
            </g>

          </g>
        </svg>
        </div>
        {/* A plain HTML overlay, not an SVG foreignObject (WebKit's foreignObject support proved
            unreliable enough on a real device to abandon rather than patch again -- see git
            history), and deliberately OUTSIDE the scrolling container, not inside it: positioned
            against this outer non-scrolling wrapper, so it stays put on screen while the chart
            scrolls underneath instead of dragging along with it. Position is frozen per selected
            row (see the effect above), not recalculated on scroll, so it only ever moves when
            you pick a different column -- exactly the same as picking one without having
            scrolled at all. Stable key so switching between two already-selected columns slides
            in place rather than closing/reopening (see BarChart's tag for the same pattern). */}
        <AnimatePresence>
          {hovered && popupPos && (
            <m.div
              key="pace-popup"
              className="glass pointer-events-none absolute w-[200px] rounded-xl px-3 py-2 text-xs text-ink"
              style={{ top: popupPos.top }}
              initial={{ opacity: 0, left: popupPos.left }}
              animate={{ opacity: 1, left: popupPos.left }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
            >
              <div className="font-medium">{driverName(hovered.label)}</div>
              {hovered.team && hovered.team !== hovered.label && (
                <div className="mt-1 text-muted">{hovered.team}</div>
              )}
              <div className="mt-2 space-y-0.5 text-muted">
                <div><span className="font-semibold text-ink">Mean</span> {hovered.stats.mean.toFixed(3)}s</div>
                <div><span className="font-semibold text-ink">Median</span> {hovered.stats.median.toFixed(3)}s</div>
                <div><span className="font-semibold text-ink">Q1-Q3</span> {hovered.stats.q1.toFixed(3)}-{hovered.stats.q3.toFixed(3)}s</div>
                <div><span className="font-semibold text-ink">Ceiling</span> {hovered.stats.pace_ceiling.toFixed(3)}s</div>
                <div><span className="font-semibold text-ink">{hovered.stats.n_laps}</span> laps of data</div>
              </div>
            </m.div>
          )}
        </AnimatePresence>
        <ScrollFadeEdge visible={canScrollRight} />
        </div>
      )}

      {rows.length > 0 && (
        <>
          <p className="mt-4 text-sm text-muted">
            Sorted by mean pace; gaps are mean delta to the fastest. Lap 1 excluded, fuel-corrected.
            Solid line median, dashed line mean, dotted line pace ceiling (fastest tenth of laps), box
            is the middle 50 percent of laps, whiskers cover 99.3 percent, dots are outliers.
          </p>
          {pace.stop_count_spread >= 2 && (
            <p className="mt-2 text-sm text-muted">
              Pit-equated: stop counts vary by up to {pace.stop_count_spread} across the field, so treat
              these gaps as an estimate.
            </p>
          )}
        </>
      )}
    </m.div>
  )
}
