import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, m } from 'framer-motion'
import { ScrollFadeEdge } from '@/components/ScrollFadeEdge'
import { resolveTeamColor, teamColorWithAlpha } from '@/lib/teamColors'
import { useScrollFade } from '@/lib/useScrollFade'

export interface BarChartRow {
  id: string
  label: string
  value: number
  /** Shown instead of `value` when set (e.g. an absolute time while `value` drives bar height
   * as a gap-to-fastest). */
  displayValue?: number
  team?: string | null
}

// Real breathing room on every edge, not just enough for the average case: an <svg> element
// clips at its own viewBox edge by default, so a wide axis tick (e.g. "+1.293s"), the last bar's
// hover label, or the tallest bar's hover label (it sits right above the top gridline) all get
// visibly truncated without this margin. top must clear the hover tag's full height (26px) plus
// its gap above the bar (see GAP_ABOVE_BAR below) -- the tallest bar in any dataset always
// touches y=0 exactly, so anything less forces the tag's clamp to overlap into the bar itself.
const MARGIN = { top: 46, right: 36, bottom: 34, left: 60 }
const HEIGHT = 260
const INNER_H = HEIGHT - MARGIN.top - MARGIN.bottom
// Structural, not fluid: every driver gets this many real pixels of column width no matter the
// container size. A wide desktop card fits the whole field inside its own width for free; a
// narrow phone card only fits a handful, so the chart scrolls horizontally instead of shrinking
// labels into overlap (the previous approach -- one constant true-pixel font size stretched over
// a fluid-scaled column width -- broke exactly here: the column shrank but the label didn't).
const MIN_SLOT = 40
// The hover/tap value callout: a small enclosed tag sized for the widest realistic value
// ("+1.293s", "28.094s").
const PANEL_W = 80
const PANEL_H = 26
// Real breathing room above the bar, not sitting right on its tip.
const GAP_ABOVE_BAR = 14

/** Shared vertical bar chart: one bar per row, team-colored, row label below, a light y-axis
 * for at-rest reading, and the exact value on hover (one at a time). Used for practice best
 * sectors and top speeds. Scrolls horizontally on narrow containers instead of thinning labels. */
