import { useRef, useState } from 'react'
import { m, useReducedMotion } from 'framer-motion'
import { Car, CarDefs, CAR_W, useCarId } from '@/components/CarGlyph'
import { ChartTabs } from '@/components/ChartTabs'
import { FollowTip } from '@/components/FollowTip'
import { LadderStrip } from '@/components/LadderStrip'
import { driverName } from '@/lib/drivers'
import { lappedGapText, gapText } from '@/lib/finishing'
import { columnWidths, labelSide, layoutBands, maxLappedColumns, rowHeight, scaleLinear, staircaseStep, textWidth, type ColKind } from '@/lib/ladder'
import {
  availableViews, flattenGroups, gainReach, gapAxis, groupByLapsDown, isClassified, isOut, outLabel, planColumns, raceLaps, raceTip,
  signed, splitGains, statusGroups, strategySplit, tyreName, tyreStyle, type LapColumn, type OutRow, type RaceView,
} from '@/lib/raceResults'
import { resolveTeamColor } from '@/lib/teamColors'
import { useCanHover } from '@/lib/useCanHover'
import { useContainerWidth } from '@/lib/useContainerWidth'
import { useFollowTip } from '@/lib/useFollowTip'
import type { ResultRow } from '@/lib/api'

const PAD = 16
const AXIS_H = 26
const BASELINE = 4.5 // one alphabetic baseline for name and figure (see QualiSegmentsChart)
const COMPACT_STRIP = 12 // header height of a band with no title (stacked layout)
const RACE_STRIP = 42 // header height of a titled band: just the title, unlike the qualifying strip that also holds the cutoff tag
const LEAD_ROOM = 130 // beyond a lead-lap car's nose: its code and a figure as long as the winner's total time
const LAPPED_ROOM = 80 // beyond a lapped car's nose: its code and "+11.8s" (or "P12" when the API sent no seconds)
const MERGED_ROOM = 88 // the same for a merged "or more" column, whose figure also carries laps down: "P18 +15"
const HALO = { paintOrder: 'stroke', stroke: 'var(--color-surface)', strokeWidth: 4, strokeLinejoin: 'round' } as const

const TABS: { value: RaceView; label: string; hint: string }[] = [
  { value: 'finishers', label: 'Finishers', hint: 'Cars by laps down, with the gap to the winner on the lead lap' },
  { value: 'places', label: 'Movers', hint: 'Places gained or lost against the starting grid' },
  { value: 'strategy', label: 'Strategy', hint: 'Tyre stints, lap by lap' },
]

