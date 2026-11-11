import { useState } from 'react'
import { AnimatePresence, m, useReducedMotion } from 'framer-motion'
import { Link } from 'react-router-dom'
import { BackHomeButton } from '@/components/BackHomeButton'
import { BlurFade } from '@/components/BlurFade'
import { LoadingSwap } from '@/components/LoadingSwap'
import { ScrollReveal } from '@/components/ScrollReveal'
import { Skeleton } from '@/components/Skeleton'
import { Tooltip } from '@/components/Tooltip'
import { useApi, type SeasonWeekendRow, type WeekendSummary } from '@/lib/api'

// Only the first screenful cascades on load; rows reached by scrolling fade in one at a time as
// they enter the viewport, so the scroll itself is the stagger and no per-row delay is needed.
const STAGGERED_ROWS = 6

// Enough rows to fill past the fold on a phone, so the loading state holds the page's real
// footprint (a full season is ~24 rounds, so this under-reserves rather than leaving a gap).
const SKELETON_ROWS = 8

// A year's list is ~2000px tall, so the shared stiff spring (`expandTransition`) crosses the whole
// viewport in ~2 frames and the footer visibly snaps; a fixed-duration ease reads as a smooth wipe.
const PANEL_TRANSITION = {
  height: { duration: 0.45, ease: [0.4, 0, 0.2, 1] as const },
  opacity: { duration: 0.25 },
}

