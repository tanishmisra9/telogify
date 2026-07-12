import { useApi, type SeasonStats as SeasonStatsData, type WeekendSummary } from '@/lib/api'

const STATS = [
  { key: 'total_laps', label: 'Laps analysed', format: (v: number) => v.toLocaleString() },
  { key: 'total_km', label: 'Km of telemetry', format: (v: number) => Math.round(v).toLocaleString() },
] as const

// Landing-page proof-of-scale, below the live insight (not inside the countdown): two headline
// numbers in the same oversized mono treatment as the countdown numerals. "Current season" is
// derived the same way SeasonRedirect does (max year among ingested weekends), never hardcoded.
// No BlurFade here, same reasoning as LiveInsight: this mounts only after an async fetch
// resolves, and BlurFade's mount reveal doesn't fire reliably for that.
export function SeasonStats() {
  const { data: weekends } = useApi<WeekendSummary[]>('/weekends')
  const years = (weekends ?? []).map((w) => w.year)
  const year = years.length > 0 ? Math.max(...years) : null

  // ponytail: useApi always fetches on mount, so a placeholder path is used until `year`
  // resolves; it 404s harmlessly (data stays null) and re-fetches once the real path is known.
  const { data } = useApi<SeasonStatsData>(year != null ? `/season/${year}/stats` : '/season/0/stats')

  if (!data || !data.total_laps) return null

  return (
    <section className="mt-24 sm:mt-32">
      <div className="glass rounded-[--radius-panel] p-8 sm:p-12">
        <p className="kicker text-accent">Season {data.year} so far</p>
        <div className="mt-6 grid grid-cols-2 gap-4 sm:gap-6">
          {STATS.map(({ key, label, format }) => (
            <div key={key}>
              {/* One step down from Countdown's text-5xl base: these are up to 6-7 digit
                  figures (with thousands separators), not Countdown's fixed 2-digit values, so
                  the same base size overflows a 2-column mobile layout. */}
              <span className="num block text-3xl leading-none tracking-tight text-ink tabular-nums sm:text-6xl xl:text-8xl">
                {format(data[key])}
              </span>
              <span className="mt-2 block text-xs uppercase tracking-[0.2em] text-muted sm:text-sm">{label}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
