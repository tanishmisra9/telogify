import { useRef, useState } from 'react'
import { m, useReducedMotion } from 'framer-motion'
import { Car, CarDefs, CAR_W, useCarId } from '@/components/CarGlyph'
import { FollowTip } from '@/components/FollowTip'
import { LadderStrip } from '@/components/LadderStrip'
import { driverName } from '@/lib/drivers'
import { labelSide, layoutBands, rowHeight, scaleLinear, STRIP_H, textWidth } from '@/lib/ladder'
import { formatLap, formatTick, timeAxis } from '@/lib/qualiSegments'
import { resolveTeamColor } from '@/lib/teamColors'
import { useCanHover } from '@/lib/useCanHover'
import { useContainerWidth } from '@/lib/useContainerWidth'
import { useFollowTip } from '@/lib/useFollowTip'
import type { QualiSegmentRow, QualiSegmentsData } from '@/lib/api'

const PAD = 16
const AXIS_H = 26
// Text is placed on ONE alphabetic baseline (cy + 4.5 for 13px type) rather than `dominant-baseline: central`: a smaller
// figure tspan under `central` rides ~6px above its name. Shared baseline = name and figure always line up.
const BASELINE = 4.5
const HALO = { paintOrder: 'stroke', stroke: 'var(--color-surface)', strokeWidth: 4, strokeLinejoin: 'round' } as const

