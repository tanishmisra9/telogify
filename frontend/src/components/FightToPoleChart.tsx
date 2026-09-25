import { useId, useState, type MouseEvent } from 'react'
import { AnimatePresence, m, useReducedMotion } from 'framer-motion'
import { ChartTabs } from '@/components/ChartTabs'
import { CornerDataNote } from '@/components/CornerDataNote'
import { TeamRule } from '@/components/TeamMark'
import { driverName } from '@/lib/drivers'
import {
  MAX_PICKED,
  pickerRows,
  resolveSelection,
  sameSet,
  surname,
  teamOptions,
  toggleDriver,
  type PickerRow,
  type TeamOption,
} from '@/lib/qualiPair'
import { resolveTeamColor, teamColorWithAlpha, teammateShade } from '@/lib/teamColors'
import { drawTransition, expandTransition } from '@/lib/motion'
import { useSvgTextScale } from '@/lib/useSvgTextScale'
import type { QualiTraceCorner, QualiTraceData, QualiTraceDriver } from '@/lib/api'

const WIDTH = 1100
const PANEL_H = 150
const GAP_AFTER_SPEED = 68
const GAP_AFTER_DELTA = 40
const MARGIN = { top: 50, right: 56, bottom: 28, left: 56 }
const INNER_W = WIDTH - MARGIN.left - MARGIN.right
const PANELS_H = PANEL_H * 3 + GAP_AFTER_SPEED + GAP_AFTER_DELTA
const HEIGHT = MARGIN.top + PANELS_H + MARGIN.bottom

// Plain point-to-point path, not lib/svgPath's smoothPath (Catmull-Rom) -- that's tuned for
// sparse, hand-picked points (round-by-round trend lines) and would overshoot on dense,
// already-smooth telemetry samples like these.
function linePath(xs: number[], ys: number[]): string {
  if (xs.length === 0) return ''
  let d = `M ${xs[0]},${ys[0]}`
  for (let i = 1; i < xs.length; i++) d += ` L ${xs[i]},${ys[i]}`
  return d
}

function yScale(
  values: number[],
  height: number,
  opts?: { includeZero?: boolean; fixed?: [number, number]; extraTopPad?: number },
) {
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
  const max = hi + pad + (opts?.extraTopPad ?? 0)
  return { min, max, y: (v: number) => height * (1 - (v - min) / (max - min)) }
}

const ROW = 'grid min-h-11 w-full grid-cols-[1.75rem_minmax(0,1fr)_auto] items-center gap-x-2 px-2 py-1 text-sm'
// Enabled rows get the pointer + hover ring; a row that can't be picked (two already chosen, or no
// usable lap) is greyed and inert so it never looks tappable.
const ROW_BTN = `${ROW} border-[0.75px] border-ink/20 text-left shadow-[inset_0_0_0_1.5px_transparent] transition-[opacity,box-shadow] duration-150 enabled:cursor-pointer enabled:hover:shadow-[inset_0_0_0_1.5px_var(--color-ink)] disabled:cursor-default disabled:opacity-40`

const fmt = (t: number | null) => (t != null ? `${t.toFixed(3)}s` : null)

