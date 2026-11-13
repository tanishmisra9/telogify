import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import { ScrollFadeEdge } from '@/components/ScrollFadeEdge'
import { useScrollFade } from '@/lib/useScrollFade'

// Layout shared by the two "by round" charts (Gap by round, Race starts) so their axes line up.
const HEIGHT = 440
export const MARGIN = { top: 16, right: 16, bottom: 52, left: 56 }
export const INNER_H = HEIGHT - MARGIN.top - MARGIN.bottom
// Structural, not fluid: each round gets this many real pixels of x-axis space no matter the
// container size, same reasoning as BarChart/PaceSpreadChart. Generous on purpose, not just
// enough to avoid tick overlap: these charts draw up to ~10 overlapping team lines per round, and
// a fluid-scaled axis squeezed thin later in a season reads as a tangle -- a heart monitor, not
// a comparison. Scrolling a wider chart beats cramming a full season into one screenful.
export const MIN_ROUND_SLOT = 64
const PLOT_PAD = 8 // below the last gridline, so a dot sitting on it isn't clipped
// Left of the first round: x(first round) is 0, and the svg clips at its own edge, so without this the first dot
// (r 3.5) is half cut and its tap target (r 12) loses half its width. Equal to the hit circle's radius.
export const PLOT_PAD_X = 12
const VIEWPORT_H = MARGIN.top + INNER_H + PLOT_PAD
const STRIP_H = MARGIN.bottom - PLOT_PAD

export interface AxisTick {
  pos: number // along the plot, in plot pixels (0 = the plot's top or left edge)
  label: string
}

// The chart's scrolling viewport plus its two axes. The plot scrolls in both directions once zoomed;
// the y labels (left) and the round labels (below) live OUTSIDE the scroller so they stay on screen, and
// follow the scroll position through a direct `transform` write in the scroll handler (no React render per
// scroll tick, so they move in the same frame as the plot, not one behind). Children are drawn in plot
// coordinates (x in 0..innerW, y in 0..innerH); gridlines come from `yTicks`.
// Deliberate exception to the "one scroll system" layout rule: the vertical scroll region only exists while
// zoomed (at 1x the viewport is exactly as tall as the plot), by request, to navigate a zoomed chart.
export function ZoomChartFrame({
  viewportRef,
  innerW,
  innerH,
  yTicks,
  xTicks,
  zoomed,
  svgLabel,
  regionLabel,
  children,
}: {
  viewportRef: RefObject<HTMLDivElement | null>
  innerW: number
  innerH: number
  yTicks: AxisTick[]
  xTicks: AxisTick[]
  zoomed: boolean
  svgLabel: string
  regionLabel: string
  children: ReactNode
}) {
  const canScrollRight = useScrollFade(viewportRef)
  const yGroup = useRef<SVGGElement>(null)
  const xGroup = useRef<SVGGElement>(null)
  const [view, setView] = useState({ w: 0, h: VIEWPORT_H })

  const sync = () => {
    const el = viewportRef.current
    if (!el) return
    yGroup.current?.setAttribute('transform', `translate(${MARGIN.left},${MARGIN.top - el.scrollTop})`)
    xGroup.current?.setAttribute('transform', `translate(${-el.scrollLeft},0)`)
  }
  const measure = () => {
    const el = viewportRef.current
    if (el) setView((v) => (v.w === el.clientWidth && v.h === el.clientHeight ? v : { w: el.clientWidth, h: el.clientHeight }))
  }

  // Re-apply after every commit (new ticks / sizes), and size the axis svgs before the first paint.
  useLayoutEffect(() => {
    sync()
    measure()
  })

  useEffect(() => {
    const el = viewportRef.current
    if (!el) return
    el.addEventListener('scroll', sync, { passive: true })
    const ro = new ResizeObserver(() => {
      measure()
      sync()
    })
    ro.observe(el)
    return () => {
      el.removeEventListener('scroll', sync)
      ro.disconnect()
    }
    // sync/measure only read refs and call setState; they are stable in effect
  }, [viewportRef])

  const plotW = PLOT_PAD_X + innerW + MARGIN.right
  const plotH = MARGIN.top + innerH + PLOT_PAD

  return (
    <div className="flex">
      <svg width={MARGIN.left} height={view.h} className="shrink-0" aria-hidden>
        <g ref={yGroup} transform={`translate(${MARGIN.left},${MARGIN.top})`}>
          {yTicks.map((t) => (
            <text key={t.label} x={-9} y={t.pos} textAnchor="end" dominantBaseline="middle" fill="var(--color-muted)" fontSize={13}>
              {t.label}
            </text>
          ))}
        </g>
      </svg>
      <div className="relative min-w-0 flex-1">
        <div
          ref={viewportRef}
          role="region"
          aria-label={regionLabel}
          tabIndex={0}
          className="overflow-auto overscroll-x-contain touch-pan-x touch-pan-y focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          style={zoomed ? { height: VIEWPORT_H } : undefined}
        >
          <svg width={plotW} height={plotH} viewBox={`0 0 ${plotW} ${plotH}`} className="block max-w-none" role="img" aria-label={svgLabel}>
            <g transform={`translate(${PLOT_PAD_X},${MARGIN.top})`}>
              {yTicks.map((t) => (
                <line key={t.label} x1={-PLOT_PAD_X} x2={innerW} y1={t.pos} y2={t.pos} stroke="var(--color-muted)" strokeOpacity={0.35} strokeWidth={1.25} strokeDasharray="4 4" />
              ))}
              {children}
            </g>
          </svg>
        </div>
        <ScrollFadeEdge visible={canScrollRight} />
        <svg width={view.w} height={STRIP_H} aria-hidden className="block">
          <g ref={xGroup}>
            {xTicks.map((t) => (
              <text key={t.label} x={t.pos + PLOT_PAD_X} y={14} textAnchor="middle" fill="var(--color-muted)" fontSize={12}>
                {t.label}
              </text>
            ))}
          </g>
          <text x={view.w / 2} y={38} textAnchor="middle" fill="var(--color-muted)" fontSize={12}>
            Round
          </text>
        </svg>
      </div>
    </div>
  )
}
