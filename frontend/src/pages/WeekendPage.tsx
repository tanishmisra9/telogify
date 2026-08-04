import { useEffect, useState } from 'react'
import { AnimatePresence, m } from 'framer-motion'
import { Link, useParams } from 'react-router-dom'
import { BackToTopButton } from '@/components/BackToTopButton'
import { BarChart } from '@/components/BarChart'
import { BlurFade } from '@/components/BlurFade'
import { ChartTabs } from '@/components/ChartTabs'
import { CountdownPanel } from '@/components/CountdownPanel'
import { DegradationChart } from '@/components/DegradationChart'
import { DesktopOnlyNote } from '@/components/DesktopOnlyNote'
import { FightToPoleChart } from '@/components/FightToPoleChart'
import { Insight } from '@/components/Insight'
import { LoadingSwap } from '@/components/LoadingSwap'
import { PaceSpreadChart } from '@/components/PaceSpreadChart'
import { QualiCharacterTable } from '@/components/QualiCharacterTable'
import { Results } from '@/components/Results'
import { ScrollReveal } from '@/components/ScrollReveal'
import { SectionNav, type NavSection } from '@/components/SectionNav'
import { SectionTitle } from '@/components/SectionTitle'
import { Skeleton, SkeletonCard } from '@/components/Skeleton'
import { Tooltip } from '@/components/Tooltip'
import { expandTransition } from '@/lib/motion'
import {
  useApi,
  type DegradationData,
  type InsightItem,
  type PaceData,
  type QualiCharacterData,
  type QualiInsightItem,
  type QualiTraceData,
  type ResultRow,
  type SectorBestRow,
  type SectorsData,
  type SessionInfo,
  type TopSpeedRow,
  type TopSpeedsData,
  type WeekendSummary,
} from '@/lib/api'

const PRACTICE_CODES = ['FP1', 'FP2', 'FP3']

function formatSessionDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })
}

function PracticeSectorChart({ sector, rows }: { sector: number; rows: SectorBestRow[] }) {
  const sorted = rows.filter((r) => r.sector === sector).sort((a, b) => a.best_time_s - b.best_time_s)
  if (sorted.length === 0) return null

  const fastest = sorted[0].best_time_s
  const bars = sorted.map((r, i) => ({
    id: r.driver,
    label: r.driver,
    // No driver can be faster than `fastest` by definition; clamp away the floating-point noise
    // that otherwise shows up as e.g. "-0.000s" on the leader's own row or the axis's zero tick.
    value: Math.max(0, r.best_time_s - fastest),
    // Only the leader shows its absolute time; everyone else falls back to `value` (the gap).
    displayValue: i === 0 ? r.best_time_s : undefined,
    team: r.constructor,
  }))

  return (
    <div>
      <h3 className="mb-2 text-[1.35rem] font-semibold text-ink">Sector {sector}</h3>
      <BarChart rows={bars} formatValue={(v, row) => (row.displayValue != null ? `${v.toFixed(3)}s` : `+${v.toFixed(3)}s`)} />
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
      <div className="mt-5 grid grid-cols-[minmax(0,1fr)] gap-8">
        {[1, 2, 3].map((sector) => (
          <PracticeSectorChart key={sector} sector={sector} rows={data.drivers} />
        ))}
      </div>
      <p className="mt-2 text-sm text-muted">
        Indicative: practice fuel loads and engine modes vary between runs, so this is a read on
        where time is, not a verdict. Bars are each driver's gap to the fastest sector time.
      </p>
    </div>
  )
}