export function BarChart({
  rows,
  formatValue = (v) => v.toFixed(3),
  domainMin = 0,
}: {
  rows: BarChartRow[]
  formatValue?: (v: number, row: BarChartRow) => string
  domainMin?: number
}) {
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  // The hover hit-rect spans a column's full width (see below), so the cursor can land
  // anywhere across it, not just at the bar's own center; tracking it directly is what lets
  // the tag actually sit under the pointer left-to-right instead of snapping to the bar's
  // fixed center. Vertically the tag stays pinned to the bar's own peak (see panelY below) --
  // that axis reads as "attached to this bar's value," not "chasing the cursor."
  const [hoveredX, setHoveredX] = useState(0)
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [containerWidth, setContainerWidth] = useState(0)
  // Dragging a finger across bars to scroll the chart horizontally was also toggling whatever
  // bar the finger passed over (touchend fires wherever the finger lifts, scroll or not). Only
  // treat it as a tap -- and toggle the label -- if the finger barely moved between start and end.
  const touchStartRef = useRef<{ x: number; y: number } | null>(null)
  // Mouse-specific gotcha: scrolling via wheel/trackpad while the cursor stays put doesn't move
  // the pointer, but the bar underneath it changes as the content scrolls past -- and the browser
  // fires a real mouseenter for whatever ends up there, silently swapping the selection out from
  // under the reader. A JS timestamp guard on the handler isn't reliable (the browser's hit-test
  // recalculation and the scroll event aren't guaranteed to fire in a fixed order), so this
  // disables pointer events on the bars at the CSS level for a beat after any scroll -- the
  // browser then can't dispatch mouseenter to them at all, regardless of ordering.
  const [isScrolling, setIsScrolling] = useState(false)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setContainerWidth(entry.contentRect.width))
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

  if (rows.length === 0) return null

  const innerWNeeded = rows.length * MIN_SLOT
  // containerWidth is the scrolling area alone (the y-axis panel is a separate flex sibling
  // with its own width, see the frozen axis <svg> below), so only MARGIN.right -- the scrolling
  // SVG's own breathing room -- comes off it.
  const innerW = Math.max(containerWidth - MARGIN.right, innerWNeeded)
  const width = innerW + MARGIN.right

  const lo = Math.min(domainMin, ...rows.map((r) => r.value))
  const hi = Math.max(...rows.map((r) => r.value)) || 1
  const span = hi - lo || 1
  const y = (v: number) => INNER_H * (1 - (v - lo) / span)

  const step = innerW / rows.length
  const bw = Math.min(30, step * 0.6)
  const center = (i: number) => step * i + step / 2
  const baseline = y(lo)
  const yTicks = Array.from({ length: 4 }, (_, i) => lo + (span * i) / 3)
  const hoveredRow = rows.find((r) => r.id === hoveredId) ?? null

  // Local X in the same coordinate space as the inner <g> (SVG units happen to equal CSS
  // pixels here: explicit width/height attrs match the viewBox 1:1, no independent scaling).
  // getBoundingClientRect() already reflects the container's horizontal scroll position, so
  // this stays correct while the chart is scrolled.
  const localX = (clientX: number) => {
    const rect = svgRef.current?.getBoundingClientRect()
    return rect ? clientX - rect.left : 0
  }

  return (
    <div className="flex">
      {/* Frozen y-axis: its own small SVG outside the scrolling container, not part of it, so
          the value scale stays put and readable no matter how far into the field you've
          scrolled. Only the gridlines, bars, and labels scroll. */}
      <svg width={MARGIN.left} height={HEIGHT} className="shrink-0" aria-hidden>
        <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
          {yTicks.map((t) => (
            <text key={t} x={-9} y={y(t)} textAnchor="end" dominantBaseline="middle" fill="var(--color-muted)" fontSize={12} className="num">
              {/* A tick isn't any one row, so format it as a plain axis value (no row-specific
                 displayValue override, e.g. practice sectors' leader-shows-absolute special case). */}
              {formatValue(t, { id: '', label: '', value: t })}
            </text>
          ))}
        </g>
      </svg>
      <div className="relative min-w-0 flex-1">
      <div ref={containerRef} className="overflow-x-auto overscroll-x-contain">
      <svg ref={svgRef} width={width} height={HEIGHT} viewBox={`0 0 ${width} ${HEIGHT}`} className="max-w-none" role="img" aria-label="Bar chart">
        <g transform={`translate(0,${MARGIN.top})`}>
          {yTicks.map((t) => (
            <line key={t} x1={0} x2={innerW} y1={y(t)} y2={y(t)} stroke="var(--color-border)" strokeDasharray="4 4" />
          ))}
          <g className={isScrolling ? 'pointer-events-none' : ''}>
          {rows.map((r, i) => {
            const cx = center(i)
            const top = y(r.value)
            const stroke = resolveTeamColor(r.team ?? null)
            const fill = teamColorWithAlpha(r.team ?? null, hoveredId === r.id ? 0.8 : 0.55)
            return (
              <g
                key={r.id}
                className="cursor-pointer"
                onMouseEnter={(e) => {
                  setHoveredId(r.id)
                  setHoveredX(localX(e.clientX))
                }}
                onMouseMove={(e) => setHoveredX(localX(e.clientX))}
                onMouseLeave={() => setHoveredId((h) => (h === r.id ? null : h))}
                // Touch has no hover to toggle off, so a tap here should show/hide the label on
                // its own -- but touch also fires a synthetic mouseenter (then a click) after
                // this, and toggling from both raced: the click's toggle would immediately
                // undo whatever mouseenter had just set, so it looked like it flickered and
                // needed a second tap. preventDefault on touchend stops the browser from firing
                // that synthetic mouse sequence at all, so only this handler runs for touch.
                onTouchStart={(e) => {
                  const t = e.touches[0]
                  touchStartRef.current = { x: t.clientX, y: t.clientY }
                  setHoveredX(localX(t.clientX))
                }}
                onTouchEnd={(e) => {
                  e.preventDefault()
                  const start = touchStartRef.current
                  const t = e.changedTouches[0]
                  const moved = start ? Math.hypot(t.clientX - start.x, t.clientY - start.y) : 0
                  if (moved > 10) return
                  setHoveredId((h) => (h === r.id ? null : r.id))
                }}
              >
                {/* Full column-width AND full chart-height (margins included) hit area, so hovering
                   anywhere above/below a short bar, or over its label, still triggers it. */}
                <rect x={i * step} y={-MARGIN.top} width={step} height={HEIGHT} fill="transparent" />
                <m.rect
                  x={cx - bw / 2}
                  y={top}
                  width={bw}
                  height={Math.max(1.5, baseline - top)}
                  animate={{ fill, stroke, strokeWidth: hoveredId === r.id ? 2 : 1 }}
                  transition={{ duration: 0.18 }}
                  rx={2}
                  className="pointer-events-none"
                />
                <text x={cx} y={INNER_H + 21} textAnchor="middle" fill="var(--color-ink)" fontSize={13.5} fontWeight={600} className="pointer-events-none font-display">
                  {r.label}
                </text>
              </g>
            )
          })}
          </g>
          {/* Stable key, not keyed by hoveredRow.id: switching from one bar to an adjacent one
              should slide the SAME tag over to the new position and swap its value, not
              unmount/remount a new instance (which always looks like the tag closing and
              reopening, no matter how the exit/enter timing is tuned). Fade in/out only happens
              on the true open/close transition; switching between two already-tapped bars just
              moves the tag and its rects/text in place via their own animated x/y. */}
          <AnimatePresence>
            {hoveredRow &&
              (() => {
                // A small enclosed tag, not bare text: reads as a callout instead of a stray
                // number floating in the chart. X is magnetic: it leans toward the cursor but
                // mostly stays parked at the bar's own center (only MAGNET of the cursor's
                // offset from center actually shows), so sweeping the mouse around inside one
                // driver's column doesn't drag the tag all over the place -- it only really
                // moves once the cursor crosses into a different bar's column and the center
                // itself jumps. Y stays pinned to the bar's own peak so it reads as "attached to
                // this bar," not chasing the cursor vertically. Both clamp so the tag never runs
                // off the SVG's edges.
                const cx = center(rows.findIndex((r) => r.id === hoveredRow.id))
                const MAGNET = 0.3
                const magnetX = cx + (hoveredX - cx) * MAGNET
                const panelX = Math.min(Math.max(magnetX - PANEL_W / 2, 0), Math.max(0, innerW - PANEL_W))
                const panelY = Math.max(y(hoveredRow.value) - PANEL_H - GAP_ABOVE_BAR, -MARGIN.top + 4)
                return (
                  // Blur fade for true open/close (safe here -- this is plain SVG, not a
                  // foreignObject, so it doesn't hit the WebKit filter-corruption bug). Each
                  // child's `initial` matches its own first-render position exactly, so nothing
                  // animates in from the SVG's (0,0) corner on first mount -- only `animate`
                  // changing on a later re-render (switching to a different bar while already
                  // open) actually moves them, which is the intended slide.
                  <m.g
                    key="bar-panel"
                    className="pointer-events-none"
                    initial={{ opacity: 0, filter: 'blur(4px)' }}
                    animate={{ opacity: 1, filter: 'blur(0px)' }}
                    exit={{ opacity: 0, filter: 'blur(4px)' }}
                    transition={{ duration: 0.16 }}
                  >
                    <m.rect
                      initial={{ x: panelX + 2.5, y: panelY + 2.5 }}
                      animate={{ x: panelX + 2.5, y: panelY + 2.5 }}
                      transition={{ duration: 0.16 }}
                      width={PANEL_W}
                      height={PANEL_H}
                      fill="var(--color-shadow)"
                      rx={2}
                    />
                    <m.rect
                      initial={{ x: panelX, y: panelY }}
                      animate={{ x: panelX, y: panelY }}
                      transition={{ duration: 0.16 }}
                      width={PANEL_W}
                      height={PANEL_H}
                      fill="var(--color-surface)"
                      stroke="var(--color-ink)"
                      strokeWidth={1.5}
                      rx={2}
                    />
                    <m.text
                      initial={{ x: panelX + PANEL_W / 2, y: panelY + PANEL_H / 2 + 1 }}
                      animate={{ x: panelX + PANEL_W / 2, y: panelY + PANEL_H / 2 + 1 }}
                      transition={{ duration: 0.16 }}
                      textAnchor="middle"
                      dominantBaseline="middle"
                      fill="var(--color-ink)"
                      fontSize={13}
                      fontWeight={700}
                      className="num"
                    >
                      {formatValue(hoveredRow.displayValue ?? hoveredRow.value, hoveredRow)}
                    </m.text>
                  </m.g>
                )
              })()}
          </AnimatePresence>
        </g>
      </svg>
      </div>
      <ScrollFadeEdge visible={canScrollRight} />
      </div>
    </div>
  )
}
