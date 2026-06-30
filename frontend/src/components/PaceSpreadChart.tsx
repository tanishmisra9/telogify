import { useMemo, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { teamLogo } from '@/lib/assets'
import { constructorRows, driverRows, type PaceRow } from '@/lib/paceStats'
import { resolveTeamColor, teamColorWithAlpha } from '@/lib/teamColors'
import type { PaceStint } from '@/lib/api'

type ViewMode = 'drivers' | 'constructors'

const MARGIN = { top: 24, right: 16, bottom: 100, left: 54 }
const WIDTH = 1100
const HEIGHT = 480
const INNER_W = WIDTH - MARGIN.left - MARGIN.right
const INNER_H = HEIGHT - MARGIN.top - MARGIN.bottom
const LOGO = 38 // team logo size under each box (constructor view)

// Inline d3-scaleBand (paddingInner 0.35, paddingOuter 0.12) so we don't pull in d3-scale.
function bandLayout(n: number) {
  const step = INNER_W / Math.max(1, n - 0.35 + 2 * 0.12)
  const bandwidth = step * (1 - 0.35)
  const x0 = step * 0.12
  return {
    bandwidth,
    center: (i: number) => x0 + step * i + bandwidth / 2,
  }
}

export function PaceSpreadChart({ stints }: { stints: PaceStint[] }) {
  const [viewMode, setViewMode] = useState<ViewMode>('drivers')
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const reduce = useReducedMotion()

  const rows = useMemo<PaceRow[]>(
    () => (viewMode === 'drivers' ? driverRows(stints) : constructorRows(stints)),
    [stints, viewMode],
  )

  const { yMin, yMax } = useMemo(() => {
    let lo = Infinity
    let hi = -Infinity
    for (const r of rows) {
      const s = r.stats
      lo = Math.min(lo, s.whisker_low, ...s.outliers)
      hi = Math.max(hi, s.whisker_high, ...s.outliers)
    }
    const pad = (hi - lo) * 0.06 || 0.5
    return { yMin: lo - pad, yMax: hi + pad }
  }, [rows])

  const band = bandLayout(rows.length)
  const y = (v: number) => INNER_H * (1 - (v - yMin) / (yMax - yMin))
  const yTicks = Array.from({ length: 6 }, (_, i) => yMin + ((yMax - yMin) * i) / 5)
  const hovered = rows.find((r) => r.id === hoveredId) ?? null

  return (
    <motion.div
      className="glass w-full overflow-x-auto rounded-[--radius-panel] p-5"
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 120, damping: 20 }}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold tracking-tight">Pace spread</h2>
        <div className="inline-flex rounded-full border border-border bg-surface/60 p-0.5" role="group" aria-label="Chart view">
          {(['drivers', 'constructors'] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setViewMode(mode)}
              className={`rounded-full px-3 py-1 text-sm transition-colors ${
                viewMode === mode ? 'bg-accent/15 text-accent' : 'text-muted hover:text-ink'
              }`}
            >
              {mode === 'drivers' ? 'Drivers' : 'Constructors'}
            </button>
          ))}
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="text-sm text-muted">No pace data.</p>
      ) : (
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full max-w-full" role="img" aria-label="Pace spread box plot">
          <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
            {yTicks.map((tick) => (
              <g key={tick}>
                <line x1={0} x2={INNER_W} y1={y(tick)} y2={y(tick)} stroke="var(--color-border)" strokeDasharray="4 4" />
                <text x={-9} y={y(tick)} textAnchor="end" dominantBaseline="middle" fill="var(--color-muted)" fontSize={14}>
                  {tick.toFixed(1)}s
                </text>
              </g>
            ))}

            {rows.map((row, i) => {
              const cx = band.center(i)
              const bw = Math.min(band.bandwidth * 0.6, 34)
              const logo = teamLogo(row.team)
              const s = row.stats
              const stroke = resolveTeamColor(row.team)
              const fill = teamColorWithAlpha(row.team, 0.28)
              const yQ1 = y(s.q1)
              const yQ3 = y(s.q3)
              const boxTop = Math.min(yQ1, yQ3)
              const boxH = Math.abs(yQ3 - yQ1) || 1
              const isHovered = hoveredId === row.id

              return (
                <g
                  key={row.id}
                  onMouseEnter={() => setHoveredId(row.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  opacity={hoveredId && !isHovered ? 0.45 : 1}
                >
                  <line x1={cx} x2={cx} y1={y(s.whisker_high)} y2={yQ3} stroke={stroke} strokeWidth={2} />
                  <line x1={cx} x2={cx} y1={yQ1} y2={y(s.whisker_low)} stroke={stroke} strokeWidth={2} />
                  <line x1={cx - bw / 2} x2={cx + bw / 2} y1={y(s.whisker_high)} y2={y(s.whisker_high)} stroke={stroke} strokeWidth={2} />
                  <line x1={cx - bw / 2} x2={cx + bw / 2} y1={y(s.whisker_low)} y2={y(s.whisker_low)} stroke={stroke} strokeWidth={2} />
                  <rect x={cx - bw / 2} y={boxTop} width={bw} height={boxH} fill={fill} stroke={stroke} strokeWidth={1.25} rx={3} />
                  <line x1={cx - bw / 2} x2={cx + bw / 2} y1={y(s.median)} y2={y(s.median)} stroke={stroke} strokeWidth={3} />
                  <line x1={cx - bw / 2} x2={cx + bw / 2} y1={y(s.mean)} y2={y(s.mean)} stroke={stroke} strokeWidth={2} strokeDasharray="5 4" />
                  {s.outliers.map((o, oi) => (
                    <circle key={`${row.id}-o-${oi}`} cx={cx} cy={y(o)} r={4} fill="none" stroke={stroke} strokeWidth={1.5} />
                  ))}

                  {viewMode === 'drivers' ? (
                    <>
                      <text x={cx} y={INNER_H + 24} textAnchor="middle" fill="var(--color-ink)" fontSize={14} fontWeight={500}>
                        {row.label}
                      </text>
                      <text x={cx} y={INNER_H + 42} textAnchor="middle" fill="var(--color-muted)" fontSize={12}>
                        +{row.gap_to_fastest_s.toFixed(2)}
                      </text>
                      <text x={cx} y={INNER_H + 58} textAnchor="middle" fill="var(--color-muted)" fontSize={12}>
                        {s.compounds.length ? s.compounds.join('-') : 'N/A'}
                      </text>
                    </>
                  ) : (
                    <>
                      {logo ? (
                        <image href={logo} x={cx - LOGO / 2} y={INNER_H + 8} width={LOGO} height={LOGO * 0.7} preserveAspectRatio="xMidYMid meet" />
                      ) : (
                        <text x={cx} y={INNER_H + 28} textAnchor="middle" fill="var(--color-ink)" fontSize={14} fontWeight={500}>
                          {row.label}
                        </text>
                      )}
                      <text x={cx} y={INNER_H + 48} textAnchor="middle" fill="var(--color-muted)" fontSize={12}>
                        +{row.gap_to_fastest_s.toFixed(2)}
                      </text>
                      <text x={cx} y={INNER_H + 64} textAnchor="middle" fill="var(--color-muted)" fontSize={12}>
                        {s.compounds.length ? s.compounds.join('-') : 'N/A'}
                      </text>
                    </>
                  )}
                </g>
              )
            })}

            {hovered && (
              <foreignObject x={Math.min(INNER_W - 200, Math.max(0, band.center(rows.indexOf(hovered)) - 100))} y={4} width={200} height={132}>
                <div className="glass rounded-xl px-3 py-2 text-xs text-ink">
                  <div className="font-medium">{hovered.label}</div>
                  <div className="mt-1 text-muted">{hovered.team}</div>
                  <div className="mt-2 space-y-0.5 text-muted">
                    <div>Mean {hovered.stats.mean.toFixed(3)}s</div>
                    <div>Median {hovered.stats.median.toFixed(3)}s</div>
                    <div>Q1-Q3 {hovered.stats.q1.toFixed(3)}-{hovered.stats.q3.toFixed(3)}s</div>
                    <div>{hovered.stats.n_laps} laps</div>
                  </div>
                </div>
              </foreignObject>
            )}
          </g>
        </svg>
      )}

      <p className="mt-3 max-w-prose text-xs text-muted">
        Dashed line mean, solid line median, box is the middle 50 percent of laps, whiskers cover
        99.3 percent, dots are outliers.
      </p>
    </motion.div>
  )
}
