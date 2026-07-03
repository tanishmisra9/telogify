import { BarChart } from '@/components/BarChart'
import type { SectorBestRow, SectorsData } from '@/lib/api'

function SectorChart({ sector, rows }: { sector: number; rows: SectorBestRow[] }) {
  const sorted = rows.filter((r) => r.sector === sector).sort((a, b) => a.best_time_s - b.best_time_s)
  if (sorted.length === 0) return null

  const fastest = sorted[0].best_time_s
  const bars = sorted.map((r) => ({
    id: r.driver,
    label: r.driver,
    value: r.best_time_s - fastest,
    team: r.constructor,
  }))

  return (
    <div>
      <h3 className="mb-2 text-[1.35rem] font-semibold text-ink">Sector {sector}</h3>
      <BarChart rows={bars} formatValue={(v) => v.toFixed(3)} />
    </div>
  )
}

export function SectorBars({ data }: { data: SectorsData }) {
  if (data.drivers.length === 0) {
    return <p className="text-sm text-muted">No practice sector data yet.</p>
  }

  return (
    <div className="glass rounded-[--radius-panel] p-6">
      <h2 className="font-display text-[2.025rem] font-semibold tracking-tight sm:text-[2.7rem]">Best sectors</h2>
      <div className="mt-5 grid gap-8">
        {[1, 2, 3].map((sector) => (
          <SectorChart key={sector} sector={sector} rows={data.drivers} />
        ))}
      </div>
      <p className="mt-2 text-xs text-muted">
        Indicative: practice fuel loads and engine modes vary between runs, so this is a read on
        where time is, not a verdict. Bars are each driver's gap to the fastest sector time.
      </p>
    </div>
  )
}
