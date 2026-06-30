import { useParams } from 'react-router-dom'
import { BlurFade } from '@/components/BlurFade'
import { Insight } from '@/components/Insight'
import { PaceSpreadChart } from '@/components/PaceSpreadChart'
import { Results } from '@/components/Results'
import {
  useApi,
  type InsightItem,
  type PaceStint,
  type ResultRow,
  type WeekendSummary,
} from '@/lib/api'

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="mb-6 text-2xl font-semibold tracking-tight">{children}</h2>
}

export function WeekendPage() {
  const { year, round } = useParams()
  const base = `/weekends/${year}/${round}`

  const weekend = useApi<WeekendSummary>(base)
  const insights = useApi<InsightItem[]>(`${base}/insights`)
  const pace = useApi<{ stints: PaceStint[] }>(`${base}/pace`)
  const results = useApi<ResultRow[]>(`${base}/results`)

  const stints = pace.data?.stints ?? []

  return (
    <main className="mx-auto max-w-5xl px-6 py-16">
      <BlurFade>
        <p className="num text-sm text-accent">
          {year} · Round {round}
        </p>
        <h1 className="mt-2 text-5xl font-semibold tracking-tight">
          {weekend.data?.event_name ?? 'Weekend'}
        </h1>
        {weekend.data && (
          <p className="mt-2 text-muted">
            {weekend.data.circuit_name}
            {weekend.data.country ? ` · ${weekend.data.country}` : ''}
          </p>
        )}
      </BlurFade>

      <section className="mt-16">
        <SectionTitle>Your 3 insights</SectionTitle>
        {insights.loading && <p className="text-muted">Loading insights...</p>}
        {insights.data && insights.data.length === 0 && (
          <p className="text-muted">No insights yet. Run the pipeline for this weekend.</p>
        )}
        <div className="grid gap-4">
          {insights.data?.map((item, i) => (
            <BlurFade key={item.slot} delay={0.06 * i}>
              <Insight item={item} />
            </BlurFade>
          ))}
        </div>
      </section>

      <section className="mt-20">
        {/* Break out of the max-w-5xl column so the box plot gets real horizontal room. */}
        <div className="relative left-1/2 w-screen max-w-[95rem] -translate-x-1/2 px-6">
          <BlurFade>
            <PaceSpreadChart stints={stints} />
          </BlurFade>
        </div>
      </section>

      <section className="mt-20 max-w-2xl">
        <SectionTitle>Finishing order</SectionTitle>
        <BlurFade>
          <Results rows={results.data ?? []} />
        </BlurFade>
      </section>
    </main>
  )
}
