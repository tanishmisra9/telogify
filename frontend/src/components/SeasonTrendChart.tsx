import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, m, useReducedMotion } from 'framer-motion'
import { ChartTabs } from '@/components/ChartTabs'
import { PointPopup } from '@/components/PointPopup'
import { INNER_H, MARGIN, MIN_ROUND_SLOT, PLOT_PAD_X, ZoomChartFrame } from '@/components/ZoomChartFrame'
import { ZoomControls } from '@/components/ZoomControls'
import { TeamSelectLegend } from '@/components/TeamSelectLegend'
import { resolveTeamColor, teamShortName } from '@/lib/teamColors'
import { useChartPointHover } from '@/lib/useChartPointHover'
import { useChartZoom } from '@/lib/useChartZoom'
import { useIsMobile } from '@/lib/useIsMobile'
import { drawTransition, morphTransition, spring } from '@/lib/motion'
import { formArrow, formSentence } from '@/lib/seasonStart'
import { smoothPath } from '@/lib/svgPath'
import { MIN_ZOOM } from '@/lib/zoom'
import type { SeasonConstructorRow, SeasonRound } from '@/lib/api'

type Metric = 'pace' | 'quali' | 'cumulative'
const METRIC_LABEL: Record<Metric, string> = { pace: 'Race pace', quali: 'Qualifying', cumulative: 'Cumulative' }
// 100 = that round's fastest team on this metric, increasing downward as the gap grows. For
// qualifying this is a literal percentage of the fastest lap time; for pace (a seconds gap) and
// cumulative (a raw score) it's the same index convention applied for a consistent axis across
// all three tabs, not a true percentage of those units.
//
// Pace and qualifying get a fixed, whole-percent axis (100-105% / 100-106%) since their gaps
// span several points and round numbers read easier than computed decimals. Cumulative's gap
// is naturally much smaller (it's a season-long average, not one round), so it keeps a dynamic
// axis sized to its own data with finer decimal ticks rather than being squeezed into the same
// 1%-per-tick scale.
const FIXED_AXIS_MAX: Partial<Record<Metric, number>> = { pace: 5, quali: 6 }

// Aligns a team's sparse {round, value} points onto every round in `roundNums`, so the same
// team's path always has the same number of points (and therefore the same smoothPath command
// structure) regardless of which metric is selected — required for the d attribute to morph
// smoothly between metrics rather than snap when round coverage differs (pace/quali/cumulative
// trend arrays can have gaps independently of each other; see season.py's build_season_snapshot).
// Missing rounds are linearly interpolated between the nearest known points, or held flat at the
// nearest known value past either edge — a visual continuity aid, consistent with this chart's
// existing framing of the axis as an index for comparison, not a literal per-round measurement.
function resampleToRounds(points: { round: number; value: number }[], roundNums: number[]): number[] {
  const sorted = [...points].sort((a, b) => a.round - b.round)
  return roundNums.map((r) => {
    const exact = sorted.find((p) => p.round === r)
    if (exact) return exact.value
    const before = [...sorted].reverse().find((p) => p.round < r)
    const after = sorted.find((p) => p.round > r)
    if (before && after) {
      const t = (r - before.round) / (after.round - before.round)
      return before.value + (after.value - before.value) * t
    }
    return (before ?? after)?.value ?? 0
  })
}

// This chart's convention is the same across all three metrics: lower is better (100 = that
// round's fastest team, higher = further behind). pace/quali already have a backend-computed
// season aggregate (MetricAgg.mean); cumulative has no dedicated aggregate field, so rank it by
// its most recent round's trend value instead. A team with no data for the metric sorts last.
function rankValue(row: SeasonConstructorRow, metric: Metric): number {
  if (metric === 'pace') return row.pace_gap.mean ?? Infinity
  if (metric === 'quali') return row.quali_gap_pct.mean ?? Infinity
  // The legend shows this same weighted figure, so order by it (an API without it: latest round).
  const weighted = row.form?.cumulative?.weighted
  if (weighted != null) return weighted
  const sorted = [...row.trend.cumulative].sort((a, b) => a.round - b.round)
  return sorted.length > 0 ? sorted[sorted.length - 1].value : Infinity
}

