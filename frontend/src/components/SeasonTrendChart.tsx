import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, m, useReducedMotion } from 'framer-motion'
import { ChartTabs } from '@/components/ChartTabs'
import { ScrollFadeEdge } from '@/components/ScrollFadeEdge'
import { TeamSelectLegend } from '@/components/TeamSelectLegend'
import { resolveTeamColor } from '@/lib/teamColors'
import { drawTransition, morphTransition, spring } from '@/lib/motion'
import { smoothPath } from '@/lib/svgPath'
import { useScrollFade } from '@/lib/useScrollFade'
import type { SeasonConstructorRow, SeasonRound } from '@/lib/api'

const HEIGHT = 440
const MARGIN = { top: 16, right: 16, bottom: 52, left: 56 }
const INNER_H = HEIGHT - MARGIN.top - MARGIN.bottom
// Structural, not fluid: each round gets this many real pixels of x-axis space no matter the
// container size, same reasoning as BarChart/PaceSpreadChart. Generous on purpose, not just
// enough to avoid tick overlap: this chart draws up to ~10 overlapping team lines per round, and
// a fluid-scaled axis squeezed thin later in a season reads as a tangle -- a heart monitor, not
// a comparison. Scrolling a wider chart beats cramming a full season into one screenful.
const MIN_ROUND_SLOT = 64

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

// One line per constructor: gap to the round's fastest team, round by round. Lower is
// better and the y-axis is inverted (0 at top), so a line hugging the top is a season-long
// front-runner and a line dropping away is a team losing ground. Copies DegradationChart's scaffold.
export function SeasonTrendChart({ rows, rounds }: { rows: SeasonConstructorRow[]; rounds: SeasonRound[] }) {
  const reduce = useReducedMotion()
  const [metric, setMetric] = useState<Metric>('pace')
  // Empty = show every team (default). Not reset on metric switch, so a comparison survives
  // moving between Race pace/Qualifying/Cumulative.
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const containerRef = useRef<HTMLDivElement>(null)
  const [containerWidth, setContainerWidth] = useState(0)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setContainerWidth(entry.contentRect.width))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const canScrollRight = useScrollFade(containerRef)

  const toggleTeam = (team: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(team)) next.delete(team)
      else next.add(team)
      return next
    })

  const roundNums = rounds.map((r) => r.round)
  const xMin = Math.min(...roundNums)
  const xMax = Math.max(...roundNums)
  const innerWNeeded = Math.max(1, roundNums.length - 1) * MIN_ROUND_SLOT
  // containerWidth is the scrolling area alone now (the y-axis panel is a separate flex sibling
  // with its own width), so only MARGIN.right -- the scrolling SVG's own breathing room -- comes
  // off it.
  const innerW = Math.max(containerWidth - MARGIN.right, innerWNeeded)
  // No MARGIN.left here: the y-axis moved into its own frozen panel outside this scrolling SVG,
  // so this one's own content starts right at x=0 instead of leaving room for axis labels.
  const width = innerW + MARGIN.right

  // Filtered on the team's original (pre-resample) point count, so a team with zero real data
  // for this metric still doesn't render a fabricated flat line — resampling only fills gaps
  // for teams that have some data.
  const series = rows
    .filter((r) => r.trend[metric].length > 0)
    .map((r) => ({ team: r.constructor, values: resampleToRounds(r.trend[metric], roundNums) }))
  const values = series.flatMap((s) => s.values)

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
  const y = (v: number) => INNER_H * (v / yMax) // 0 at the top (fastest team on top)

  const yTicks =
    fixedMax != null
      ? Array.from({ length: yMax + 1 }, (_, i) => i)
      : Array.from({ length: 5 }, (_, i) => (yMax * i) / 4)
  const formatTick = (v: number) => (fixedMax != null ? `${100 + v}%` : `${(100 + v).toFixed(1)}%`)

  return (
    <m.div
      className="glass w-full rounded-[--radius-panel] p-5"
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={spring}
    >
      <div className="mb-4 flex flex-wrap items-center justify-end gap-3">
        <ChartTabs
          ariaLabel="Metric"
          active={metric}
          onChange={setMetric}
          tabs={(['pace', 'quali', 'cumulative'] as Metric[]).map((mkey) => ({ value: mkey, label: METRIC_LABEL[mkey] }))}
        />
      </div>

      <div className="flex">
        {/* Frozen y-axis: its own small SVG outside the scrolling container, not part of it, so
            the percent scale stays put and readable no matter how far into the season you've
            scrolled. Only the round axis and the lines themselves scroll. */}
        <svg width={MARGIN.left} height={HEIGHT} className="shrink-0" aria-hidden>
          <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
            {yTicks.map((t) => (
              <text key={t} x={-9} y={y(t)} textAnchor="end" dominantBaseline="middle" fill="var(--color-muted)" fontSize={13}>
                {formatTick(t)}
              </text>
            ))}
          </g>
        </svg>
        <div className="relative min-w-0 flex-1">
        <div ref={containerRef} className="overflow-x-auto overscroll-x-contain">
        <svg width={width} height={HEIGHT} viewBox={`0 0 ${width} ${HEIGHT}`} className="max-w-none" role="img" aria-label={`${METRIC_LABEL[metric]} gap by round`}>
          <g transform={`translate(0,${MARGIN.top})`}>
            {yTicks.map((t) => (
              <line key={t} x1={0} x2={innerW} y1={y(t)} y2={y(t)} stroke="var(--color-muted)" strokeOpacity={0.35} strokeWidth={1.25} strokeDasharray="4 4" />
            ))}
            {roundNums.map((r) => (
              <text key={r} x={x(r)} y={INNER_H + 22} textAnchor="middle" fill="var(--color-muted)" fontSize={12}>
                {r}
              </text>
            ))}

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
                    transition={reduce ? { duration: 0 } : { ...drawTransition, d: morphTransition }}
                  />
                )
              })}
            </AnimatePresence>
          </g>
        </svg>
        </div>
        <ScrollFadeEdge visible={canScrollRight} />
        {/* "Round" axis title, static outside the scrolling container: only the round-number
            ticks above should scroll with the x-axis, the title itself should stay put. */}
        <p
          className="pointer-events-none absolute inset-x-0 text-center text-xs text-muted"
          style={{ top: MARGIN.top + INNER_H + 36 }}
        >
          Round
        </p>
        </div>
      </div>

      <div className="mt-6 border-t border-border pt-5">
        <TeamSelectLegend
          rows={series.map((s) => ({ team: s.team }))}
          selected={selected}
          onToggle={toggleTeam}
          isFiltering={isFiltering}
        />
      </div>
      <p className="mt-4 text-xs text-muted">
        Gap to each round's fastest team, round by round. 100% is that round's fastest team on
        this metric; higher is further behind, so a line near the top ran at the front all season
        and a line dropping away lost ground. For race pace and cumulative, the percentage is an
        index for a consistent axis across tabs, not a literal percentage of seconds or score.
        Click a team to isolate its line, click again to bring it back.
      </p>
    </m.div>
  )
}
