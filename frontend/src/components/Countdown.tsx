import { BlurFade } from '@/components/BlurFade'
import { CountdownPanel } from '@/components/CountdownPanel'
import { useAppSettled, useApi, type NextRace } from '@/lib/api'

// The landing-page centerpiece: the next race as a bold paper panel, the schedule ticking in the
// same mono figures the app uses for telemetry. Self-hides when there's no next race (season over
// or FastF1 unavailable), so the section never ships broken.
//
// Fetches immediately on mount regardless of `settled` (so this request is one of the ones
// useAppSettled() is itself waiting on), but withholds the actual reveal until settled is true --
// this is the landing page's first below-the-fold block, so its BlurFade both starts the
// post-hero cascade and is the first real proof that `!data` no longer means "still loading."
export function Countdown() {
  const { data } = useApi<NextRace>('/next-race')
  const settled = useAppSettled()
  if (!data || !settled) return null

  const place = data.location

  return (
    <BlurFade>
      <section className="mt-24 sm:mt-32">
        <CountdownPanel
          kicker={`Next race · Round ${data.round}`}
          subtitle={place && <span className="block">{place}</span>}
          title={data.event_name}
          targetIso={data.date_utc}
        />
      </section>
    </BlurFade>
  )
}
