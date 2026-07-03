import { BarChart } from '@/components/BarChart'
import type { TopSpeedsData } from '@/lib/api'

export function TopSpeedBars({ data }: { data: TopSpeedsData }) {
  if (data.drivers.length === 0) {
    return <p className="text-sm text-muted">No practice top-speed data yet.</p>
  }

  const sorted = [...data.drivers].sort((a, b) => b.max_speed_kmh - a.max_speed_kmh)
  const bars = sorted.map((r) => ({
    id: r.driver,
    label: r.driver,
    value: r.max_speed_kmh,
    team: r.constructor,
  }))
  const domainMin = Math.min(...sorted.map((r) => r.max_speed_kmh)) - 6

  return (
    <div className="glass rounded-[--radius-panel] p-6">
      <h2 className="font-display text-[2.025rem] font-semibold tracking-tight sm:text-[2.7rem]">Top speeds (km/h)</h2>
      <div className="mt-5">
        <BarChart rows={bars} formatValue={(v) => v.toFixed(0)} domainMin={domainMin} />
      </div>
      <p className="mt-2 text-xs text-muted">
        Indicative: engine modes and fuel loads vary between practice runs, so a deficit here may
        be a mode choice rather than a true weakness.
      </p>
    </div>
  )
}
