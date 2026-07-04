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

// The landing-page centerpiece: the next race as a bold paper panel, the schedule ticking in the
// same mono figures the app uses for telemetry. Self-hides when there's no next race (season over
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

  const place = [data.location, data.country].filter(Boolean).join(', ')
  const raceDate = new Date(data.date_utc).toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  })

  return (
    <section className="mt-24 sm:mt-32">
      <div className="glass rounded-[--radius-panel] p-8 sm:p-12">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
          <p className="kicker text-accent">Next race · Round {data.round}</p>
          <p className="num text-sm text-muted">
            {raceDate}
            {place ? ` · ${place}` : ''}
          </p>
        </div>

        <h2 className="mt-4 font-display text-5xl leading-[0.95] tracking-tight sm:text-7xl xl:text-8xl">
          {data.event_name}
        </h2>

        <div className="mt-10 grid grid-cols-4 gap-4 sm:gap-6">
          {parts(target).map(([label, value]) => (
            <div key={label} className="border-t-2 border-ink pt-3">
              <span className="num block text-5xl leading-none tracking-tight text-ink tabular-nums sm:text-7xl xl:text-8xl">
                {pad(value)}
              </span>
              <span className="mt-2 block text-xs uppercase tracking-[0.2em] text-muted sm:text-sm">
                {label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