function PracticeTopSpeeds({ data }: { data: TopSpeedsData }) {
  // Both units are already in the payload (max_speed_mph is computed backend-side), so the
  // toggle is pure presentation. Same ChartTabs language as the compound/metric switchers.
  const [unit, setUnit] = useState<'kmh' | 'mph'>('kmh')

  if (data.drivers.length === 0) {
    return <p className="text-sm text-muted">No practice top-speed data yet.</p>
  }

  const speedOf = (r: TopSpeedRow) => (unit === 'mph' ? r.max_speed_mph : r.max_speed_kmh)
  const unitLabel = unit === 'mph' ? 'mph' : 'km/h'
  const sorted = [...data.drivers].sort((a, b) => speedOf(b) - speedOf(a))
  const bars = sorted.map((r) => ({
    id: r.driver,
    label: r.driver,
    value: speedOf(r),
    team: r.constructor,
  }))
  // The same visual headroom below the slowest bar in either unit (6 km/h ≈ 4 mph).
  const domainMin = Math.min(...sorted.map(speedOf)) - (unit === 'mph' ? 4 : 6)

  return (
    <div className="glass rounded-[--radius-panel] p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-[2.025rem] font-semibold tracking-tight sm:text-[2.7rem]">Top speeds</h2>
        <ChartTabs
          ariaLabel="Speed unit"
          active={unit}
          onChange={setUnit}
          tabs={[
            { value: 'kmh', label: 'KM/H', hint: 'kilometres per hour' },
            { value: 'mph', label: 'MPH', hint: 'miles per hour' },
          ]}
        />
      </div>
      <div className="mt-5">
        <BarChart
          rows={bars}
          // Axis ticks call this with a synthetic row (id: '', see BarChart's own tick
          // comment) and are left-anchored inside a fixed 60px margin: appending the unit
          // there overflows the SVG's left edge and gets clipped ("331 km/h" -> "31 km/h").
          // The KM/H/MPH toggle already states the unit, so ticks stay bare; only the hover
          // callout (which has its own sized panel) shows the full "331 km/h".
          formatValue={(v, row) => (row?.id === '' ? v.toFixed(0) : `${v.toFixed(0)} ${unitLabel}`)}
          domainMin={domainMin}
        />
      </div>
      <p className="mt-2 text-sm text-muted">
        Indicative: engine modes and fuel loads vary between practice runs, so a deficit here may
        be a mode choice rather than a true weakness.
      </p>
    </div>
  )
}

const METHODOLOGY_SEEN_KEY = 'telogify:seen-methodology'

function MethodologyDisclosure() {
  const [open, setOpen] = useState(() => {
    try {
      return localStorage.getItem(METHODOLOGY_SEEN_KEY) === null
    } catch {
      return true
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(METHODOLOGY_SEEN_KEY, '1')
    } catch {
      /* private mode: disclosure just defaults open every visit */
    }
  }, [])

  return (
    <div className="glass mt-6 rounded-[--radius-panel] p-6">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-4 text-left"
      >
        <p className="font-display text-[1.35rem] font-semibold tracking-tight text-ink">How these are made</p>
        <Tooltip label={open ? 'Collapse' : 'Expand'}>
          <span className="-m-3 flex shrink-0 items-center justify-center rounded-full p-3 text-muted transition-colors hover:bg-accent/10 hover:text-accent active:bg-accent/20">
            <m.svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden
              animate={{ rotate: open ? 180 : 0 }}
              transition={expandTransition}
            >
              <path d="m6 9 6 6 6-6" />
            </m.svg>
          </span>
        </Tooltip>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <m.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={expandTransition}
            className="overflow-hidden"
          >
            <p className="mt-3 text-sm leading-relaxed text-muted">
              Every figure above is read from official timing and car telemetry, then computed into a
              database by deterministic analysis, with nothing estimated. An agent then picks the three
              findings you could not get from the timing screen, favouring a weakness in one area
              (qualifying, straight-line speed, tyre wear, corner grip) that explains an outcome in another.
              Each number is traceable back to the exact data it came from.
            </p>
          </m.div>
        )}
      </AnimatePresence>
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

