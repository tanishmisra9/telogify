import { useReducedMotion } from 'framer-motion'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { PaceStint } from '@/lib/api'

const COMPOUND_COLOR: Record<string, string> = {
  SOFT: '#ff5961',
  MEDIUM: '#ffd34e',
  HARD: '#e8e8e8',
  INTERMEDIATE: '#4cc06a',
  WET: '#3b9eff',
}
const palette = ['#f0b34a', '#5ad1c8', '#c98bff', '#7aa6ff', '#ff8f5a', '#9ad34a', '#ff6fae', '#69d0ff']

function compoundColor(c: string | null): string {
  return (c && COMPOUND_COLOR[c]) || '#8a8a93'
}

type Series = { id: string; label: string; color: string }
type Row = { lap: number; [key: string]: number }

function buildRows(points: Array<{ id: string; lap: number; value: number }>): Row[] {
  const map = new Map<number, Row>()
  for (const p of points) {
    const row = map.get(p.lap) ?? ({ lap: p.lap } as Row)
    row[p.id] = p.value
    map.set(p.lap, row)
  }
  return [...map.values()].sort((a, b) => a.lap - b.lap)
}

// Per-stint series, each colored by its tyre compound.
function driverModel(stints: PaceStint[]) {
  const series: Series[] = []
  const points: Array<{ id: string; lap: number; value: number }> = []
  for (const st of stints) {
    const id = `${st.driver}#${st.stint_number}`
    series.push({ id, label: `${st.driver} ${st.compound ?? ''}`.trim(), color: compoundColor(st.compound) })
    ;(st.lap_times ?? []).forEach((t, idx) => points.push({ id, lap: (st.lap_start ?? 1) + idx, value: t }))
  }
  return { series, rows: buildRows(points) }
}

// One line per constructor: mean lap time across that team's drivers/stints.
function constructorModel(stints: PaceStint[]) {
  const byConLap = new Map<string, Map<number, number[]>>()
  for (const st of stints) {
    const c = st.constructor ?? '?'
    const laps = byConLap.get(c) ?? new Map<number, number[]>()
    ;(st.lap_times ?? []).forEach((t, idx) => {
      const lap = (st.lap_start ?? 1) + idx
      const arr = laps.get(lap) ?? []
      arr.push(t)
      laps.set(lap, arr)
    })
    byConLap.set(c, laps)
  }
  const series: Series[] = []
  const points: Array<{ id: string; lap: number; value: number }> = []
  let ci = 0
  for (const [c, laps] of byConLap) {
    series.push({ id: c, label: c, color: palette[ci++ % palette.length] })
    for (const [lap, arr] of laps) points.push({ id: c, lap, value: arr.reduce((a, b) => a + b, 0) / arr.length })
  }
  return { series, rows: buildRows(points) }
}

export function PaceChart({ stints, mode }: { stints: PaceStint[]; mode: 'driver' | 'constructor' }) {
  const reduce = useReducedMotion()
  const { series, rows } = mode === 'driver' ? driverModel(stints) : constructorModel(stints)

  if (rows.length === 0) {
    return <p className="text-sm text-muted">No pace data.</p>
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 8, left: 4 }}>
        <CartesianGrid stroke="var(--color-border)" vertical={false} />
        <XAxis
          dataKey="lap"
          type="number"
          domain={['dataMin', 'dataMax']}
          stroke="var(--color-muted)"
          tick={{ fontSize: 11 }}
          tickLine={false}
        />
        <YAxis
          reversed
          domain={['auto', 'auto']}
          stroke="var(--color-muted)"
          tick={{ fontSize: 11 }}
          tickLine={false}
          width={44}
          tickFormatter={(v: number) => v.toFixed(1)}
        />
        <Tooltip
          contentStyle={{
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            borderRadius: 10,
            fontSize: 12,
          }}
          labelFormatter={(l) => `Lap ${l}`}
          formatter={(v, name) => [`${Number(v).toFixed(2)} s`, name]}
        />
        {series.map((s) => (
          <Line
            key={s.id}
            dataKey={s.id}
            name={s.label}
            stroke={s.color}
            strokeWidth={1.6}
            dot={false}
            connectNulls
            isAnimationActive={!reduce}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