export function Weekends() {
  const currentYear = new Date().getFullYear()
  const { data: pastData, loading: pastLoading, error } = useApi<WeekendSummary[]>('/weekends')
  // The full current-season fixture, ingested or not (see /season/{year}/weekends) -- every
  // other year is already fully ingested, so only the current year needs this richer fetch.
  const { data: seasonData, loading: seasonLoading } = useApi<SeasonWeekendRow[]>(
    `/season/${currentYear}/weekends`,
  )
  const loading = pastLoading || seasonLoading

  // Past years come straight from /weekends (always ingested). The current year is replaced
  // wholesale by the season fixture, which already includes its own ingested rows -- falling
  // back to /weekends' own current-year rows only if that fetch itself failed, so a transient
  // schedule outage doesn't blank the season currently in progress.
  const currentYearRows: SeasonWeekendRow[] =
    seasonData ??
    (pastData ?? [])
      .filter((w) => w.year === currentYear)
      .map((w) => ({ ...w, date_utc: null, ingested: true }))
  const weekends = [
    ...(pastData ?? [])
      .filter((w) => w.year !== currentYear)
      .map((w): SeasonWeekendRow => ({ ...w, date_utc: null, ingested: true })),
    ...currentYearRows,
  ].sort((a, b) => a.year - b.year || a.round - b.round)
  const loggedCount = weekends.filter((w) => w.ingested).length

  // One collapsible group per year, newest first; rounds stay in calendar order inside a year.
  // Only the newest year opens by default (a user's own toggle, tracked by year, always wins), so
  // a long archive doesn't push the current season off the screen.
  const years = [...new Set(weekends.map((w) => w.year))].sort((a, b) => b - a)
  const [toggled, setToggled] = useState<Record<number, boolean>>({})
  const reduce = useReducedMotion()
  const isOpen = (year: number) => toggled[year] ?? year === years[0]

  return (
    <main className="mx-auto max-w-[1312px] px-6 py-16 sm:py-24">
      <BlurFade>
        <div className="mb-6">
          <BackHomeButton />
        </div>
        <div className="flex flex-col gap-3 border-b-2 border-ink pb-3 sm:flex-row sm:items-end sm:justify-between sm:gap-4">
          {/* Split on purpose: mobile keeps the 0.9x display-ramp size (text-[3.375rem]) because
              the narrower column needs it, while sm+ is back on the raw text-7xl it was before the
              0.9x pass -- the reduction was only ever wanted on mobile. */}
          <h1 className="font-display text-[3.375rem] leading-[0.95] tracking-tight sm:text-7xl">
            Race weekends
          </h1>
          {/* Always mounted; only the text changes. This header is flex-col below `sm`, so the
              badge is its own row there -- gating the whole span on `!loading` meant it appeared
              late and pushed the rest of the page down by 29px (measured; desktop was unaffected
              since the badge sits inline beside the h1 there). One span with a non-breaking space
              while loading reserves the identical line box by construction, so there's no height
              to measure and nothing to drift out of sync. Still never renders "0 logged", which
              would be a real but wrong figure a reader could act on. */}
          <span className="kicker whitespace-nowrap text-muted">
            {loading ? ' ' : `${loggedCount} logged`}
          </span>
        </div>
        <p className="mt-4 max-w-4xl text-lg leading-relaxed text-muted">
          Every race weekend of the season, each analysed weekend traced to official timing data.
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
          <div className="mt-8">
            {/* Reserves the year header's measured height so the crossfade into the list does not shift. */}
            <Skeleton className="h-[68px] sm:h-[87px]" />
          <ul>
            {Array.from({ length: SKELETON_ROWS }).map((_, i) => (
              <li key={i} className="border-b border-border py-6">
                {/* Measured against a real row (86.5px desktop; 109px on a phone when the event
                    name wraps to two lines, 81px when it fits one) minus this li's own py-6 and
                    border, so the reserved rows match what replaces them. */}
                <Skeleton className="h-[60px] md:h-[38px]" />
              </li>
            ))}
          </ul>
          </div>
        }
      >
        {error ? (
          <p className="mt-8 text-muted">API offline.</p>
        ) : !loading && weekends.length === 0 ? (
          <p className="mt-8 text-muted">No weekends processed yet.</p>
        ) : (
          <div>
            {years.map((year, yi) => {
              const rows = weekends.filter((w) => w.year === year)
              const open = isOpen(year)
              const panelId = `weekends-${year}`
              // The load-time blur-fade cascade only belongs to the first render. Re-running it on
              // every expand stacks a per-row blur/translate inside the height animation, and the
              // filter dropping to `none` at its end re-rasterizes the rows (a visible snap on iOS
              // Safari). Once a user has toggled a year, the panel's own height/opacity is the reveal.
              const Reveal = toggled[year] === undefined ? ScrollReveal : 'div'
              return (
                <section key={year} className={yi === 0 ? 'mt-8' : 'mt-10'}>
                  <h2>
                    <Tooltip
                      align="start"
                      className="relative flex w-full"
                      label={`${open ? 'Collapse' : 'Expand'} ${year}: ${rows.length} race weekend${rows.length === 1 ? '' : 's'}`}
                    >
                      <button
                        type="button"
                        onClick={() => setToggled((t) => ({ ...t, [year]: !open }))}
                        aria-expanded={open}
                        aria-controls={panelId}
                        className="group flex w-full cursor-pointer items-center justify-between gap-4 border-b-[1.5px] border-ink py-3 text-left transition-colors hover:bg-surface sm:py-4"
                      >
                        <span className="font-display text-[2.7rem] leading-none tracking-tight sm:text-[3.375rem]">
                          {year}
                        </span>
                        <span className="flex items-center gap-4">
                          <span className="num text-sm text-muted">
                            {rows.length} {rows.length === 1 ? 'weekend' : 'weekends'}
                          </span>
                          {/* Drawn chevron (not a glyph): points right when closed, turns down
                              when open. Accent so it reads as the control. */}
                          <svg
                            aria-hidden
                            viewBox="0 0 24 24"
                            className={`h-6 w-6 shrink-0 text-accent transition-transform duration-200 ease-out ${open ? 'rotate-90' : ''}`}
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2.25"
                            strokeLinecap="square"
                            strokeLinejoin="miter"
                          >
                            <path d="M9 5l7 7-7 7" />
                          </svg>
                        </span>
                      </button>
                    </Tooltip>
                  </h2>
                  <AnimatePresence initial={false}>
                    {open && (
                      <m.ul
                        id={panelId}
                        key="rows"
                        className="overflow-hidden"
                        initial={reduce ? false : { height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={reduce ? { opacity: 0 } : { height: 0, opacity: 0 }}
                        transition={reduce ? { duration: 0 } : PANEL_TRANSITION}
                      >
                        {rows.map((w, i) => (
                          <Reveal key={`${w.year}-${w.round}`} {...(Reveal === ScrollReveal ? { delay: yi === 0 && i < STAGGERED_ROWS ? 0.04 * i : 0 } : {})}>
                            <li className="border-b border-border">
                              <Link
                                to={`/weekends/${w.year}/${w.round}`}
                                aria-label={`${w.event_name}, round ${w.round}, ${w.year}`}
                                className="group flex items-center gap-5 py-6 transition-colors hover:bg-surface"
                              >
                                <span className="num w-14 text-2xl font-bold text-accent">
                                  {String(w.round).padStart(2, '0')}
                                </span>
                                <span className="flex-1">
                                  <span className="block font-display text-2xl leading-tight transition-transform duration-200 group-hover:translate-x-1 sm:text-3xl">
                                    {w.event_name}
                                  </span>
                                </span>
                              </Link>
                            </li>
                          </Reveal>
                        ))}
                      </m.ul>
                    )}
                  </AnimatePresence>
                </section>
              )
            })}
          </div>
        )}
      </LoadingSwap>
    </main>
  )
}
