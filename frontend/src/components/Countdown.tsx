import { useEffect, useState } from 'react'
import { useApi, type NextRace } from '@/lib/api'

const pad = (n: number) => String(n).padStart(2, '0')

function parts(target: number) {
  const s = Math.max(0, Math.floor((target - Date.now()) / 1000))
  const days = Math.floor(s / 86400)
  return [
    [days === 1 ? 'Day' : 'Days', days],
    ['Hours', Math.floor((s % 86400) / 3600)],
    ['Minutes', Math.floor((s % 3600) / 60)],
    ['Seconds', s % 60],
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
          <p className="kicker text-sm! text-accent">Next race · Round {data.round}</p>
          {/* Same kicker voice as the line above (mono, uppercase, tracked), just muted instead
              of accent-red, so the two lines read as one typographic family, not two. */}
          <p className="kicker text-sm! text-muted">
            {raceDate}
            {place ? ` · ${place}` : ''}
          </p>
        </div>

        {/* -0.07em compensates for font-metric optical misalignment, not a layout bug: this
            heading's box-left edge is pixel-identical to the kicker/digit rows above and below
            it (verified via getBoundingClientRect), but Instrument Sans (font-display) carries
            noticeably more built-in left-side-bearing on a capital letter than the mono font
            does (measured via canvas text metrics: ~8px vs ~1.5px at 96px, i.e. the heading's
            own ink starts ~6.5px right of where the kicker's ink starts despite an identical CSS
            edge). An em unit keeps the correction proportional as the heading scales across
            breakpoints instead of a single px value that would only be right at one size. */}
        <h2 className="mt-4 ml-[-0.07em] font-display text-5xl leading-[0.95] tracking-tight sm:text-7xl xl:text-8xl">
          {data.event_name}
        </h2>

        {/* Flex, not an equal-width grid: a grid column stretches each unit to the same width
            regardless of content, so the units end up scattered at inconsistent distances from
            each other and from the panel's own left edge. Flex sizes each "02 Days" chunk to its
            own content and keeps a uniform gap between them, so the row starts flush with the
            heading/kicker above it instead of floating independently. The label sits at the
            number's own baseline beside it (SeasonStats' pattern below), not stacked underneath. */}
        <div className="mt-10 flex flex-wrap gap-x-10 gap-y-4" aria-live="polite" aria-atomic="true">
          {parts(target).map(([label, value]) => (
            <div key={label} className="flex items-baseline gap-2">
              <span className="num text-4xl leading-none tracking-tight text-ink tabular-nums sm:text-6xl xl:text-8xl">
                {pad(value)}
              </span>
              {/* kicker (not a bare uppercase/tracking utility stack) so this sits in the same
                  mono fontface as the digits above it and every other kicker on the panel,
                  instead of silently inheriting the body sans font. */}
              <span className="kicker text-xs! text-muted sm:text-sm!">{label}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
