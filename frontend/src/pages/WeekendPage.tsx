import { useParams } from 'react-router-dom'
import { BlurFade } from '@/components/BlurFade'
import { DegradationChart } from '@/components/DegradationChart'
import { Insight } from '@/components/Insight'
import { PaceSpreadChart } from '@/components/PaceSpreadChart'
import { QualiCharacterTable } from '@/components/QualiCharacterTable'
import { Results } from '@/components/Results'
import { SectorBars } from '@/components/SectorBars'
import { TopSpeedBars } from '@/components/TopSpeedBars'
import {
  useApi,
  type DegradationData,
  type InsightItem,
  type PaceData,
  type QualiCharacterData,
  type ResultRow,
  type SectorsData,
  type SessionInfo,
  type TopSpeedsData,
  type WeekendSummary,
} from '@/lib/api'

const PRACTICE_CODES = ['FP1', 'FP2', 'FP3']
const QUALI_CODES = ['Q', 'SQ']

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-8 border-b-2 border-ink pb-3">
      <h2 className="font-display text-5xl leading-[0.95] tracking-tight sm:text-7xl">{children}</h2>
    </div>
  )
}

function Upcoming({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-[--radius-panel] border border-dashed border-border p-6 text-sm text-muted">
      {children}
    </p>
  )
}

export function WeekendPage() {
  const { year, round } = useParams()
  const base = `/weekends/${year}/${round}`

  const weekend = useApi<WeekendSummary>(base)
  const insights = useApi<InsightItem[]>(`${base}/insights`)
  const sessions = useApi<SessionInfo[]>(`${base}/sessions`)
  const sectors = useApi<SectorsData>(`${base}/sectors`)
  const topspeeds = useApi<TopSpeedsData>(`${base}/topspeeds`)
  const qualiCharacter = useApi<QualiCharacterData>(`${base}/quali-character`)
  const pace = useApi<PaceData>(`${base}/pace`)
  const degradation = useApi<DegradationData>(`${base}/degradation`)
  const results = useApi<ResultRow[]>(`${base}/results`)

  const present = new Set(sessions.data?.map((s) => s.session_type) ?? [])
  const practiceHappened = PRACTICE_CODES.some((c) => present.has(c))
  const qualiHappened = QUALI_CODES.some((c) => present.has(c))
  const raceHappened = present.has('R')
  const sessionsLoaded = !sessions.loading

  return (
    <main className="py-16">
      {/* Narrower reading column: hero + the 3 insights. */}
      <div className="mx-auto max-w-5xl px-6">
        <BlurFade>
          <p className="kicker text-accent">
            {year} · Round {round}
          </p>
          <h1 className="mt-3 font-display text-6xl leading-[0.95] tracking-tight sm:text-8xl">
            {weekend.data?.event_name ?? 'Weekend'}
          </h1>
          {weekend.data && <p className="mt-3 text-lg text-muted">{weekend.data.circuit_name}</p>}
        </BlurFade>

        <section className="mt-16">
          <SectionTitle>Your three insights</SectionTitle>
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
      </div>

      {/* Wide column: every analysis block shares this same edge, so sections stay
          aligned with each other as you scroll instead of jumping between widths. */}
      <div className="mx-auto max-w-[1312px] px-6">
        <section className="mt-20">
          <SectionTitle>Practice</SectionTitle>
          {!sessionsLoaded ? (
            <p className="text-sm text-muted">Loading...</p>
          ) : !practiceHappened ? (
            <Upcoming>Practice hasn't run yet. Best sectors and top speeds appear here once it has.</Upcoming>
          ) : (
            <div className="grid gap-6">
              <BlurFade>{sectors.data && <SectorBars data={sectors.data} />}</BlurFade>
              <BlurFade delay={0.06}>{topspeeds.data && <TopSpeedBars data={topspeeds.data} />}</BlurFade>
            </div>
          )}
        </section>

        <section className="mt-20">
          <SectionTitle>Qualifying</SectionTitle>
          {!sessionsLoaded ? (
            <p className="text-sm text-muted">Loading...</p>
          ) : !qualiHappened ? (
            <Upcoming>Qualifying hasn't run yet. The car-character comparison appears here once it has.</Upcoming>
          ) : (
            <BlurFade>{qualiCharacter.data && <QualiCharacterTable data={qualiCharacter.data} />}</BlurFade>
          )}
        </section>

        <section className="mt-20">
          <SectionTitle>Race</SectionTitle>
          {!sessionsLoaded ? (
            <p className="text-sm text-muted">Loading...</p>
          ) : !raceHappened ? (
            <Upcoming>Race day hasn't happened yet. Pace ranking, tyre degradation and the
              finishing order appear here once it has.</Upcoming>
          ) : (
            <div className="grid gap-6">
              <BlurFade>
                <PaceSpreadChart pace={pace.data ?? { drivers: [], constructors: [], stop_counts: {}, stop_count_spread: 0 }} />
              </BlurFade>
              <BlurFade delay={0.06}>{degradation.data && <DegradationChart data={degradation.data} />}</BlurFade>
              <BlurFade delay={0.1}>
                <div className="glass rounded-[--radius-panel] p-6">
                  <h2 className="mb-4 text-4xl font-semibold tracking-tight sm:text-5xl">Finishing order</h2>
                  <Results rows={results.data ?? []} />
                </div>
              </BlurFade>
            </div>
          )}
        </section>
      </div>
    </main>
  )
}