// The whole qualifying order. Click to add a driver (two at most); once two are chosen every other
// row greys out until one is unclicked. A driver with no plottable lap stays in place, greyed, with
// the reason in the row. Selected rows carry their actual line color (the shaded one for a
// teammate), so the grid doubles as the chart's legend.
function DriverGrid({
  rows,
  selected,
  colors,
  onToggle,
}: {
  rows: PickerRow[]
  selected: string[]
  colors: Record<string, string>
  onToggle: (driver: string) => void
}) {
  const full = selected.length >= MAX_PICKED
  return (
    <ol className="mt-2 grid grid-flow-col grid-rows-8 lg:grid-rows-6">
      {rows.map((r) => {
        const on = selected.includes(r.driver)
        const time = fmt(r.time_s)
        const pos = <span className="num text-xs text-muted">{r.position ?? '-'}</span>
        const mark = (
          <span className="inline-flex min-w-0 items-center gap-2">
            {on ? (
              <span aria-hidden className="h-[3px] w-4 shrink-0 rounded-[2px]" style={{ backgroundColor: colors[r.driver] }} />
            ) : (
              <TeamRule team={r.constructor} />
            )}
            <span className={`truncate ${on ? 'font-semibold' : 'font-medium'}`}>{surname(r.driver)}</span>
          </span>
        )
        if (!r.plottable) {
          return (
            <li key={r.driver}>
              <div className={`${ROW} opacity-40`}>
                {pos}
                {mark}
                <span className="num text-xs text-muted">{time ? `${time} no trace` : 'no time'}</span>
              </div>
            </li>
          )
        }
        return (
          <li key={r.driver}>
            <button
              type="button"
              onClick={() => onToggle(r.driver)}
              disabled={full && !on}
              aria-pressed={on}
              aria-label={`${r.position != null ? `P${r.position} ` : ''}${driverName(r.driver)}${time ? `, ${time}` : ''}${on ? ', selected, select again to remove' : full ? ', remove a driver to choose another' : ', compare'}`}
              className={ROW_BTN}
              style={{ backgroundColor: teamColorWithAlpha(r.constructor, on ? 0.2 : 0.09) }}
            >
              {pos}
              {mark}
              <span className="num text-xs text-ink">{time}</span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}

// One row per team: pick it to compare its two drivers. Radio-like: another team switches
// straight over, the selected team clears. A team without two plottable drivers is greyed and says
// which driver is why.
function TeamGrid({
  options,
  selected,
  onPick,
}: {
  options: TeamOption[]
  selected: string[]
  onPick: (option: TeamOption) => void
}) {
  return (
    <ol className="mt-2 grid grid-flow-col grid-rows-6">
      {options.map((o) => {
        const on = o.blocked == null && sameSet(selected, o.codes)
        return (
          <li key={o.team}>
            <button
              type="button"
              onClick={() => onPick(o)}
              disabled={o.blocked != null}
              aria-pressed={on}
              aria-label={`${o.team}${o.blocked ? `, ${o.blocked}, cannot compare` : on ? ', selected, select again to clear' : ', compare teammates'}`}
              className={ROW_BTN}
              style={{ backgroundColor: teamColorWithAlpha(o.team, on ? 0.2 : 0.09) }}
            >
              <span className="num text-xs text-muted">{o.bestPosition ?? '-'}</span>
              <span className="inline-flex min-w-0 items-center gap-2">
                <TeamRule team={o.team} />
                <span className={`truncate ${on ? 'font-semibold' : 'font-medium'}`}>{o.team}</span>
              </span>
              <span className="num text-xs text-muted">{o.blocked}</span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={`shrink-0 transition-transform duration-200 motion-reduce:transition-none ${open ? 'rotate-180' : ''}`}
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  )
}

export function FightToPoleChart({ data, sprint = false }: { data: QualiTraceData; sprint?: boolean }) {
  const reduce = useReducedMotion()
  const { ref: svgRef, textPx } = useSvgTextScale(WIDTH)
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)
  // SVG-space y of the cursor, so the readout follows the mouse instead of sitting pinned to
  // the top of the chart.
  const [hoveredY, setHoveredY] = useState(0)
  const [unit, setUnit] = useState<'kmh' | 'mph'>('kmh')
  // null = untouched (the default pair); an array, even an empty one, is the reader's own pick.
  const [picked, setPicked] = useState<string[] | null>(null)
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<'drivers' | 'teams'>('drivers')
  const panelId = useId()

  const title = sprint ? 'The fight to sprint pole' : 'The fight to pole'
  const lapLabel = sprint ? 'sprint qualifying laps' : 'qualifying laps'

  const [first, second] = data.drivers
  if (!first || !second || data.grid_m.length === 0) {
    return <p className="text-sm text-muted">Not enough {lapLabel} yet.</p>
  }

  // Default is the top two plottable laps (P1/P2, or the next two when pole's telemetry was
  // scrubbed); Reset returns to it. The chart draws exactly the selected drivers, even one or none.
  const defaultCodes = [first.driver, second.driver]
  const selected = resolveSelection(picked, data.drivers.map((d) => d.driver), defaultCodes)
  // Fastest lap first: that lap is the delta reference, as in the stock P1/P2 chart.
  const shown = data.drivers
    .filter((d) => selected.includes(d.driver))
    .sort((a, b) => (a.lap_time_s ?? Infinity) - (b.lap_time_s ?? Infinity))
  const ref = shown[0] as QualiTraceDriver | undefined

  // Teammates: the same hue twice is unreadable, so the slower lap takes a dramatically
  // ink-shifted shade of the team color. Keyed off the resolved colors, not the raw constructor
  // strings: two drivers with missing team data both fall back to the same muted color and need
  // the same disambiguation a real same-team pair does.
  const colors: Record<string, string> = {}
  shown.forEach((d, i) => {
    const base = resolveTeamColor(d.constructor)
    colors[d.driver] = i > 0 && base === resolveTeamColor(shown[0].constructor) ? teammateShade(d.constructor) : base
  })

  // Stored delta_s is measured against one shared reference lap; every series sits on the same
  // fraction-aligned grid, so its difference from the fastest selected lap is exact (and the finish
  // point is the true lap-time gap). The fastest lap is the zero line.
  const deltas = ref ? shown.map((d) => d.delta_s.map((v, i) => v - ref.delta_s[i])) : []

  // The official pole sitter's lap telemetry was scrubbed (e.g. a corrupted distance channel), so
  // they're absent from the chart entirely. Say so.
  const poleMissing = data.pole_driver != null && !data.drivers.some((d) => d.driver === data.pole_driver)
  const refIsPole = ref != null && ref.driver === data.pole_driver
  const refLap = !ref
    ? 'the fastest selected lap'
    : refIsPole
      ? sprint ? 'the sprint pole lap' : 'the pole lap'
      : `${driverName(ref.driver)}'s lap`

  const rows = pickerRows(data.drivers, data.unavailable ?? [])
  const teams = teamOptions(rows)
  const isDefault = sameSet(selected, defaultCodes)
  // Left out of the comparison: told apart by whether they set a time (a real lap whose
  // telemetry wasn't usable) or not. Pole is named once, in the pole note, when that already
  // says it.
  const list = (codes: string[]) => new Intl.ListFormat('en', { type: 'conjunction' }).format(codes.map(driverName))
  const skipped = (data.unavailable ?? []).filter((u) => !(poleMissing && u.driver === data.pole_driver))
  const noTrace = skipped.filter((u) => u.best_lap_s != null).map((u) => u.driver)
  const noTime = skipped.filter((u) => u.best_lap_s == null).map((u) => u.driver)

  // Chart geometry stays in km/h regardless of unit (a linear conversion doesn't change the
  // curve's shape); only the displayed numbers convert.
  const toDisplay = (v: number) => (unit === 'mph' ? v * 0.621371 : v)
  const unitLabel = unit === 'mph' ? 'mph' : 'km/h'

  const maxDist = data.grid_m[data.grid_m.length - 1] || 1
  const x = (m: number) => (m / maxDist) * INNER_W
  const xs = data.grid_m.map(x)

  // Corner numbers collide at tight, technical circuits (Monaco's chicane sequences pack several
  // corners within a few meters of each other) -- skip a label when it would land within 16px of
  // the last one shown. The dotted line still marks every corner; only the number thins out.
  const MIN_LABEL_GAP_PX = 16
  // Keyed by number+letter, not number alone: chicane/hairpin sub-apexes share a number (e.g.
  // "1" and "1A"), and a number-only key made every corner with that number render whichever
  // label first passed the gap check, duplicating it at each corner's own position.
  // `?? ''`: rows ingested before `letter` was added to corners_json won't have the key.
  const cornerLabel = (c: QualiTraceCorner) => `${c.number}${c.letter ?? ''}`
  const labeledCorners = new Set<string>()
  let lastLabelX = -Infinity
  for (const c of data.corners) {
    const cx = x(c.distance_m)
    if (cx - lastLabelX >= MIN_LABEL_GAP_PX) {
      labeledCorners.add(cornerLabel(c))
      lastLabelX = cx
    }
  }

  // Extra headroom above the fastest speed so the curve's peak doesn't crowd the corner
  // numbers drawn just above it. With nothing selected the axes still frame the default pair, so
  // the chart holds its shape instead of collapsing.
  const framing = shown.length > 0 ? shown : data.drivers.slice(0, MAX_PICKED)
  const speed = yScale(framing.flatMap((d) => d.speed_kmh), PANEL_H, { extraTopPad: 20 })
  const delta = yScale(deltas.flat(), PANEL_H, { includeZero: true })
  const throttle = yScale([], PANEL_H, { fixed: [0, 100] })

  // Per panel, one series per shown driver (same order as `shown`).
  const panels = [
    { key: 'speed', label: `Top speed (${unitLabel})`, offset: 0, scale: speed, series: shown.map((d) => d.speed_kmh) },
    { key: 'delta', label: 'Delta (s)', offset: PANEL_H + GAP_AFTER_SPEED, scale: delta, series: deltas },
    {
      key: 'throttle',
      label: 'Throttle (%)',
      offset: PANEL_H + GAP_AFTER_SPEED + PANEL_H + GAP_AFTER_DELTA,
      scale: throttle,
      series: shown.map((d) => d.throttle_pct),
    },
  ]

  function handleMove(e: MouseEvent<SVGRectElement>) {
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    // One scale factor serves both axes: the viewBox aspect ratio is preserved.
    const scale = WIDTH / rect.width
    const xSvg = (e.clientX - rect.left) * scale - MARGIN.left
    const frac = Math.min(1, Math.max(0, xSvg / INNER_W))
    setHoveredIndex(Math.round(frac * (data.grid_m.length - 1)))
    setHoveredY((e.clientY - rect.top) * scale - MARGIN.top)
  }

  return (
    <div className="glass w-full select-none rounded-panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-[2.025rem] font-semibold tracking-tight sm:text-[2.7rem]">{title}</h2>
        <ChartTabs
          ariaLabel="Speed unit"
          active={unit}
          onChange={setUnit}
          tabs={[
            { value: 'kmh', label: 'KM/H', hint: 'kilometres per hour' },
            { value: 'mph', label: 'MPH', hint: 'miles per hour' },
          ]}
        />
      </div>

      {poleMissing && (
        <p className="mt-2 text-xs text-muted">
          {driverName(data.pole_driver as string)} took {sprint ? 'sprint pole' : 'pole'}
          {data.pole_lap_time_s != null ? ` in ${data.pole_lap_time_s.toFixed(3)}s` : ''}. Telemetry
          for that lap isn&apos;t usable here, so the comparison starts from the next two.
        </p>
      )}

      <div className="mt-5 border-y border-border">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            aria-controls={open ? panelId : undefined}
            className="flex min-h-11 min-w-0 flex-1 cursor-pointer items-center gap-4 text-left"
          >
            <span className="flex min-w-0 flex-wrap items-center gap-x-2 text-sm">
              {shown.length === 0 && <span className="text-muted">None selected</span>}
              {shown.map((d, i) => (
                <span key={d.driver} className="inline-flex items-center gap-2">
                  {i > 0 && <span className="text-muted">vs</span>}
                  <span aria-hidden className="h-[3px] w-4 shrink-0 rounded-[2px]" style={{ backgroundColor: colors[d.driver] }} />
                  <span className="font-semibold">{surname(d.driver)}</span>
                  {d.lap_time_s != null && <span className="num text-xs text-muted">{d.lap_time_s.toFixed(3)}s</span>}
                </span>
              ))}
            </span>
            <span className="ml-auto inline-flex items-center text-muted">
              <span className="sr-only">{open ? 'Close driver picker' : 'Change drivers'}</span>
              <Chevron open={open} />
            </span>
          </button>
          <button
            type="button"
            onClick={() => setPicked(null)}
            disabled={isDefault}
            className="inline-flex min-h-11 shrink-0 items-center border-b-2 border-transparent font-display text-base font-medium tracking-tight text-muted transition-colors enabled:cursor-pointer enabled:hover:border-ink enabled:hover:text-ink disabled:opacity-40"
          >
            Reset
          </button>
        </div>
        <AnimatePresence initial={false}>
          {open && (
            <m.div
              id={panelId}
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={reduce ? { duration: 0 } : expandTransition}
              className="overflow-hidden"
            >
              <div className="pb-4 pt-1">
                <div className="flex flex-wrap items-center gap-x-6">
                  <ChartTabs
                    ariaLabel="Pick by"
                    active={mode}
                    onChange={setMode}
                    tabs={[
                      { value: 'drivers', label: 'Drivers' },
                      { value: 'teams', label: 'Teams' },
                    ]}
                  />
                  <p className="text-xs text-muted">
                    {mode === 'drivers'
                      ? 'Pick up to two drivers. Click a selected driver to remove them.'
                      : 'Pick a team to compare its two drivers. Click it again to clear.'}
                  </p>
                </div>
                {mode === 'drivers' ? (
                  <DriverGrid rows={rows} selected={selected} colors={colors} onToggle={(d) => setPicked(toggleDriver(selected, d))} />
                ) : (
                  <TeamGrid options={teams} selected={selected} onPick={(o) => setPicked(sameSet(selected, o.codes) ? [] : o.codes)} />
                )}
              </div>
            </m.div>
          )}
        </AnimatePresence>
      </div>

      {(noTrace.length > 0 || noTime.length > 0) && (
        <p className="mt-2 text-xs text-muted">
          {noTrace.length > 0 &&
            `No usable telemetry for the fastest ${sprint ? 'sprint qualifying' : 'qualifying'} ${noTrace.length > 1 ? 'laps' : 'lap'} of ${list(noTrace)}, so ${noTrace.length > 1 ? 'they are' : 'it is'} left out instead of guessed. `}
          {noTime.length > 0 && `${list(noTime)} set no time.`}
        </p>
      )}

      <div className="relative mt-5">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full max-w-full"
        role="img"
        aria-label={`${title}: ${shown.length > 0 ? shown.map((d) => driverName(d.driver)).join(' vs ') : 'no drivers selected'}`}
      >
        <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
          {panels.map((panel) => (
            <g key={panel.key} transform={`translate(0,${panel.offset})`}>
              <text x={0} y={-22} fill="var(--color-muted)" fontSize={textPx(15)}>
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
                <g key={cornerLabel(c)}>
                  <line
                    x1={x(c.distance_m)}
                    x2={x(c.distance_m)}
                    y1={0}
                    y2={PANEL_H}
                    stroke="var(--color-border)"
                    strokeDasharray="2 3"
                  />
                  {panel.key === 'speed' && labeledCorners.has(cornerLabel(c)) && (
                    <text x={x(c.distance_m)} y={-8} textAnchor="middle" fontSize={textPx(13)} fill="var(--color-muted)">
                      {cornerLabel(c)}
                    </text>
                  )}
                </g>
              ))}

              {panel.series.map((values, i) => (
                <m.path
                  key={`${panel.key}-${shown[i].driver}`}
                  fill="none"
                  stroke={colors[shown[i].driver]}
                  strokeWidth={2.5}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  initial={reduce ? false : { pathLength: 0, opacity: 0 }}
                  animate={{ pathLength: 1, opacity: 1 }}
                  transition={reduce ? { duration: 0 } : drawTransition}
                  d={linePath(xs, values.map(panel.scale.y))}
                />
              ))}
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

          {hoveredIndex != null && shown.length > 0 && (
            <foreignObject
              x={Math.min(INNER_W - 210, Math.max(0, xs[hoveredIndex] + 12))}
              // To the right of the cursor, vertically centered on it (clamped inside the
              // panels) rather than sitting pinned to the top of the chart.
              y={Math.min(PANELS_H - 130, Math.max(0, hoveredY - 40))}
              width={210}
              height={130}
              className="pointer-events-none"
            >
              <div className="glass rounded-xl px-3 py-2 text-xs text-ink">
                <div className="text-muted">{Math.round(data.grid_m[hoveredIndex])}m</div>
                {shown.map((drv, i) => ({ drv, color: colors[drv.driver], dl: deltas[i], isRef: i === 0 })).map(({ drv, color, dl, isRef }) => (
                  <div key={drv.driver} className="mt-1.5 flex items-center gap-2">
                    <svg width="14" height="6" aria-hidden="true">
                      <line x1={0} x2={14} y1={3} y2={3} stroke={color} strokeWidth={2} />
                    </svg>
                    <div className="leading-tight">
                      <span className="num font-semibold text-ink">{toDisplay(drv.speed_kmh[hoveredIndex]).toFixed(0)} {unitLabel}</span>
                      {/* The reference lap is the zero line by definition, so its own delta is left off. */}
                      {!isRef && <span className="ml-2 num text-muted">{dl[hoveredIndex] >= 0 ? '+' : ''}{dl[hoveredIndex].toFixed(3)}s</span>}
                      <span className="ml-2 num text-muted">{drv.throttle_pct[hoveredIndex].toFixed(0)}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </foreignObject>
          )}
        </g>
      </svg>
      {shown.length === 0 && (
        <p className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-muted">
          Pick a driver to see their lap.
        </p>
      )}
      </div>

      {data.corners.length === 0 && <CornerDataNote />}

      <p className="mt-4 text-sm text-muted">
        Telemetry from each driver's fastest {sprint ? 'sprint qualifying' : 'qualifying'} lap,
        aligned by position on track; dotted lines mark turn numbers. Delta is the running time
        gap to {refLap}:
        below the line means ahead at that point, above means behind, and where it ends is the
        final gap. Throttle is how much of full power the driver is asking for: 100% is flat
        out, and every dip is a braking zone or a corner taken partly lifted. Move over the
        chart to scrub through the lap.
      </p>
    </div>
  )
}
