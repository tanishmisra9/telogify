import { useParams } from 'react-router-dom'
import { BarChart } from '@/components/BarChart'
import { BlurFade } from '@/components/BlurFade'
import { DegradationChart } from '@/components/DegradationChart'
import { Insight } from '@/components/Insight'
import { PaceSpreadChart } from '@/components/PaceSpreadChart'
import { QualiCharacterTable } from '@/components/QualiCharacterTable'
import { Results } from '@/components/Results'
import { SectionTitle } from '@/components/SectionTitle'
import { Skeleton, SkeletonCard } from '@/components/Skeleton'
import {
  useApi,
  type DegradationData,
  type InsightItem,
  type PaceData,
  type QualiCharacterData,
  type ResultRow,
  type SectorBestRow,
  type SectorsData,
  type SessionInfo,
  type TopSpeedsData,
  type WeekendSummary,
} from '@/lib/api'

const PRACTICE_CODES = ['FP1', 'FP2', 'FP3']

function PracticeSectorChart({ sector, rows }: { sector: number; rows: SectorBestRow[] }) {
  const sorted = rows.filter((r) => r.sector === sector).sort((a, b) => a.best_time_s - b.best_time_s)
  if (sorted.length === 0) return null

  const fastest = sorted[0].best_time_s
  const bars = sorted.map((r) => ({
    id: r.driver,
    label: r.driver,
    value: r.best_time_s - fastest,
    displayValue: r.best_time_s,
    team: r.constructor,
  }))

  return (
    <div>
      <h3 className="mb-2 text-[1.35rem] font-semibold text-ink">Sector {sector}</h3>
      <BarChart rows={bars} formatValue={(v) => `${v.toFixed(3)}s`} />
    </div>
  )
}

function PracticeSectors({ data }: { data: SectorsData }) {
  if (data.drivers.length === 0) {
    return <p className="text-sm text-muted">No practice sector data yet.</p>
  }

  return (
    <div className="glass rounded-[--radius-panel] p-6">
      <h2 className="font-display text-[2.025rem] font-semibold tracking-tight sm:text-[2.7rem]">Best sectors</h2>
      <div className="mt-5 grid gap-8">
        {[1, 2, 3].map((sector) => (
          <PracticeSectorChart key={sector} sector={sector} rows={data.drivers} />
        ))}
      </div>
      <p className="mt-2 text-xs text-muted">
        Indicative: practice fuel loads and engine modes vary between runs, so this is a read on
        where time is, not a verdict. Bars are each driver's gap to the fastest sector time.
      </p>
    </div>
  )
}

