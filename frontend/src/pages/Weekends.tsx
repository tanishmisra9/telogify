import { Link } from 'react-router-dom'
import { BlurFade } from '@/components/BlurFade'
import { useApi, type WeekendSummary } from '@/lib/api'

export function Weekends() {
  const { data, loading, error } = useApi<WeekendSummary[]>('/weekends')
  const weekends = [...(data ?? [])].sort((a, b) => a.year - b.year || a.round - b.round)

  return (
    <main className="mx-auto max-w-[1312px] px-6 py-16 sm:py-24">
      <BlurFade>
        <div className="flex flex-col gap-1 border-b-2 border-ink pb-3 sm:flex-row sm:items-end sm:justify-between sm:gap-4">
          <h1 className="font-display text-6xl leading-[0.95] tracking-tight sm:text-7xl">
            Race weekends
          </h1>
          <span className="kicker whitespace-nowrap text-muted">{weekends.length} logged</span>
        </div>
      </BlurFade>

      {loading && <p className="mt-8 text-muted">Loading...</p>}
      {error && <p className="mt-8 text-muted">API offline.</p>}
      {data && data.length === 0 && <p className="mt-8 text-muted">No weekends processed yet.</p>}

      <ul>
        {weekends.map((w, i) => (
          <BlurFade key={w.id} delay={0.04 * i}>
            <li>
              <Link
                to={`/weekends/${w.year}/${w.round}`}
                aria-label={`${w.event_name}, round ${w.round}, ${w.year}`}
                className="group flex items-center gap-5 border-b border-border py-6 transition-colors hover:bg-surface"
              >
                <span className="num w-14 text-2xl font-bold text-accent">
                  {String(w.round).padStart(2, '0')}
                </span>
                <span className="flex-1">
                  <span className="block font-display text-2xl leading-tight transition-transform duration-200 group-hover:translate-x-1 sm:text-3xl">
                    {w.event_name}
                  </span>
                  <span className="mt-1 block text-sm text-muted">
                    {w.circuit_name}
                    {w.country ? ` · ${w.country}` : ''}
                  </span>
                </span>
                <span className="num text-sm text-muted">{w.year}</span>
                {/* Affordance: rows are links; the arrow arrives on hover in the same
                    direction the title nudges, so the whole row reads as one gesture. */}
                <span
                  aria-hidden
                  className="w-6 pr-1 text-xl text-accent opacity-0 transition-all duration-200 group-hover:translate-x-1 group-hover:opacity-100"
                >
                  →
                </span>
              </Link>
            </li>
          </BlurFade>
        ))}
      </ul>
    </main>
  )
}
