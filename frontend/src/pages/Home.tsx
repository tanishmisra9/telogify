import { Link } from 'react-router-dom'
import { BlurFade } from '@/components/BlurFade'
import { useApi, type WeekendSummary } from '@/lib/api'

export function Home() {
  const { data, loading, error } = useApi<WeekendSummary[]>('/weekends')

  return (
    <main className="mx-auto max-w-5xl px-6 py-16">
      <BlurFade>
        <h1 className="text-5xl font-semibold tracking-tight">Race weekends</h1>
        <p className="mt-3 max-w-xl text-muted">
          Three telemetry insights per weekend, every number grounded in the data.
        </p>
      </BlurFade>

      {loading && <p className="mt-12 text-muted">Loading...</p>}
      {error && <p className="mt-12 text-muted">Could not reach the API.</p>}
      {data && data.length === 0 && (
        <p className="mt-12 text-muted">No weekends processed yet.</p>
      )}

      <ul className="mt-12 divide-y divide-border">
        {data?.map((w, i) => (
          <BlurFade key={w.id} delay={0.04 * i}>
            <li>
              <Link
                to={`/weekends/${w.year}/${w.round}`}
                className="group -mx-4 flex items-baseline gap-5 rounded-lg px-4 py-5 transition-colors hover:bg-surface/50"
              >
                <span className="num w-12 text-sm text-accent">
                  R{String(w.round).padStart(2, '0')}
                </span>
                <span className="flex-1">
                  <span className="block text-lg transition-colors group-hover:text-accent">
                    {w.event_name}
                  </span>
                  <span className="block text-sm text-muted">
                    {w.circuit_name}
                    {w.country ? ` · ${w.country}` : ''}
                  </span>
                </span>
                <span className="num text-sm text-muted">{w.year}</span>
              </Link>
            </li>
          </BlurFade>
        ))}
      </ul>
    </main>
  )
}
