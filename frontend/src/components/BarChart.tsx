import { useEffect, useRef, useState } from 'react'
import { driverName } from '@/lib/drivers'
import { resolveTeamColor, teamColorWithAlpha } from '@/lib/teamColors'

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
// visibly truncated without this margin.
const MARGIN = { top: 28, right: 36, bottom: 34, left: 60 }
const HEIGHT = 260
const INNER_H = HEIGHT - MARGIN.top - MARGIN.bottom
// Structural, not fluid: every driver gets this many real pixels of column width no matter the
// container size. A wide desktop card fits the whole field inside its own width for free; a
// narrow phone card only fits a handful, so the chart scrolls horizontally instead of shrinking
// labels into overlap (the previous approach -- one constant true-pixel font size stretched over
// a fluid-scaled column width -- broke exactly here: the column shrank but the label didn't).
const MIN_SLOT = 40

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
  const containerRef = useRef<HTMLDivElement>(null)
  const [containerWidth, setContainerWidth] = useState(0)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setContainerWidth(entry.contentRect.width))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  if (rows.length === 0) return null

  const innerWNeeded = rows.length * MIN_SLOT
  const innerW = Math.max(containerWidth - MARGIN.left - MARGIN.right, innerWNeeded)
  const width = innerW + MARGIN.left + MARGIN.right

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

  return (
    <div ref={containerRef} className="overflow-x-auto overscroll-x-contain">
      <svg width={width} height={HEIGHT} viewBox={`0 0 ${width} ${HEIGHT}`} className="max-w-none" role="img" aria-label="Bar chart">
        <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
          {yTicks.map((t) => (
            <g key={t}>
              <line x1={0} x2={innerW} y1={y(t)} y2={y(t)} stroke="var(--color-border)" strokeDasharray="4 4" />
              {/* A tick isn't any one row, so format it as a plain axis value (no row-specific
                 displayValue override, e.g. practice sectors' leader-shows-absolute special case). */}
              <text x={-9} y={y(t)} textAnchor="end" dominantBaseline="middle" fill="var(--color-muted)" fontSize={12} className="num">
                {formatValue(t, { id: '', label: '', value: t })}
              </text>
            </g>
          ))}
          {rows.map((r, i) => {
            const cx = center(i)
            const top = y(r.value)
            const stroke = resolveTeamColor(r.team ?? null)
            const fill = teamColorWithAlpha(r.team ?? null, hoveredId === r.id ? 0.8 : 0.55)
            return (
              <g
                key={r.id}
                onMouseEnter={() => setHoveredId(r.id)}
                onMouseLeave={() => setHoveredId((h) => (h === r.id ? null : h))}
              >
                {/* Full column-width AND full chart-height (margins included) hit area, so hovering
                   anywhere above/below a short bar, or over its label, still triggers it. */}
                <rect x={i * step} y={-MARGIN.top} width={step} height={HEIGHT} fill="transparent" />
                <rect
                  x={cx - bw / 2}
                  y={top}
                  width={bw}
                  height={Math.max(1.5, baseline - top)}
                  fill={fill}
                  stroke={stroke}
                  strokeWidth={hoveredId === r.id ? 2 : 1}
                  rx={2}
                  className="pointer-events-none"
                />
                <text x={cx} y={INNER_H + 21} textAnchor="middle" fill="var(--color-ink)" fontSize={13.5} fontWeight={600} className="pointer-events-none font-display">
                  {r.label}
                </text>
              </g>
            )
          })}
          {hoveredRow && (
            <text
              x={center(rows.findIndex((r) => r.id === hoveredRow.id))}
              y={y(hoveredRow.value) - 8}
              textAnchor="middle"
              fill="var(--color-ink)"
              fontSize={13}
              fontWeight={700}
              className="num pointer-events-none"
            >
              {driverName(hoveredRow.label)} {formatValue(hoveredRow.displayValue ?? hoveredRow.value, hoveredRow)}
            </text>
          )}
        </g>
      </svg>
    </div>
  )
}
