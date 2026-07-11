import { useRef, useState, type MouseEvent } from 'react'
import { m, useReducedMotion } from 'framer-motion'
import { driverName } from '@/lib/drivers'
import { resolveTeamColor } from '@/lib/teamColors'
import { drawTransition } from '@/lib/motion'
import type { QualiTraceData, QualiTraceDriver } from '@/lib/api'

const WIDTH = 1100
const PANEL_H = 150
const PANEL_GAP = 28
const MARGIN = { top: 38, right: 20, bottom: 28, left: 56 }
const INNER_W = WIDTH - MARGIN.left - MARGIN.right
const PANELS_H = PANEL_H * 3 + PANEL_GAP * 2
const HEIGHT = MARGIN.top + PANELS_H + MARGIN.bottom

// ponytail: locked to P1 vs P2 -- data.drivers is already ordered fastest-first by the API, so
// [0]/[1] are pole/runner-up. Upgrade path: accept a driver-pair prop (or a picker) over
// data.drivers when comparing more than the top two is ever needed; QualiTrace/the API already
// carry every driver's trace, so that's a frontend-only change, no ingest/DB work required.

// Plain point-to-point path, not lib/svgPath's smoothPath (Catmull-Rom) -- that's tuned for
// sparse, hand-picked points (round-by-round trend lines) and would overshoot on dense,
// already-smooth telemetry samples like these.
function linePath(xs: number[], ys: number[]): string {
  if (xs.length === 0) return ''
  let d = `M ${xs[0]},${ys[0]}`
  for (let i = 1; i < xs.length; i++) d += ` L ${xs[i]},${ys[i]}`
  return d
}

function yScale(values: number[], height: number, opts?: { includeZero?: boolean; fixed?: [number, number] }) {
  if (opts?.fixed) {
    const [min, max] = opts.fixed
    return { min, max, y: (v: number) => height * (1 - (v - min) / (max - min)) }
  }
  let lo = Math.min(...values)
  let hi = Math.max(...values)
  if (opts?.includeZero) {
    lo = Math.min(lo, 0)
    hi = Math.max(hi, 0)
  }
  const pad = (hi - lo) * 0.1 || 0.5
  const min = lo - pad
  const max = hi + pad
  return { min, max, y: (v: number) => height * (1 - (v - min) / (max - min)) }
}

function DriverBadge({ driver, color, dashed }: { driver: QualiTraceDriver; color: string; dashed: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <svg width="20" height="8" aria-hidden="true">
        <line
          x1={0}
          x2={20}
          y1={4}
          y2={4}
          stroke={color}
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeDasharray={dashed ? '4 3' : undefined}
        />
      </svg>
      <div>
        <p className="font-display text-sm font-semibold text-ink">{driverName(driver.driver)}</p>
        <p className="text-xs text-muted">
          {driver.constructor ?? 'Unknown team'}
          {driver.lap_time_s != null ? ` · ${driver.lap_time_s.toFixed(3)}s` : ''}
        </p>
      </div>
    </div>
  )
}