// Team order for the animated paths. Filtered on data presence only, no sort -- exported so a
// test can pin the regression this guards against: this order must be identical across metrics
// for the same team set, or AnimatePresence sees a moved child and restarts its draw-in instead
// of morphing (see the `series` comment below for the mechanism).
export function seriesTeamOrder(rows: SeasonConstructorRow[], metric: Metric): string[] {
  return rows.filter((r) => r.trend[metric].length > 0).map((r) => r.constructor)
}

// Team order for the legend only: ranked by the selected metric, independent of `seriesTeamOrder`.
export function legendTeamOrder(rows: SeasonConstructorRow[], metric: Metric): string[] {
  return [...rows]
    .sort((a, b) => rankValue(a, metric) - rankValue(b, metric))
    .filter((r) => r.trend[metric].length > 0)
    .map((r) => r.constructor)
}

// Legend rows for the selected tab: the recency-weighted season figure on the chart's own axis
// (100% = the round's fastest team), the rank-movement arrow, and the arrow in words as the hint.
// Teams with no `form` (an older API) get a bare row.
export function legendRowsFor(rows: SeasonConstructorRow[], metric: Metric) {
  const rowByTeam = new Map(rows.map((r) => [r.constructor, r]))
  return legendTeamOrder(rows, metric).map((team) => {
    const f = rowByTeam.get(team)?.form?.[metric]
    if (!f || f.weighted == null) return { team }
    return {
      team,
      value: [`${(100 + f.weighted).toFixed(1)}%`, formArrow(f.form_places)].filter(Boolean).join('  '),
      title: formSentence(f) ?? undefined,
    }
  })
}

// What a hovered dot says, in the units the backend actually stores (the axis is an index; see
// FIXED_AXIS_MAX above): qualifying is a true percentage of the fastest lap, race pace is seconds a lap
// behind the fastest team's median, cumulative is the 0..1 blended score (0 = the round's best team).
// A value of exactly 0 is that round's best team on the metric.
export function trendPointCopy(
  metric: Metric,
  team: string,
  eventName: string | undefined,
  round: number,
  value: number,
): { title: string; lines: string[] } {
  const best = value === 0
  const line =
    metric === 'quali'
      ? best ? 'Fastest qualifier of the round' : `${value.toFixed(2)}% behind the fastest qualifier`
      : metric === 'pace'
        ? best ? 'Fastest race pace of the round' : `${value.toFixed(2)} s a lap behind the fastest race pace`
        : best ? 'Best overall of the round' : `Overall score ${value.toFixed(2)} (0 is the round's best, 1 its worst)`
  return { title: `${team}, ${eventName ?? `round ${round}`}`, lines: [line] }
}