// One gate shared by Practice/Sprint/Qualifying/Race: a single countdown panel while the next
// relevant session hasn't started, a single "No data yet." panel once it has but nothing's been
// computed, and otherwise the section's real charts (unchanged, each keeping its own loading
// fallback for the ordinary in-flight case). Replaces what used to be a skeleton card PER chart
// (each with its own disclaimer footer) whenever there was really just one thing to say.
// Wrapped in LoadingSwap so the `!sessionsLoaded` placeholder crossfades into whichever resolved
// state follows (countdown/upcoming/children) instead of hard-swapping and leaving a gap.
function SessionGate({
  sessionsLoaded,
  loading,
  target,
  label,
  happened,
  noData,
  children,
  delay,
}: {
  sessionsLoaded: boolean
  loading: React.ReactNode
  target: SessionInfo | null
  label: string
  happened: boolean
  noData: boolean
  children: React.ReactNode
  // Matched to this section's own SectionTitle delay, so its loading placeholder blur-fades in
  // alongside its heading instead of popping in crisp while the heading is still mid-reveal.
  delay: number
}) {
  const resolved = (() => {
    if (!happened) {
      if (target?.status === 'unavailable') {
        return <Upcoming>There was an issue with this session.</Upcoming>
      }
      // CountdownPanel has no "expired" state of its own (it clamps at 00:00:00:00 and just
      // sits there), so only render it while the target is genuinely still in the future. Once
      // a session's scheduled start has passed but it isn't ingested yet (and isn't stale enough
      // to be "unavailable"), that's the same situation as noData below -- the session ran, the
      // data just isn't in yet -- so reuse that copy instead of a dead countdown.
      if (target?.date_utc && new Date(target.date_utc).getTime() > Date.now()) {
        return (
          <CountdownPanel
            kicker="Coming up"
            subtitle={formatSessionDate(target.date_utc)}
            targetIso={target.date_utc}
            compact
          />
        )
      }
      if (target?.date_utc) return <Upcoming>No data yet.</Upcoming>
      return <Upcoming>{label} hasn&apos;t happened yet.</Upcoming>
    }
    if (noData) return <Upcoming>No data yet.</Upcoming>
    return <>{children}</>
  })()

  return (
    <LoadingSwap loading={!sessionsLoaded} delay={delay} placeholder={loading}>
      {resolved}
    </LoadingSwap>
  )
}

function FightToPoleDesktopNote() {
  return (
    <DesktopOnlyNote>
      The fight to pole: scrub through every driver&apos;s qualifying lap telemetry side by
      side. Open this weekend on a larger screen to use it.
    </DesktopOnlyNote>
  )
}

