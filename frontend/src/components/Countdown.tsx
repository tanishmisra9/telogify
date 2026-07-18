import { CountdownPanel } from '@/components/CountdownPanel'
import { useApi, type NextRace } from '@/lib/api'

// The landing-page centerpiece: the next race as a bold paper panel, the schedule ticking in the
// same mono figures the app uses for telemetry. Self-hides when there's no next race (season over
// or FastF1 unavailable), so the section never ships broken.
export function Countdown() {
  const { data } = useApi<NextRace>('/next-race')
  if (!data) return null

  const place = [data.location, data.country].filter(Boolean).join(', ')
  const raceDate = new Date(data.date_utc).toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  })

  return (
    <section className="mt-24 sm:mt-32">
      <CountdownPanel
        kicker={`Next race · Round ${data.round}`}
        subtitle={`${raceDate}${place ? ` · ${place}` : ''}`}
        title={data.event_name}
        targetIso={data.date_utc}
      />
    </section>
  )
}
