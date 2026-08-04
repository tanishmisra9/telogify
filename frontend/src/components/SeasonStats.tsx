import { BlurFade } from '@/components/BlurFade'
import { useAppSettled, useApi, type SeasonStats as SeasonStatsData, type WeekendSummary } from '@/lib/api'

const STATS = [
  { key: 'total_laps', label: 'Laps analysed', format: (v: number) => v.toLocaleString() },
  { key: 'total_km', label: 'Km ingested', format: (v: number) => Math.round(v).toLocaleString() },
] as const

// Landing-page proof-of-scale, below the live insight (not inside the countdown): two headline
// numbers in the same oversized mono treatment as the countdown numerals. "Current season" is
// derived the same way SeasonRedirect does (max year among ingested weekends), never hardcoded.
//
// Fetches immediately on mount regardless of `settled` (both requests here are among the ones
// useAppSettled() itself waits on); the reveal waits for settled so this lands in the same
// top-down cascade as Countdown/LiveInsight above it instead of popping in independently the
// moment its own (possibly faster) fetch happens to resolve.
export function SeasonStats() {
  const { data: weekends } = useApi<WeekendSummary[]>('/weekends')
  const years = (weekends ?? []).map((w) => w.year)
  const year = years.length > 0 ? Math.max(...years) : null

  const { data } = useApi<SeasonStatsData>(year != null ? `/season/${year}/stats` : null)
  const settled = useAppSettled()

  if (!data || !data.total_laps || !settled) return null

  return (
    <BlurFade delay={0.12}>
      <section className="mt-24 sm:mt-32">
        <div className="glass rounded-[--radius-panel] p-8 sm:p-12">
          <p className="kicker text-sm! text-accent">Telogify&apos;s telemetry so far</p>
          {/* mt-4, not mt-6: matches Countdown's kicker-to-heading gap and Insight's kicker's own
              mb-4, so the kicker-to-content rhythm is one shared token across all three panels. */}
          <div className="mt-4 grid grid-cols-1 gap-6 sm:grid-cols-2">
            {STATS.map(({ key, label, format }) => (
              <div key={key} className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                {/* Label sits beside the number, not below it, so the number is sized to leave
                    room for the widest label ("Laps analysed") next to it on one line even at
                    a narrow mobile width -- one step down from Countdown's own text-5xl, which
                    was sized for a bare digit pair with nothing beside it. */}
                <span className="num text-4xl leading-none tracking-tight text-ink tabular-nums sm:text-6xl xl:text-8xl">
                  {format(data[key])}
                </span>
                <span className="text-xs uppercase tracking-[0.15em] text-muted sm:text-sm">{label}</span>
              </div>
            ))}
          </div>
        </div>
      </section>
    </BlurFade>
  )
}