// One line per constructor: gap to the round's fastest team, round by round. Lower is
// better and the y-axis is inverted (0 at top), so a line hugging the top is a season-long
// front-runner and a line dropping away is a team losing ground. Copies DegradationChart's scaffold.
export function SeasonTrendChart({ rows, rounds }: { rows: SeasonConstructorRow[]; rounds: SeasonRound[] }) {
  const reduce = useReducedMotion()
  const isMobile = useIsMobile()
  const [metric, setMetric] = useState<Metric>('cumulative')
  // Empty = show every team (default). Not reset on metric switch, so a comparison survives
  // moving between Race pace/Qualifying/Cumulative.
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const viewportRef = useRef<HTMLDivElement>(null)
  const { zoom, width, zooming, zoomIn, zoomOut, reset, pinchingRef } = useChartZoom(viewportRef)
  const { hovered, setHovered, isScrolling, pointHandlers } = useChartPointHover(viewportRef, () => pinchingRef.current)
  // A readout is anchored to where its dot was; zooming moves the dot, so close it.
  useEffect(() => setHovered(null), [zoom, setHovered])

  const toggleTeam = (team: string) => {
    // Touch has no mouseleave: an open readout would stay set while its team is hidden and pop back
    // when the team returns, so changing the isolation closes it.
    setHovered(null)
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(team)) next.delete(team)
      else next.add(team)
      return next
    })
  }

  const roundNums = rounds.map((r) => r.round)
  const xMin = Math.min(...roundNums)
  const xMax = Math.max(...roundNums)
  const innerWNeeded = Math.max(1, roundNums.length - 1) * MIN_ROUND_SLOT
  // `width` is the viewport's width (the y-axis is a separate panel), so only MARGIN.right -- the plot's own
  // breathing room -- comes off it. Zoom then scales the plot beyond the viewport: dots and text keep their pixel size.
  const innerW = Math.max(width - MARGIN.right - PLOT_PAD_X, innerWNeeded) * zoom
  const innerH = INNER_H * zoom

  // Filtered on the team's original (pre-resample) point count, so a team with zero real data
  // for this metric still doesn't render a fabricated flat line — resampling only fills gaps
  // for teams that have some data. Order must NOT depend on `metric`: these become the
  // AnimatePresence-tracked <m.path> children below, and Framer restarts a moved child's
  // `initial` (pathLength 0) -> `animate` (pathLength 1) draw-in instead of just morphing `d`,
  // which is what broke the cross-metric morph before (reordering here to match legend rank).
  const rowByTeam = new Map(rows.map((r) => [r.constructor, r]))
  const series = seriesTeamOrder(rows, metric).map((team) => ({
    team,
    values: resampleToRounds(rowByTeam.get(team)!.trend[metric], roundNums),
  }))
  const values = series.flatMap((s) => s.values)

  // Ranked by the selected metric (lower is better, matching this chart's own convention -- see
  // the caption below) so the legend order actually reflects the current tab instead of staying
  // frozen at the overall-rank order regardless of which metric is selected. Kept separate from
  // `series` above: the legend can reorder freely, the animated paths cannot.
  // On phones the figure stacks under the name (see the legend's stackValue) and a long name is
  // shortened so it isn't cut off, same as the Race starts legend.
  const legendRows = legendRowsFor(rows, metric).map((r) => ({
    ...r,
    label: isMobile && r.team.length > 13 ? teamShortName(r.team) : undefined,
  }))

  if (series.length === 0 || values.length === 0) {
    return <p className="text-sm text-muted">No trend data yet.</p>
  }

  // Selection persists across metric tabs, but a team's selection can be meaningless for a
  // metric it has no data for. If every selected team is absent here, fall back to showing the
  // full field for this metric rather than an empty chart (same recipe as DegradationChart's
  // compound-switch fallback).
  const isFiltering = selected.size > 0 && series.some((s) => selected.has(s.team))
  const visibleSeries = isFiltering ? series.filter((s) => selected.has(s.team)) : series

  const dataMax = Math.max(...values)
  const fixedMax = FIXED_AXIS_MAX[metric]
  const yMax = fixedMax != null ? Math.max(fixedMax, Math.ceil(dataMax)) : dataMax * 1.05 || 1
  const x = (v: number) => (xMax === xMin ? innerW / 2 : ((v - xMin) / (xMax - xMin)) * innerW)
  const y = (v: number) => innerH * (v / yMax) // 0 at the top (fastest team on top)

  const yTicks =
    fixedMax != null
      ? Array.from({ length: yMax + 1 }, (_, i) => i)
      : Array.from({ length: 5 }, (_, i) => (yMax * i) / 4)
  const formatTick = (v: number) => (fixedMax != null ? `${100 + v}%` : `${(100 + v).toFixed(1)}%`)

  // The readout follows the dot under the cursor, but only while that team is still drawn (isolating
  // another team removes the dot without a mouseleave).
  const eventOf = new Map(rounds.map((r) => [r.round, r.event_name]))
  const hoveredValue =
    hovered && visibleSeries.some((s) => s.team === hovered.key)
      ? rowByTeam.get(hovered.key)?.trend[metric].find((p) => p.round === hovered.round)?.value
      : undefined
  const tip =
    hovered && hoveredValue != null
      ? trendPointCopy(metric, hovered.key, eventOf.get(hovered.round), hovered.round, hoveredValue)
      : null

  return (
    <m.div
      className="glass w-full rounded-panel p-5"
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={spring}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <ZoomControls zoom={zoom} onIn={zoomIn} onOut={zoomOut} onReset={reset} />
        <ChartTabs
          ariaLabel="Metric"
          active={metric}
          onChange={(mk) => {
            setMetric(mk)
            setHovered(null)
          }}
          tabs={(['cumulative', 'pace', 'quali'] as Metric[]).map((mkey) => ({ value: mkey, label: METRIC_LABEL[mkey] }))}
        />
      </div>

      <ZoomChartFrame
        viewportRef={viewportRef}
        innerW={innerW}
        innerH={innerH}
        yTicks={yTicks.map((t) => ({ pos: y(t), label: formatTick(t) }))}
        xTicks={roundNums.map((r) => ({ pos: x(r), label: String(r) }))}
        zoomed={zoom > MIN_ZOOM}
        svgLabel={`${METRIC_LABEL[metric]} gap by round`}
        regionLabel="Gap by round chart, scrollable when zoomed"
      >
        <AnimatePresence>
          {visibleSeries.map((s) => {
            const color = resolveTeamColor(s.team)
            const pathD = smoothPath(roundNums.map((r, i) => ({ x: x(r), y: y(s.values[i]) })))
            return (
              <m.path
                key={s.team}
                fill="none"
                stroke={color}
                strokeWidth={2}
                strokeLinecap="round"
                initial={reduce ? false : { pathLength: 0, opacity: 0, d: pathD }}
                animate={{ pathLength: 1, opacity: 1, d: pathD }}
                exit={{ opacity: 0 }}
                transition={reduce || zooming ? { duration: 0 } : { ...drawTransition, d: morphTransition }}
              />
            )
          })}
        </AnimatePresence>

        {/* Dots: one per REAL round (trend[metric]), never per resampled value, so a stretch of line
            with no dot under it is filled in between its neighbours. They glide with the line on a tab
            switch and fade in as the draw-in finishes. A wide transparent circle is the hit target;
            pointer events are off while scrolling so a still cursor can't swap the readout. */}
        <g className={isScrolling ? 'pointer-events-none' : undefined}>
          {visibleSeries.map((s) => {
            const color = resolveTeamColor(s.team)
            return rowByTeam.get(s.team)!.trend[metric].map((p) => {
              const cx = x(p.round)
              const cy = y(p.value)
              return (
                <g key={`${s.team}-${p.round}`} {...pointHandlers(s.team, p.round)}>
                  <circle cx={cx} cy={cy} r={12} fill="transparent" />
                  <m.circle
                    r={3.5}
                    fill={color}
                    initial={reduce ? false : { cx, cy, opacity: 0 }}
                    animate={{ cx, cy, opacity: 1 }}
                    transition={
                      reduce || zooming
                        ? { duration: 0 }
                        : { cx: morphTransition, cy: morphTransition, opacity: { duration: 0.2, delay: 0.4 } }
                    }
                  />
                </g>
              )
            })
          })}
        </g>
      </ZoomChartFrame>
      <PointPopup hovered={hovered} tip={tip} />

      <div className="mt-6 border-t border-border pt-5">
        <TeamSelectLegend
          rows={legendRows}
          selected={selected}
          onToggle={toggleTeam}
          isFiltering={isFiltering}
          stackValue={isMobile}
        />
      </div>
      <p className="mt-4 text-sm text-muted">
        Gap to each round's fastest team, round by round. Each dot is a real round (hover or tap it for
        the value); a line running between two dots with none in between is filled in for that stretch.
        100% is that round's fastest team on
        this metric; higher is further behind, so a line near the top ran at the front all season
        and a line dropping away lost ground. For race pace and cumulative, the percentage is an
        index for a consistent axis across tabs, not a literal percentage of seconds or score.
        The legend shows each team's season figure on that same scale, with recent rounds weighted
        more (a round's weight halves every 6 rounds), and the arrow is places gained or lost on that
        recent form against the whole season, so it is relative to the rest of the field. Click a
        team to isolate its line, click again to bring it back.
      </p>
    </m.div>
  )
}
