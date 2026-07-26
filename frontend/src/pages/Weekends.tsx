import { Link } from 'react-router-dom'
import { BackHomeButton } from '@/components/BackHomeButton'
import { BlurFade } from '@/components/BlurFade'
import { LoadingSwap } from '@/components/LoadingSwap'
import { ScrollReveal } from '@/components/ScrollReveal'
import { Skeleton } from '@/components/Skeleton'
import { useApi, type WeekendSummary } from '@/lib/api'

// Only the first screenful cascades on load; rows reached by scrolling fade in one at a time as
// they enter the viewport, so the scroll itself is the stagger and no per-row delay is needed.
const STAGGERED_ROWS = 6

// Enough rows to fill past the fold on a phone, so the loading state holds the page's real
// footprint (a full season is ~24 rounds, so this under-reserves rather than leaving a gap).
const SKELETON_ROWS = 8

export function Weekends() {
  const { data, loading, error } = useApi<WeekendSummary[]>('/weekends')
  const weekends = [...(data ?? [])].sort((a, b) => a.year - b.year || a.round - b.round)

  return (
    <main className="mx-auto max-w-[1312px] px-6 py-16 sm:py-24">
      <BlurFade>
        <div className="mb-6">
          <BackHomeButton />
        </div>
        <div className="flex flex-col gap-3 border-b-2 border-ink pb-3 sm:flex-row sm:items-end sm:justify-between sm:gap-4">
          {/* 0.9x text-6xl/text-7xl. Same scale factor the other display headings already use
              (WeekendPage's text-[3.375rem]/text-[5.4rem], Insight's text-[2.025rem]/[2.7rem]),
              so this stays on the existing type ramp rather than introducing a new size. */}
          <h1 className="font-display text-[3.375rem] leading-[0.95] tracking-tight sm:text-[4.05rem]">
            Race weekends
          </h1>
          {/* Withheld while loading rather than rendering "0 logged", which is a real (wrong)
              figure a reader can act on, not an obviously-empty placeholder. */}
          {!loading && (
            <span className="kicker whitespace-nowrap text-muted">{weekends.length} logged</span>
          )}
        </div>
        <p className="mt-4 max-w-3xl text-lg leading-relaxed text-muted">
          Every ingested race weekend, each with its verdicts traced to official timing data.
        </p>
      </BlurFade>

      {/* Was a bare "Loading..." line, which both under-reserved the list's height (so the page
          grew underneath it once rows landed) and read as a hard, unanimated pop against the
          blur-fade every other element on the page uses. Same LoadingSwap treatment as the
          Season/Weekend pages: reserve the rows' real footprint, then crossfade into them. */}
      <LoadingSwap
        loading={loading}
        delay={0.08}
        placeholder={
          <ul className="mt-8">
            {Array.from({ length: SKELETON_ROWS }).map((_, i) => (
              <li key={i} className="border-b border-border py-6">
                {/* Measured against a real row (110.5px desktop / 133px mobile, the difference
                    being the event name wrapping to two lines in a narrow column) minus this
                    li's own py-6 and border, so the reserved rows match what replaces them. */}
                <Skeleton className="h-[84px] md:h-[62px]" />
              </li>
            ))}
          </ul>
        }
      >
        {error ? (
          <p className="mt-8 text-muted">API offline.</p>
        ) : data && data.length === 0 ? (
          <p className="mt-8 text-muted">No weekends processed yet.</p>
        ) : (
          <ul>
            {weekends.map((w, i) => (
              <ScrollReveal key={w.id} delay={i < STAGGERED_ROWS ? 0.04 * i : 0}>
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
                      {/* Circuit only, no country: the event name directly above already carries
                          the nationality ("Chinese Grand Prix" / "Shanghai"), so appending the
                          country repeated it on nearly every row. */}
                      <span className="mt-1 block text-sm text-muted">{w.circuit_name}</span>
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
              </ScrollReveal>
            ))}
          </ul>
        )}
      </LoadingSwap>
    </main>
  )
}