// The race as three pictures of the same result, switched with the tabs above. Cars carry the team colour and the
// three-letter code; the nose is the value. Cars that did not finish (DNF / DNS / DSQ), or started from the pit lane (PL),
// are only names in a block at the bottom left: no glyph, because there is no value to point at.
export function RaceResultsChart({ rows }: { rows: ResultRow[] }) {
  const reduce = useReducedMotion()
  const views = availableViews(rows)
  const [picked, setPicked] = useState<RaceView | null>(null)
  const view = picked && views.includes(picked) ? picked : views[0]
  const ref = useRef<HTMLDivElement>(null)
  const width = useContainerWidth(ref)
  const { at, setAt, handlers, pointer } = useFollowTip()
  const carId = useCarId()
  const ROW_H = rowHeight(useCanHover()) // taller rows for a finger

  const x1 = width - PAD
  const rowKey = (r: ResultRow) => `${view}:${r.driver}`
  // A row's hover cell AND its wash: one rect, limited to the row's own column (`cx0..cx1`). It must NOT be wider: in the
  // column layout rows of different columns share a y, and a full-width cell of a later column sat on top of an earlier
  // column's cars and swallowed their hover (the tooltip then described the wrong car, or none).
  const wash = (cy: number, key: string, bad: boolean, cx0 = PAD - 6, cx1 = x1 + 6) => (
    <rect
      x={cx0} y={cy - ROW_H / 2} width={cx1 - cx0} height={ROW_H}
      fill={bad ? 'var(--color-accent)' : 'var(--color-ink)'} fillOpacity={at?.key === key ? (bad ? 0.2 : 0.07) : bad ? 0.09 : 0}
    />
  )

  // A car with nothing to point at (DNF / DNS / DSQ, PL, no grid): no glyph, its code and a label right-aligned at `xr`, on
  // a light red wash, exactly as qualifying shows a car with no time. A hover/tap row like any car.
  // `centerX` centres the text there instead (Places, on its zero line); the wash still spans the row.
  const outRow = (o: OutRow, cy: number, xr: number, washX0: number, centerX?: number) => {
    const key = rowKey(o.row)
    return (
      <g key={key} {...handlers(key)}>
        <rect x={washX0} y={cy - ROW_H / 2} width={xr - washX0 + 6} height={ROW_H} fill="var(--color-accent)" fillOpacity={at?.key === key ? 0.2 : 0.09} />
        <text data-row={key} x={centerX ?? xr} y={cy + BASELINE} textAnchor={centerX == null ? 'end' : 'middle'} fill="var(--color-ink)" fontSize={13} fontWeight={500}>
          {o.row.driver}
          <tspan dx={8} fill="var(--color-muted)" fontSize={12} className="num">{o.label}</tspan>
        </text>
      </g>
    )
  }
  // Out rows that continue below a plot (Places, Strategy): right-aligned at the far edge, or centred on `centerX`.
  const tailRows = (list: OutRow[], top: number, centerX?: number) =>
    list.map((o, i) => outRow(o, top + i * ROW_H + ROW_H / 2, x1, PAD - 6, centerX))

  const tipRow = rows.find((r) => rowKey(r) === at?.key)
  const tip = tipRow ? raceTip(tipRow, view) : null
  let height = AXIS_H + 6
  let body: React.ReactNode = null
  let note: React.ReactNode = null

  if (width > 0 && view === 'finishers') {
    const allCols = groupByLapsDown(rows)
    const outs = flattenGroups(statusGroups(rows.filter(isOut)))
    // Fit the laps-down columns to the room: drop empty ones farthest-first, then merge the farthest into "+N laps or more"
    // (no car is ever lost); not even one fits -> stack, where empty bands are just dropped.
    const cap = maxLappedColumns(width, outs.length > 0)
    const hasLapped = allCols.some((c) => c.kind === 'lapped' && c.rows.length > 0)
    const kindsOf = (cs: LapColumn[]): ColKind[] => [...cs.map((c) => c.kind), ...(outs.length ? (['out'] as ColKind[]) : [])]
    let cols = planColumns(allCols, !hasLapped || cap >= 1 ? cap : null)
    let kinds = kindsOf(cols)
    let widths = !hasLapped || cap >= 1 ? columnWidths(width, kinds) : null
    if (!widths) {
      cols = planColumns(allCols, null)
      kinds = kindsOf(cols)
    }
    const sideBySide = widths != null
    const colX: number[] = []
    let acc = PAD
    for (const w of widths ?? []) {
      colX.push(acc)
      acc += w
    }
    const leadIdx = cols.findIndex((c) => c.kind === 'lead')
    const leadGaps = (cols[leadIdx]?.rows ?? []).map((r) => r.gap_to_leader_s).filter((g): g is number => g != null)
    // The first tick label is "Winner" (~43px wide) and the next is centred on its tick, so an interval needs ~64px: a narrow
    // lead column gets fewer ticks, never overlapping ones.
    const leadSpan = sideBySide && leadIdx >= 0 ? Math.max(0, (widths as number[])[leadIdx] - 12 - CAR_W - LEAD_ROOM) : x1 - PAD - CAR_W
    const ax = gapAxis(Math.max(0, ...leadGaps), Math.max(2, Math.floor(leadSpan / 64)))

    // One column's cars. Lead lap: x is the real gap to the winner. Lapped columns: cars step along in finishing order
    // (not to scale) and each is LABELLED with its gap to the leader at its last lap. `gx0..gx1` is the column; `right` pins labels to the right of the
    // car (a column neighbour is there, so a flipped label would cross into it).
    // Only the laps-down columns carry a header: the lead lap and the out cars need no label.
    const headerOf = (c: LapColumn) => (c.kind === 'lead' ? '' : c.title)
    const roomOf = (c: LapColumn) => (c.kind === 'lead' ? LEAD_ROOM : c.showDown ? MERGED_ROOM : LAPPED_ROOM)
    const groupRows = (c: LapColumn, gx0: number, gx1: number, rowsTop: number, right: boolean) => {
      const span = Math.max(0, gx1 - gx0 - CAR_W - (right ? roomOf(c) : 0))
      const xLead = scaleLinear(0, ax.max, gx0, gx0 + span)
      const step = staircaseStep(c.rows.length, span)
      return c.rows.map((r, i) => {
        const key = rowKey(r)
        const cy = rowsTop + i * ROW_H + ROW_H / 2
        const x = c.kind === 'lead' ? (r.gap_to_leader_s != null ? xLead(r.gap_to_leader_s) : null) : gx0 + i * step
        const figure =
          c.kind === 'lead'
            ? gapText(r, 'leader')
            : c.showDown
              ? `+${r.laps_down ?? '?'} laps` // laps differ inside a merged column, so its seconds would not compare: the tooltip has them
              : lappedGapText(r, 1) ?? `P${r.position}`
        if (x == null) {
          // finished on the lead lap but no gap was recorded: named, no glyph (nothing to point at)
          return (
            <g key={key} {...handlers(key)}>
              {wash(cy, key, false, gx0 - 6, gx1 + 6)}
              <text data-row={key} x={gx0} y={cy + BASELINE} fill="var(--color-ink)" fontSize={13} fontWeight={500}>
                {r.driver}
                <tspan dx={6} fill="var(--color-muted)" fontSize={12} className="num">{figure || 'no time'}</tspan>
              </text>
            </g>
          )
        }
        const side = right ? 'right' : labelSide(x, CAR_W, textWidth(r.driver.length + figure.length + 1), width, PAD)
        return (
          <g key={key} {...handlers(key)}>
            {wash(cy, key, false, gx0 - 6, gx1 + 6)}
            <g data-row={key}>
              <Car id={carId} x={x} y={cy} color={resolveTeamColor(r.constructor)} />
              <text x={side === 'right' ? x + CAR_W + 6 : x - 6} y={cy + BASELINE} textAnchor={side === 'right' ? 'start' : 'end'} fill="var(--color-ink)" fontSize={13} fontWeight={500} style={HALO}>
                {r.driver}
                <tspan dx={6} fill="var(--color-muted)" fontSize={12} className="num">{figure}</tspan>
              </text>
            </g>
          </g>
        )
      })
    }

    const tickAxis = (gx0: number, gx1: number, bottom: number, right: boolean) => {
      const span = Math.max(0, gx1 - gx0 - CAR_W - (right ? LEAD_ROOM : 0))
      const xt = scaleLinear(0, ax.max, gx0, gx0 + span)
      return ax.ticks.map((t) => (
        <g key={t} aria-hidden>
          <line x1={xt(t)} x2={xt(t)} y1={AXIS_H - 4} y2={bottom} stroke="var(--color-border)" strokeDasharray="4 4" />
          <text x={xt(t)} y={AXIS_H - 10} textAnchor={t === 0 ? 'start' : 'middle'} fill="var(--color-muted)" fontSize={12} className="num">
            {t === 0 ? 'Winner' : `+${t}s`}
          </text>
        </g>
      ))
    }

    let colsBottom: number
    let colsNode: React.ReactNode
    if (sideBySide) {
      const w = widths as number[]
      const maxRows = Math.max(outs.length, ...cols.map((c) => c.rows.length))
      colsBottom = AXIS_H + RACE_STRIP + maxRows * ROW_H
      colsNode = (
        <>
          {leadIdx >= 0 && tickAxis(colX[leadIdx], colX[leadIdx] + w[leadIdx] - 12, colsBottom, true)}
          {/* ONE rule across the top of every column, not a line per column */}
          <line x1={PAD} x2={x1} y1={AXIS_H} y2={AXIS_H} stroke="var(--color-ink)" strokeWidth={1.5} />
          {kinds.map((k, i) => {
            const gx0 = colX[i] + (i > 0 ? 12 : 0)
            const gx1 = i === kinds.length - 1 ? x1 : colX[i] + w[i] - 12
            const sep = i > 0 && <line x1={colX[i]} x2={colX[i]} y1={AXIS_H} y2={colsBottom} stroke="var(--color-border)" strokeWidth={1.5} />
            if (k === 'out') {
              return (
                <g key="out">
                  {sep}
                  <LadderStrip top={AXIS_H} x0={gx0} x1={gx1} name="" rule={false} />
                  {outs.map((o, oi) => outRow(o, AXIS_H + RACE_STRIP + oi * ROW_H + ROW_H / 2, gx1, gx0 - 6))}
                </g>
              )
            }
            const c = cols[i]
            return (
              <g key={c.key}>
                {sep}
                <LadderStrip top={AXIS_H} x0={gx0} x1={gx1} name={headerOf(c)} rule={false} maxWidth={gx1 - gx0} />
                {groupRows(c, gx0, gx1, AXIS_H + RACE_STRIP, true)}
              </g>
            )
          })}
        </>
      )
    } else {
      // The unlabelled bands (lead lap, out) need only a sliver above their rows, not a full header of dead space.
      const { bands, height: h } = layoutBands(
        kinds.map((k, i) => (k === 'out' ? outs.length : cols[i].rows.length)),
        AXIS_H,
        kinds.map((k, i) => (k === 'out' || cols[i].kind === 'lead' ? COMPACT_STRIP : RACE_STRIP)),
        ROW_H,
      )
      colsBottom = h
      const leadBand = bands[leadIdx]
      colsNode = (
        <>
          {leadBand && tickAxis(PAD, x1, leadBand.top + leadBand.height, false)}
          {kinds.map((k, i) =>
            k === 'out' ? (
              <g key="out">
                <LadderStrip top={bands[i].top} x0={PAD} x1={x1} name="" />
                {outs.map((o, oi) => outRow(o, bands[i].rowsTop + oi * ROW_H + ROW_H / 2, x1, PAD - 6))}
              </g>
            ) : (
              <g key={cols[i].key}>
                <LadderStrip top={bands[i].top} x0={PAD} x1={x1} name={headerOf(cols[i])} />
                {groupRows(cols[i], PAD, x1, bands[i].rowsTop, false)}
              </g>
            ),
          )}
        </>
      )
    }
    height = colsBottom + 6
    body = colsNode
  } else if (width > 0 && view === 'places') {
    const { listed, blocks } = splitGains(rows)
    const reach = gainReach(listed)
    const room = width >= 520 ? 100 : 64 // beyond the glyph, for the label of the largest mover
    const xOf = scaleLinear(-reach, reach, PAD + room, x1 - room)
    // Tick labels need ~38px each: pick the step from the room the plot really has (about 110px at 360px wide), not from the data
    // range alone, or "-10 -5 0 +5 +10" run together on a phone.
    const plotW = x1 - room - (PAD + room)
    const step = [1, 2, 5, 10, 20, 50].find((st) => (plotW * st) / (2 * reach) >= 38) ?? 50
    const ticks: number[] = []
    for (let t = -Math.floor(reach / step) * step; t <= reach; t += step) ticks.push(t)
    const plotBottom = AXIS_H + listed.length * ROW_H
    const outList = flattenGroups(blocks)
    height = plotBottom + outList.length * ROW_H + 6
    body = (
      <>
        <text x={PAD} y={AXIS_H - 10} fill="var(--color-muted)" fontSize={12} className="font-display">Lost</text>
        <text x={x1} y={AXIS_H - 10} textAnchor="end" fill="var(--color-muted)" fontSize={12} className="font-display">Gained</text>
        {ticks.map((t) => (
          <g key={t} aria-hidden>
            <line x1={xOf(t)} x2={xOf(t)} y1={AXIS_H - 4} y2={plotBottom} stroke={t === 0 ? 'var(--color-ink)' : 'var(--color-border)'} strokeWidth={t === 0 ? 1.5 : 1} strokeDasharray={t === 0 ? undefined : '4 4'} />
            <text x={xOf(t)} y={AXIS_H - 10} textAnchor="middle" fill="var(--color-muted)" fontSize={12} className="num">{signed(t)}</text>
          </g>
        ))}
        {listed.map((r, i) => {
          const v = r.places_gained as number
          const key = rowKey(r)
          const cy = AXIS_H + i * ROW_H + ROW_H / 2
          const x = xOf(v)
          const gained = v >= 0
          return (
            <g key={key} {...handlers(key)}>
              {wash(cy, key, false)}
              <g data-row={key}>
                {v !== 0 && <line x1={xOf(0)} x2={x} y1={cy} y2={cy} stroke="var(--color-ink)" strokeWidth={2} />}
                <Car id={carId} x={x} y={cy} color={resolveTeamColor(r.constructor)} faceRight={gained} />
                <text x={gained ? x + 6 : x - 6} y={cy + BASELINE} textAnchor={gained ? 'start' : 'end'} fill="var(--color-ink)" fontSize={13} fontWeight={500} style={HALO}>
                  {r.driver}
                  <tspan dx={6} fill={v < 0 ? 'var(--color-accent)' : 'var(--color-ink)'} fontSize={12} fontWeight={700} className="num">{signed(v)}</tspan>
                </text>
              </g>
            </g>
          )
        })}
        {tailRows(outList, plotBottom, xOf(0))}
      </>
    )
    if (listed.length === 0) note = <p className="text-sm text-muted">No starting positions to compare against.</p>
  } else if (width > 0 && view === 'strategy') {
    const { bars, blocks } = strategySplit(rows)
    const laps = Math.max(1, raceLaps(rows))
    const barX0 = PAD + CAR_W + 6 + textWidth(3) + 14
    const xOf = scaleLinear(0, laps, barX0, x1)
    const step = laps <= 30 ? 5 : laps <= 80 ? 10 : 20
    const ticks: number[] = []
    for (let t = 0; t <= laps; t += step) ticks.push(t)
    const plotBottom = AXIS_H + bars.length * ROW_H
    const outList = flattenGroups(blocks)
    height = plotBottom + outList.length * ROW_H + 6
    body = (
      <>
        <text x={PAD} y={AXIS_H - 10} fill="var(--color-muted)" fontSize={12} className="font-display">Lap</text>
        {ticks.map((t) => (
          <g key={t} aria-hidden>
            <line x1={xOf(t)} x2={xOf(t)} y1={AXIS_H - 4} y2={plotBottom} stroke="var(--color-border)" strokeDasharray="4 4" />
            <text x={xOf(t)} y={AXIS_H - 10} textAnchor="middle" fill="var(--color-muted)" fontSize={12} className="num">{t}</text>
          </g>
        ))}
        {bars.map((r, i) => {
          const key = rowKey(r)
          const cy = AXIS_H + i * ROW_H + ROW_H / 2
          const stints = r.stints ?? []
          const retired = isOut(r) // a retiree: shaded, no glyph, its stints kept
          return (
            <g key={key} {...handlers(key)}>
              {wash(cy, key, retired)}
              <g data-row={key}>
                {stints.length > 0 && !retired && <Car id={carId} x={PAD} y={cy} color={resolveTeamColor(r.constructor)} />}
                <text x={retired ? PAD : PAD + CAR_W + 6} y={cy + BASELINE} fill="var(--color-ink)" fontSize={13} fontWeight={500}>{r.driver}</text>
                {stints.length === 0 && (
                  <text x={barX0} y={cy + BASELINE} fill="var(--color-muted)" fontSize={12}>No tyre data</text>
                )}
                {stints.map((s, si) => {
                  const ty = tyreStyle(s.compound)
                  const sx = xOf(s.lap_start - 1)
                  const sw = Math.max(1, xOf(s.lap_end) - sx)
                  return (
                    <g key={si}>
                      <rect
                        x={sx} y={cy - 8} width={sw} height={16}
                        fill={ty ? ty.fill : 'none'} stroke={ty ? 'var(--tyre-edge)' : 'var(--color-muted)'} strokeWidth={1} strokeDasharray={ty ? undefined : '3 2'}
                      />
                      {ty && sw >= 16 && (
                        <text x={sx + sw / 2} y={cy + 4} textAnchor="middle" fill={ty.ink} fontSize={11} fontWeight={700} className="num">{ty.letter}</text>
                      )}
                    </g>
                  )
                })}
              </g>
            </g>
          )
        })}
        {tailRows(outList, plotBottom)}
      </>
    )
  }

  const used = view === 'strategy' ? [...new Set(rows.flatMap((r) => (r.stints ?? []).map((s) => s.compound)))] : []
  const officialStart = rows.some((r) => r.grid_source === 'official')
  const captions: Record<RaceView, string> = {
    finishers:
      `Columns are laps down: the lead lap, then +1 lap, +2 laps. On the lead lap a car sits at its real gap to the winner; ${rows.some((r) => r.lapped_gap_s != null) ? 'a lapped car steps along in finishing order, not to scale, and is labelled with its gap to the leader at the end of its last lap.' : 'a lapped car has no recorded time gap, so lapped cars step along in finishing order, not to scale.'} Cars that did not finish (DNF, DNS, DSQ) are named in the Out column at the far right.`,
    places: `${officialStart ? 'Finishing position against the official starting grid.' : 'Finishing position against classified qualifying position; grid penalties and pit-lane starts are not reflected.'} The nose points the way the car moved.${rows.some((r) => r.pit_lane) ? ' PL means it started from the pit lane, which is not a grid slot, so no places are counted.' : ''} Cars that did not finish, or have no start, are named below, not compared.`,
    strategy:
      'One bar per car across the race distance, split into tyre stints. A dashed segment is a stint with no tyre data. A shaded row is a car that retired: its bar ends where its timing ends. DNS and DSQ are named at the far right.',
  }

  return (
    <m.div
      className="glass w-full rounded-panel p-5"
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 120, damping: 20 }}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-[2.025rem] font-semibold tracking-tight sm:text-[2.7rem]">Race results</h2>
        {views.length > 1 && (
          <ChartTabs
            ariaLabel="Race results view"
            active={view}
            onChange={(v) => {
              setAt(null)
              setPicked(v)
            }}
            tabs={TABS.filter((t) => views.includes(t.value))}
          />
        )}
      </div>

      <FollowTip at={at} tip={tip} pointer={pointer} container={ref} />
      <div ref={ref} className="relative">
        {width > 0 && body && (
          <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="block select-none" role="group" aria-label={`Race results, ${TABS.find((t) => t.value === view)?.label}`}>
            <CarDefs id={carId} />
            {body}
          </svg>
        )}
        <ol className="sr-only">
          {rows.map((r) => (
            <li key={r.driver}>
              {driverName(r.driver)}, {isClassified(r) ? `finished P${r.position}, ${gapText(r, 'leader')}` : outLabel(r)}
              {r.pit_lane ? ', started from the pit lane' : r.grid != null ? `, started P${r.grid}` : ''}
              {r.places_gained != null ? `, ${signed(r.places_gained)} places` : ''}
              {r.strategy ? `, tyres ${r.strategy}` : ''}
            </li>
          ))}
        </ol>
      </div>
      {note}
      {view === 'strategy' && used.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted" aria-label="Tyre key">
          {used.map((c) => {
            const ty = tyreStyle(c)
            return (
              <li key={c ?? 'none'} className="inline-flex items-center gap-1.5">
                <span
                  aria-hidden className="inline-block h-3 w-3 border"
                  style={ty ? { backgroundColor: ty.fill, borderColor: 'var(--tyre-edge)' } : { borderStyle: 'dashed', borderColor: 'var(--color-muted)' }}
                />
                {ty ? `${ty.letter} ${tyreName(c)}` : 'No tyre data'}
              </li>
            )
          })}
        </ul>
      )}
      <p className="mt-4 text-sm text-muted">{captions[view]}</p>
    </m.div>
  )
}