function PracticeTopSpeeds({ data }: { data: TopSpeedsData }) {
  if (data.drivers.length === 0) {
    return <p className="text-sm text-muted">No practice top-speed data yet.</p>
  }

  const sorted = [...data.drivers].sort((a, b) => b.max_speed_kmh - a.max_speed_kmh)
  const bars = sorted.map((r) => ({
    id: r.driver,
    label: r.driver,
    value: r.max_speed_kmh,
    team: r.constructor,
  }))
  const domainMin = Math.min(...sorted.map((r) => r.max_speed_kmh)) - 6

  return (
    <div className="glass rounded-[--radius-panel] p-6">
      <h2 className="font-display text-[2.025rem] font-semibold tracking-tight sm:text-[2.7rem]">Top speeds (km/h)</h2>
      <div className="mt-5">
        <BarChart rows={bars} formatValue={(v) => v.toFixed(0)} domainMin={domainMin} />
      </div>
      <p className="mt-2 text-xs text-muted">
        Indicative: engine modes and fuel loads vary between practice runs, so a deficit here may
        be a mode choice rather than a true weakness.
      </p>
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

// Reserve the practice block's footprint so the page doesn't grow when the two charts land.
function PracticeSkeleton() {
  return (
    <div className="grid gap-6">
      <SkeletonCard className="min-h-[560px]" />
      <SkeletonCard className="min-h-[300px]" />
    </div>
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
  const sprintPace = useApi<PaceData>(`${base}/pace?session=SPRINT`)
  const pace = useApi<PaceData>(`${base}/pace`)
  const degradation = useApi<DegradationData>(`${base}/degradation`)
  const results = useApi<ResultRow[]>(`${base}/results`)

  const present = new Set(sessions.data?.map((s) => s.session_type) ?? [])
  const practiceHappened = PRACTICE_CODES.some((c) => present.has(c)) || present.has('SQ')
  const sprintHappened = present.has('SPRINT')
  const qualiHappened = present.has('Q')
  const raceHappened = present.has('R')
  const sessionsLoaded = !sessions.loading

  if (weekend.error || sessions.error) {
    return (
      <main className="mx-auto max-w-[1312px] px-6 py-16">
        <p className="text-muted">API offline.</p>
      </main>
    )
  }

  return (
    <main className="mx-auto max-w-[1312px] px-6 py-16">
      <BlurFade>
        <p className="kicker text-accent">
          {year} · Round {round}
        </p>
        {weekend.data ? (
          <>
            <h1 className="mt-3 font-display text-[3.375rem] leading-[0.95] tracking-tight sm:text-[5.4rem]">
              {weekend.data.event_name}
            </h1>
            <p className="mt-3 text-lg text-muted">{weekend.data.circuit_name}</p>
          </>
        ) : (
          <>
            <Skeleton className="mt-3 h-14 w-2/3 sm:h-20" />
            <Skeleton className="mt-3 h-6 w-40" />
          </>
        )}
      </BlurFade>

      <section className="mt-16">
        <SectionTitle>Your three insights</SectionTitle>
        {insights.loading ? (
          <div className="grid max-w-5xl gap-4">
            {[0, 1, 2].map((i) => (
              <SkeletonCard key={i} className="min-h-[150px]" />
            ))}
          </div>
        ) : !insights.data || insights.data.length === 0 ? (
          <p className="text-muted">No insights yet. Run the pipeline for this weekend.</p>
        ) : (
          <div className="max-w-5xl">
            <div className="grid gap-4">
              {insights.data.map((item, i) => (
                <BlurFade key={item.slot} delay={0.06 * i}>
                  <Insight item={item} />
                </BlurFade>
              ))}
            </div>
            <BlurFade delay={0.06 * insights.data.length + 0.06}>
              <div className="glass mt-6 rounded-[--radius-panel] p-6">
                <p className="font-display text-[1.35rem] font-semibold tracking-tight text-ink">How these are made</p>
                <p className="mt-3 text-sm leading-relaxed text-muted">
                  Every figure above is read from official timing and car telemetry, then computed into a
                  database by deterministic analysis, with nothing estimated. An agent then picks the three
                  findings you could not get from the timing screen, favouring a weakness in one area
                  (qualifying, straight-line speed, tyre wear, corner grip) that explains an outcome in another.
                  Each number is traceable back to the exact data it came from.
                </p>
              </div>
            </BlurFade>
          </div>
        )}
      </section>

      <section className="mt-20">
        <SectionTitle>Practice</SectionTitle>
        {!sessionsLoaded ? (
          <PracticeSkeleton />
        ) : !practiceHappened ? (
          <Upcoming>Practice hasn't run yet. Best sectors and top speeds appear here once it has.</Upcoming>
        ) : (
          <div className="grid gap-6">
            {sectors.data ? (
              <BlurFade>
                <PracticeSectors data={sectors.data} />
              </BlurFade>
            ) : (
              <SkeletonCard className="min-h-[560px]" />
            )}
            {topspeeds.data ? (
              <BlurFade delay={0.06}>
                <PracticeTopSpeeds data={topspeeds.data} />
              </BlurFade>
            ) : (
              <SkeletonCard className="min-h-[300px]" />
            )}
          </div>
        )}
      </section>

      {sprintHappened && (
        <section className="mt-20">
          <SectionTitle>Sprint</SectionTitle>
          {sprintPace.data ? (
            <BlurFade>
              <PaceSpreadChart pace={sprintPace.data} />
            </BlurFade>
          ) : (
            <SkeletonCard className="min-h-[600px]" />
          )}
        </section>
      )}

      <section className="mt-20">
        <SectionTitle>Qualifying</SectionTitle>
        {!sessionsLoaded ? (
          <SkeletonCard className="min-h-[520px]" />
        ) : !qualiHappened ? (
          <Upcoming>
            Qualifying hasn't run yet. The car-character comparison appears here once it has.
          </Upcoming>
        ) : qualiCharacter.data ? (
          <BlurFade>
            <QualiCharacterTable data={qualiCharacter.data} />
          </BlurFade>
        ) : (
          <SkeletonCard className="min-h-[520px]" />
        )}
      </section>

      <section className="mt-20">
        <SectionTitle>Race</SectionTitle>
        {!sessionsLoaded ? (
          <div className="grid gap-6">
            <SkeletonCard className="min-h-[600px]" />
            <SkeletonCard className="min-h-[540px]" />
            <SkeletonCard className="min-h-[400px]" />
          </div>
        ) : !raceHappened ? (
          <Upcoming>
            Race day hasn't happened yet. Pace ranking, tyre degradation and the finishing order appear here once
            it has.
          </Upcoming>
        ) : (
          <div className="grid gap-6">
            {pace.data ? (
              <BlurFade>
                <PaceSpreadChart pace={pace.data} />
              </BlurFade>
            ) : (
              <SkeletonCard className="min-h-[600px]" />
            )}
            {degradation.data ? (
              <BlurFade delay={0.06}>
                <DegradationChart data={degradation.data} />
              </BlurFade>
            ) : (
              <SkeletonCard className="min-h-[540px]" />
            )}
            {results.data ? (
              <BlurFade delay={0.1}>
                <div className="glass mx-auto w-full max-w-4xl rounded-[--radius-panel] p-6 sm:p-8">
                  <h3 className="mb-6 font-display text-[2.025rem] font-semibold tracking-tight sm:text-[2.7rem]">
                    Finishing order
                  </h3>
                  <Results rows={results.data} />
                </div>
              </BlurFade>
            ) : (
              <SkeletonCard className="mx-auto min-h-[400px] w-full max-w-4xl" />
            )}
          </div>
        )}
      </section>
    </main>
  )
}