// Qualifying as a ladder: one band per segment (Q3 on top), every car that ENTERED the segment placed at its best lap
// in it on ONE shared time axis, so a car is comparable across bands. The nose of each car is its time. The red line is
// the slowest time that went through to the next segment, computed by the API. A band collapses to its header.
export function QualiSegmentsChart({ data, sprint = false }: { data: QualiSegmentsData; sprint?: boolean }) {
  const reduce = useReducedMotion()
  const ref = useRef<HTMLDivElement>(null)
  const width = useContainerWidth(ref)
  const { at, setAt, handlers, pointer } = useFollowTip()
  const carId = useCarId()
  const ROW_H = rowHeight(useCanHover()) // taller rows for a finger
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  const segs = data.segments
  const times = segs.flatMap((s) => s.rows.map((r) => r.time_s).filter((t): t is number => t != null))
  const axis = timeAxis(times)
  if (!axis || segs.length === 0) return null

  const toggle = (name: string) => {
    setAt(null) // the rows under an open readout are about to move
    setCollapsed((cur) => {
      const next = new Set(cur)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const x1 = width - PAD
  const xOf = scaleLinear(axis.min, axis.max, PAD, x1 - CAR_W)
  const { bands, height: stackH } = layoutBands(segs.map((s) => (collapsed.has(s.name) ? 0 : s.rows.length)), AXIS_H, undefined, ROW_H)
  const height = stackH + 6

  const tipFor = (segName: string, r: QualiSegmentRow, cut: number | null) => {
    const lines: string[] = []
    lines.push(r.time_s != null ? `${segName}: ${formatLap(r.time_s)}` : `${segName}: no time set`)
    if (r.gap_to_fastest_s != null && r.gap_to_fastest_s > 0) lines.push(`+${r.gap_to_fastest_s.toFixed(3)}s to the fastest`)
    if (r.gap_to_cut_s != null && cut != null) {
      lines.push(r.gap_to_cut_s <= 0 ? `${Math.abs(r.gap_to_cut_s).toFixed(3)}s inside the cutoff` : `${r.gap_to_cut_s.toFixed(3)}s outside the cutoff`)
    }
    if (r.position != null) lines.push(`Classified P${r.position}`)
    return { title: `${driverName(r.driver)}${r.constructor ? `, ${r.constructor}` : ''}`, lines }
  }
  let tip: { title: string; lines: string[] } | null = null
  for (const s of segs) for (const r of s.rows) if (`${s.name}:${r.driver}` === at?.key) tip = tipFor(s.name, r, s.cut_s)

  const title = sprint ? 'Sprint qualifying results' : 'Qualifying results'
  const first = segs[segs.length - 1].name

  return (
    <m.div
      className="glass w-full rounded-panel p-5"
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 120, damping: 20 }}
    >
      <h2 className="mb-4 font-display text-[2.025rem] font-semibold tracking-tight sm:text-[2.7rem]">{title}</h2>

      <FollowTip at={at} tip={tip} pointer={pointer} container={ref} />
      <div ref={ref} className="relative">
        {width > 0 && (
          <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="block select-none" role="group" aria-label={`${title} by segment`}>
            <CarDefs id={carId} />
            {axis.ticks.map((t) => (
              <g key={t} aria-hidden>
                <line x1={xOf(t)} x2={xOf(t)} y1={AXIS_H - 4} y2={height - 6} stroke="var(--color-border)" strokeDasharray="4 4" />
                <text x={xOf(t)} y={AXIS_H - 10} textAnchor="middle" fill="var(--color-muted)" fontSize={12} className="num">
                  {formatTick(t, axis.step)}
                </text>
              </g>
            ))}

            {segs.map((seg, si) => {
              const b = bands[si]
              const open = !collapsed.has(seg.name)
              const cutX = open && seg.cut_s != null ? xOf(seg.cut_s) : null
              const tagEnd = cutX != null && cutX > width - 150
              return (
                <g key={seg.name}>
                  <LadderStrip top={b.top} x0={PAD} x1={x1} name={seg.name} count={`${seg.rows.length} cars`} open={open} onToggle={() => toggle(seg.name)} />
                  {cutX != null && (
                    <>
                      <line x1={cutX} x2={cutX} y1={b.top + STRIP_H - 18} y2={b.top + b.height} stroke="var(--color-accent)" strokeWidth={2} />
                      <text
                        x={cutX + (tagEnd ? -5 : 5)} y={b.top + STRIP_H - 9} textAnchor={tagEnd ? 'end' : 'start'}
                        fill="var(--color-accent)" fontSize={12} fontWeight={600} className="num" style={HALO}
                      >
                        Cutoff {formatLap(seg.cut_s as number)}
                      </text>
                    </>
                  )}

                  {open && seg.rows.map((r, i) => {
                    const key = `${seg.name}:${r.driver}`
                    const cy = b.rowsTop + i * ROW_H + ROW_H / 2
                    const name = r.driver // the three-letter code on the graphic; the readout carries the full name
                    const noTime = r.time_s == null
                    // Every car that went out shows its gap to the cutoff line (red) instead of its time: how narrowly it missed is the story.
                    const isOut = r.advanced === false && r.gap_to_cut_s != null
                    // Out (knocked out, or no time) rows get a light red wash across the row; hover deepens whichever wash it is.
                    const bad = noTime || isOut
                    const catcher = (
                      <rect
                        x={PAD - 6} y={cy - ROW_H / 2} width={x1 - PAD + 12} height={ROW_H}
                        fill={bad ? 'var(--color-accent)' : 'var(--color-ink)'} fillOpacity={at?.key === key ? (bad ? 0.2 : 0.07) : bad ? 0.09 : 0}
                      />
                    )
                    // No time: no car, no position on the axis. Name and "No time" sit at the right edge, on the same baseline.
                    if (noTime) {
                      return (
                        <g key={key} {...handlers(key)}>
                          {catcher}
                          <text data-row={key} x={x1} y={cy + BASELINE} textAnchor="end" fill="var(--color-ink)" fontSize={13} fontWeight={500}>
                            {name}
                            <tspan dx={8} fill="var(--color-muted)" fontSize={12} className="num">No time</tspan>
                          </text>
                        </g>
                      )
                    }
                    const x = xOf(r.time_s as number)
                    const figure = isOut ? `+${(r.gap_to_cut_s as number).toFixed(3)}` : formatLap(r.time_s as number)
                    const side = labelSide(x, CAR_W, textWidth(name.length + figure.length + 1), width, PAD)
                    return (
                      <g key={key} {...handlers(key)}>
                        {catcher}
                        <g data-row={key}>
                        <Car id={carId} x={x} y={cy} color={resolveTeamColor(r.constructor)} />
                        <text
                          x={side === 'right' ? x + CAR_W + 6 : x - 6} y={cy + BASELINE} textAnchor={side === 'right' ? 'start' : 'end'}
                          fill="var(--color-ink)" fontSize={13} fontWeight={500} style={HALO}
                        >
                          {name}
                          {figure && (
                            <tspan dx={6} fill={isOut ? 'var(--color-accent)' : 'var(--color-muted)'} fontSize={12} fontWeight={isOut ? 700 : 400} className="num">
                              {figure}
                            </tspan>
                          )}
                        </text>
                        </g>
                      </g>
                    )
                  })}
                </g>
              )
            })}
          </svg>
        )}
        {/* The ladder is a picture of a table: this is the table, for screen readers. */}
        <div className="sr-only">
          {segs.map((seg) => (
            <section key={seg.name}>
              <h3>{seg.name}{seg.cut_s != null ? `, cutoff at ${formatLap(seg.cut_s)}` : ''}</h3>
              <ol>
                {seg.rows.map((r) => (
                  <li key={r.driver}>
                    {driverName(r.driver)}, {r.time_s != null ? formatLap(r.time_s) : 'no time'}
                    {r.advanced != null ? (r.advanced ? ', advanced' : ', eliminated') : ''}
                  </li>
                ))}
              </ol>
            </section>
          ))}
        </div>
      </div>

      <p className="mt-4 text-sm text-muted">
        Each car sits at its best lap in that segment, on one shared time axis; the nose is the time and faster is to the
        left. The red cutoff line is the slowest time that went through, so a nose left of it advanced; a car that went out shows
        its gap to that line, in red, instead of its time. Who entered a segment follows the official classification, and a car
        that set no time is listed at the right without a position. {first} lists every car that ran. Click a segment
        title to fold it.
      </p>
    </m.div>
  )
}
