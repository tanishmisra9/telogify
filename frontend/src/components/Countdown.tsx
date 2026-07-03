import { useEffect, useState } from 'react'
import { useApi, type NextRace } from '@/lib/api'

const pad = (n: number) => String(n).padStart(2, '0')

function parts(target: number) {
  const s = Math.max(0, Math.floor((target - Date.now()) / 1000))
  return [
    ['Days', Math.floor(s / 86400)],
    ['Hrs', Math.floor((s % 86400) / 3600)],
    ['Min', Math.floor((s % 3600) / 60)],
    ['Sec', s % 60],
  ] as const
}

// A race-timing readout, not a hero-metric: real schedule data in the mono tabular figures
// the rest of the app uses for telemetry. Self-hides when there's no next race (season over
// or FastF1 unavailable), so the section never ships broken.
export function Countdown() {
  const { data } = useApi<NextRace>('/next-race')
  const target = data ? new Date(data.date_utc).getTime() : null
  const [, tick] = useState(0)

  useEffect(() => {
    if (target == null) return
    const id = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [target])

  if (!data || target == null) return null

  return (
    <div className="mt-24 border-t-2 border-ink pt-5 sm:mt-32">
      <p className="font-display text-2xl tracking-tight">
        <span className="text-muted">Next race</span>
        <span className="ml-4 text-ink">{data.event_name}</span>
      </p>
      <div className="mt-5 grid grid-cols-4 gap-2 sm:flex sm:flex-wrap sm:gap-x-8 sm:gap-y-4">
        {parts(target).map(([label, value]) => (
          <div key={label} className="min-w-0 sm:flex sm:items-baseline sm:gap-2">
            <span className="num block text-4xl leading-none tracking-tight text-ink sm:inline sm:text-8xl">
              {pad(value)}
            </span>
            <span className="mt-1 block text-xs text-muted sm:mt-0 sm:inline sm:text-sm">{label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