export function FightToPoleChart({ data }: { data: QualiTraceData }) {
  const reduce = useReducedMotion()
  const svgRef = useRef<SVGSVGElement>(null)
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)

  const [p1, p2] = data.drivers
  if (!p1 || !p2 || data.grid_m.length === 0) {
    return <p className="text-sm text-muted">Not enough qualifying laps yet.</p>
  }

  const p1Color = resolveTeamColor(p1.constructor)
  const p2Color = resolveTeamColor(p2.constructor)
  // Keyed off the resolved colors, not the raw constructor strings: two drivers with missing
  // team data both fall back to the same muted color and need the same disambiguation a real
  // same-team pair does.
  const sameTeam = p1Color === p2Color

  const maxDist = data.grid_m[data.grid_m.length - 1] || 1
  const x = (m: number) => (m / maxDist) * INNER_W
  const xs = data.grid_m.map(x)

  // Corner numbers collide at tight, technical circuits (Monaco's chicane sequences pack several
  // corners within a few meters of each other) -- skip a label when it would land within 16px of
  // the last one shown. The dotted line still marks every corner; only the number thins out.
  const MIN_LABEL_GAP_PX = 16
  const labeledCorners = new Set<number>()
  let lastLabelX = -Infinity
  for (const c of data.corners) {
    const cx = x(c.distance_m)
    if (cx - lastLabelX >= MIN_LABEL_GAP_PX) {
      labeledCorners.add(c.number)
      lastLabelX = cx
    }
  }

  const speed = yScale([...p1.speed_kmh, ...p2.speed_kmh], PANEL_H)
  const delta = yScale([...p1.delta_s, ...p2.delta_s], PANEL_H, { includeZero: true })
  const throttle = yScale([], PANEL_H, { fixed: [0, 100] })

  const panels = [
    { key: 'speed', label: 'Top speed (km/h)', offset: 0, scale: speed, p1: p1.speed_kmh, p2: p2.speed_kmh },
    { key: 'delta', label: 'Delta to pole (s)', offset: PANEL_H + PANEL_GAP, scale: delta, p1: p1.delta_s, p2: p2.delta_s },
    { key: 'throttle', label: 'Throttle (%)', offset: 2 * (PANEL_H + PANEL_GAP), scale: throttle, p1: p1.throttle_pct, p2: p2.throttle_pct },
  ]

  function handleMove(e: MouseEvent<SVGRectElement>) {
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    const scale = WIDTH / rect.width
    const xSvg = (e.clientX - rect.left) * scale - MARGIN.left
    const frac = Math.min(1, Math.max(0, xSvg / INNER_W))
    setHoveredIndex(Math.round(frac * (data.grid_m.length - 1)))
  }

  return (
    <div className="glass w-full rounded-[--radius-panel] p-5">
      <h2 className="font-display text-[2.025rem] font-semibold tracking-tight sm:text-[2.7rem]">The fight to pole</h2>
      <div className="mt-4 flex flex-wrap gap-8">
        <DriverBadge driver={p1} color={p1Color} dashed={false} />
        <DriverBadge driver={p2} color={p2Color} dashed={sameTeam} />
      </div>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="mt-5 w-full max-w-full"
        role="img"
        aria-label={`Fight to pole: ${driverName(p1.driver)} vs ${driverName(p2.driver)}`}
      >
        <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
          {panels.map((panel) => (
            <g key={panel.key} transform={`translate(0,${panel.offset})`}>
              <text x={0} y={-22} fill="var(--color-muted)" fontSize={12}>
                {panel.label}
              </text>
              {panel.key === 'delta' && (
                <line
                  x1={0}
                  x2={INNER_W}
                  y1={panel.scale.y(0)}
                  y2={panel.scale.y(0)}
                  stroke="var(--color-border)"
                  strokeDasharray="4 4"
                />
              )}
              {data.corners.map((c) => (
                <g key={c.number}>
                  <line
                    x1={x(c.distance_m)}
                    x2={x(c.distance_m)}
                    y1={0}
                    y2={PANEL_H}
                    stroke="var(--color-border)"
                    strokeDasharray="2 3"
                  />
                  {panel.key === 'speed' && labeledCorners.has(c.number) && (
                    <text x={x(c.distance_m)} y={-8} textAnchor="middle" fontSize={10} fill="var(--color-muted)">
                      {c.number}
                    </text>
                  )}
                </g>
              ))}

              <m.path
                fill="none"
                stroke={p1Color}
                strokeWidth={2.5}
                strokeLinecap="round"
                strokeLinejoin="round"
                initial={reduce ? false : { pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 1 }}
                transition={reduce ? { duration: 0 } : drawTransition}
                d={linePath(xs, panel.p1.map(panel.scale.y))}
              />
              <m.path
                fill="none"
                stroke={p2Color}
                strokeWidth={2.5}
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeDasharray={sameTeam ? '6 4' : undefined}
                initial={reduce ? false : { pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 1 }}
                transition={reduce ? { duration: 0 } : drawTransition}
                d={linePath(xs, panel.p2.map(panel.scale.y))}
              />
            </g>
          ))}

          {hoveredIndex != null && (
            <line x1={xs[hoveredIndex]} x2={xs[hoveredIndex]} y1={0} y2={PANELS_H} stroke="var(--color-ink)" strokeWidth={1} />
          )}

          {/* Full-size transparent catcher for continuous scrub, spanning all three panels. */}
          <rect
            x={0}
            y={0}
            width={INNER_W}
            height={PANELS_H}
            fill="transparent"
            onMouseMove={handleMove}
            onMouseLeave={() => setHoveredIndex(null)}
          />

          {hoveredIndex != null && (
            <foreignObject
              x={Math.min(INNER_W - 210, Math.max(0, xs[hoveredIndex] + 12))}
              y={0}
              width={210}
              height={130}
              className="pointer-events-none"
            >
              <div className="glass rounded-xl px-3 py-2 text-xs text-ink">
                <div className="text-muted">{Math.round(data.grid_m[hoveredIndex])}m</div>
                {[{ d: p1, color: p1Color, dashed: false }, { d: p2, color: p2Color, dashed: sameTeam }].map(
                  ({ d: drv, color, dashed }) => (
                    <div key={drv.driver} className="mt-1.5 flex items-center gap-2">
                      <svg width="14" height="6" aria-hidden="true">
                        <line x1={0} x2={14} y1={3} y2={3} stroke={color} strokeWidth={2} strokeDasharray={dashed ? '3 2' : undefined} />
                      </svg>
                      <div className="leading-tight">
                        <span className="num font-semibold text-ink">{drv.speed_kmh[hoveredIndex]?.toFixed(0)} km/h</span>
                        <span className="ml-2 num text-muted">{drv.delta_s[hoveredIndex] >= 0 ? '+' : ''}{drv.delta_s[hoveredIndex]?.toFixed(3)}s</span>
                        <span className="ml-2 num text-muted">{drv.throttle_pct[hoveredIndex]?.toFixed(0)}%</span>
                      </div>
                    </div>
                  )
                )}
              </div>
            </foreignObject>
          )}
        </g>
      </svg>

      <p className="mt-4 text-xs text-muted">
        Distance-aligned telemetry from each driver's fastest qualifying lap; dotted lines mark
        turn numbers. Delta is the time gap to the pole lap at the same point on track. Move over
        the chart to scrub through the lap.
      </p>
    </div>
  )
}