// Reserve the practice block's footprint so the page doesn't grow when the two charts land.
function PracticeSkeleton() {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
      <SkeletonCard label="Best sectors" className="min-h-[560px]" />
      <SkeletonCard label="Top speeds" className="min-h-[300px]" />
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
  const qualiInsights = useApi<QualiInsightItem[]>(`${base}/quali-insights`)
  const qualiTrace = useApi<QualiTraceData>(`${base}/quali-trace`)
  const sprintPace = useApi<PaceData>(`${base}/pace?session=SPRINT`)
  const pace = useApi<PaceData>(`${base}/pace`)
  const degradation = useApi<DegradationData>(`${base}/degradation`)
  const results = useApi<ResultRow[]>(`${base}/results`)

  // One readiness signal for the header + insights block, so they blur in together the moment
  // both are ready instead of each popping in independently as its own fetch happens to resolve.
  const topReady = weekend.data !== null && !insights.loading

  // Every session on the weekend's calendar, ingested or not (see /sessions), so "upcoming"
  // sections can count down before they've ever been ingested, not just show a blank skeleton.
  const sessionByType = new Map((sessions.data ?? []).map((s) => [s.session_type, s]))
  const isIngested = (code: string) => sessionByType.get(code)?.status === 'loaded'
  const isSprintWeekend = sessionByType.has('SQ') || sessionByType.has('SPRINT')
  const practiceHappened = [...PRACTICE_CODES, 'SQ'].some(isIngested)
  const sprintHappened = isIngested('SPRINT')
  const qualiHappened = isIngested('Q')
  const raceHappened = isIngested('R')
  const sessionsLoaded = !sessions.loading

  // The earliest not-yet-ingested session among `types`, for a section's countdown target; null
  // once all of them are in (nothing left to count down to).
  const nextSessionTarget = (types: string[]): SessionInfo | null => {
    for (const t of types) {
      const s = sessionByType.get(t)
      if (s && s.status !== 'loaded') return s
    }
    return null
  }

  const practiceNoData =
    !sectors.loading &&
    !topspeeds.loading &&
    (!sectors.data || sectors.data.drivers.length === 0) &&
    (!topspeeds.data || topspeeds.data.drivers.length === 0)
  const sprintNoData = !sprintPace.loading && (!sprintPace.data || sprintPace.data.drivers.length === 0)
  const qualiNoData =
    !qualiCharacter.loading &&
    !qualiTrace.loading &&
    (!qualiCharacter.data || qualiCharacter.data.rows.length === 0) &&
    (!qualiTrace.data || qualiTrace.data.drivers.length === 0)
  const raceNoData =
    !pace.loading &&
    !degradation.loading &&
    !results.loading &&
    (!pace.data || pace.data.drivers.length === 0) &&
    (!degradation.data || degradation.data.points.length === 0) &&
    (!results.data || results.data.length === 0)

  const navSections: NavSection[] = [
    topReady && insights.data && insights.data.length > 0 ? { id: 'insights', label: 'Insights' } : null,
    sessionsLoaded ? { id: 'practice', label: 'Practice' } : null,
    sessionsLoaded && isSprintWeekend ? { id: 'sprint', label: 'Sprint' } : null,
    sessionsLoaded ? { id: 'qualifying', label: 'Qualifying' } : null,
    sessionsLoaded ? { id: 'race', label: 'Race' } : null,
  ].filter((s): s is NavSection => s !== null)

  if (weekend.error || sessions.error) {
    // apiGet throws `${status}`, so a 404 (weekend not ingested yet) is distinguishable from a
    // real network/server failure instead of both reading as one alarming "API offline."
    const notFound = weekend.error?.includes('404') || sessions.error?.includes('404')
    return (
      <main className="mx-auto max-w-[1312px] px-6 py-16">
        <p className="text-muted">
          {notFound ? "This weekend hasn't been analysed yet." : "Couldn't reach the API. Try again shortly."}
        </p>
        <Link to="/weekends" className="mt-4 inline-block text-accent underline">
          Back to weekends
        </Link>
      </main>
    )
  }

  return (
    <main className="mx-auto max-w-[1312px] px-6 py-16">
      <SectionNav sections={navSections} />
      {/* Hero text and the "Your three insights" section share one readiness signal (topReady)
          so they land together, but are two separate LoadingSwaps (rather than one shared
          BlurFade) so the insights SectionTitle gets its own independent reveal instead of
          nesting a second blur-fade inside the hero's -- nested identical filter transitions
          compound into a heavier blur than either alone. */}
      <LoadingSwap
        loading={!topReady}
        placeholder={
          // Mirrors the hero's actual structure (back-arrow, kicker, h1, subtitle) rather than
          // padding one bar out to a guessed total -- stays in sync if the hero changes, and
          // reads as a hero instead of a slab. Heights measured off the real elements: h1 wraps
          // to two lines below the `sm` breakpoint even for short names ("Hungarian Grand Prix"
          // -> 103px), one line at sm+ (82px) since the wider column fits any event name. The
          // first bar is 29px, not the back-arrow's own 22px box: summing each element's own
          // height + margin under-measured the real total by a constant 7px at both viewports
          // (identical regardless of h1 height), which points to margin interaction around the
          // negative-margin back-link that direct box measurements didn't capture -- absorbed
          // here since it isn't proportional to anything else in the stack.
          <>
            <Skeleton className="h-[29px] w-10" />
            <Skeleton className="mt-6 h-6 w-40" />
            <Skeleton className="mt-3 h-[103px] w-2/3 sm:h-[82px]" />
            <Skeleton className="mt-3 h-7 w-52" />
          </>
        }
      >
        <Tooltip label="Back to weekends" align="start">
          <Link
            to="/weekends"
            aria-label="Back to weekends"
            // Icon-only: the label lives in the tooltip. -m-3 + p-3 gives the same 40px
            // circular hover/active target as the copy/collapse buttons.
            className="-m-3 inline-flex shrink-0 items-center justify-center rounded-full p-3 text-muted transition-colors hover:bg-accent/10 hover:text-accent active:bg-accent/20"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="m15 18-6-6 6-6" />
            </svg>
          </Link>
        </Tooltip>
        <p className="kicker mt-6 text-base! text-accent">
          {year} · Round {round}
        </p>
        <h1 className="mt-3 font-display text-[3.375rem] leading-[0.95] tracking-tight sm:text-[5.4rem]">
          {weekend.data?.event_name}
        </h1>
        <p className="mt-3 text-lg text-muted">
          {weekend.data?.circuit_name}
          {weekend.data?.country ? `, ${weekend.data.country}` : ''}
          {weekend.data?.race_laps ? ` · ${weekend.data.race_laps} laps` : ''}
        </p>
      </LoadingSwap>

      <section id="insights" className="mt-16 scroll-mt-24">
        <LoadingSwap
          loading={!topReady}
          delay={0.08}
          placeholder={
            // Heading bar first, matching SectionTitle's real footprint (mb-8 border-b-2 pb-3,
            // 52px mobile / 90px desktop measured) -- moved inside this LoadingSwap rather than
            // rendered as a sibling above it: AnimatePresence keeps placeholder and content BOTH
            // mounted during the crossfade (stacked in one grid cell), so a title rendered outside
            // the swap would add its own height on top of the placeholder's, producing a fresh
            // snap at the exact moment the hero-placeholder fix above removes one.
            <>
              <Skeleton className="mb-8 h-[52px] sm:h-[90px]" />
              {/* Measured, not estimated. These panels have no `defaultOpen` override (unlike the
                  Season page's Deployment panels) so they're always open, on every viewport -- the
                  mobile/desktop difference here is purely from the narrower column wrapping the
                  same open prose across more lines (measured 590-673px mobile vs 230px desktop). */}
              <div className="grid gap-4">
                {[0, 1, 2].map((i) => (
                  <SkeletonCard key={i} className="min-h-[650px] md:min-h-[240px]" />
                ))}
              </div>
              <Skeleton className="mt-6 min-h-[85px]" />
            </>
          }
        >
          <SectionTitle delay={0.08}>Your three insights</SectionTitle>
          {!insights.data || insights.data.length === 0 ? (
            sessionsLoaded && !raceHappened ? (
              <Upcoming>No insights yet.</Upcoming>
            ) : (
              <p className="text-muted">No insights yet. Run the pipeline for this weekend.</p>
            )
          ) : (
            // Full section width, matching the heading above (same call as the Season page's
            // Deployment panels): the narrower max-w-5xl just left-aligned with dead space
            // beside it on wider screens.
            <div>
              <div className="grid gap-4">
                {insights.data.map((item, i) => (
                  // Offset past the heading's own 0.08 delay (+ a 0.06 gap) so a card's reveal
                  // never starts before the heading above it has -- otherwise the fixed 0.06*i
                  // stagger would put card 0 at delay 0, ahead of its own section heading.
                  <BlurFade key={item.slot} delay={0.08 + 0.06 * (i + 1)}>
                    <Insight item={item} collapsible contextLabel={weekend.data?.event_name ?? ''} />
                  </BlurFade>
                ))}
              </div>
              <BlurFade delay={0.08 + 0.06 * (insights.data.length + 1) + 0.06}>
                <MethodologyDisclosure />
              </BlurFade>
            </div>
          )}
        </LoadingSwap>
      </section>

      <section id="practice" className="mt-20 scroll-mt-24">
        <SectionTitle delay={0.16}>Practice</SectionTitle>
        <SessionGate
          sessionsLoaded={sessionsLoaded}
          delay={0.16}
          loading={<PracticeSkeleton />}
          target={nextSessionTarget(['FP1'])}
          label="Practice"
          happened={practiceHappened}
          noData={practiceNoData}
        >
          <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
            {sectors.data ? (
              <ScrollReveal>
                <PracticeSectors data={sectors.data} />
              </ScrollReveal>
            ) : (
              <SkeletonCard label="Best sectors" className="min-h-[560px]" />
            )}
            {topspeeds.data ? (
              <ScrollReveal delay={0.06}>
                <PracticeTopSpeeds data={topspeeds.data} />
              </ScrollReveal>
            ) : (
              <SkeletonCard label="Top speeds" className="min-h-[300px]" />
            )}
          </div>
        </SessionGate>
      </section>

      {isSprintWeekend && (
        <section id="sprint" className="mt-20 scroll-mt-24">
          <SectionTitle delay={0.24}>Sprint</SectionTitle>
          <SessionGate
            sessionsLoaded={sessionsLoaded}
            delay={0.24}
            loading={<SkeletonCard label="Pace spread" className="min-h-[600px]" />}
            target={nextSessionTarget(['SQ', 'SPRINT'])}
            label="Sprint"
            happened={sprintHappened}
            noData={sprintNoData}
          >
            {sprintPace.data ? (
              <ScrollReveal>
                <PaceSpreadChart pace={sprintPace.data} />
              </ScrollReveal>
            ) : (
              <SkeletonCard label="Pace spread" className="min-h-[600px]" />
            )}
          </SessionGate>
        </section>
      )}

      <section id="qualifying" className="mt-20 scroll-mt-24">
        <SectionTitle delay={0.32}>Qualifying</SectionTitle>
        <SessionGate
          sessionsLoaded={sessionsLoaded}
          delay={0.32}
          loading={
            <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
              <SkeletonCard label="Car character" className="min-h-[520px]" />
              <SkeletonCard label="The fight to pole" className="hidden min-h-[640px] md:block" />
              <FightToPoleDesktopNote />
            </div>
          }
          target={nextSessionTarget(['Q'])}
          label="Qualifying"
          happened={qualiHappened}
          noData={qualiNoData}
        >
          <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
            {qualiCharacter.data ? (
              <ScrollReveal>
                <QualiCharacterTable data={qualiCharacter.data} insights={qualiInsights.data ?? []} />
              </ScrollReveal>
            ) : (
              <SkeletonCard label="Car character" className="min-h-[520px]" />
            )}
            <div className="hidden md:block">
              {qualiTrace.data ? (
                <ScrollReveal delay={0.06}>
                  <FightToPoleChart data={qualiTrace.data} />
                </ScrollReveal>
              ) : (
                <SkeletonCard label="The fight to pole" className="min-h-[640px]" />
              )}
            </div>
            <FightToPoleDesktopNote />
          </div>
        </SessionGate>
      </section>

      <section id="race" className="mt-20 scroll-mt-24">
        <SectionTitle delay={0.4}>Race</SectionTitle>
        <SessionGate
          sessionsLoaded={sessionsLoaded}
          delay={0.4}
          loading={
            <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
              <SkeletonCard label="Pace spread" className="min-h-[600px]" />
              <SkeletonCard label="Tyre degradation" className="min-h-[540px]" />
              <SkeletonCard label="Finishing order" className="min-h-[400px]" />
            </div>
          }
          target={nextSessionTarget(['R'])}
          label="Race"
          happened={raceHappened}
          noData={raceNoData}
        >
          <div className="grid grid-cols-[minmax(0,1fr)] gap-6">
            {pace.data ? (
              <ScrollReveal>
                <PaceSpreadChart pace={pace.data} />
              </ScrollReveal>
            ) : (
              <SkeletonCard label="Pace spread" className="min-h-[600px]" />
            )}
            {degradation.data ? (
              <ScrollReveal delay={0.06}>
                <DegradationChart data={degradation.data} />
              </ScrollReveal>
            ) : (
              <SkeletonCard label="Tyre degradation" className="min-h-[540px]" />
            )}
            {results.data ? (
              <ScrollReveal delay={0.1}>
                <div className="glass mx-auto w-full max-w-4xl rounded-[--radius-panel] p-6 sm:p-8">
                  <h3 className="mb-6 font-display text-[2.025rem] font-semibold tracking-tight sm:text-[2.7rem]">
                    Finishing order
                  </h3>
                  <Results rows={results.data} />
                </div>
              </ScrollReveal>
            ) : (
              <SkeletonCard label="Finishing order" className="mx-auto min-h-[400px] w-full max-w-4xl" />
            )}
          </div>
        </SessionGate>
      </section>

      <BackToTopButton />
    </main>
  )
}
