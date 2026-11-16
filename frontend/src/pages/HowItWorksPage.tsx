import { useEffect, useRef, useState } from 'react'
import { BackHomeButton } from '@/components/BackHomeButton'
import { BackToTopButton } from '@/components/BackToTopButton'
import { BlurFade } from '@/components/BlurFade'
import { LoadingSwap } from '@/components/LoadingSwap'
import { ScrollReveal } from '@/components/ScrollReveal'
import { SectionTitle } from '@/components/SectionTitle'
import { SkeletonCard } from '@/components/Skeleton'
import { useApi, type TracedExample } from '@/lib/api'
import { loadBag, nextFromBag, saveBag, type Bag } from '@/lib/shuffleBag'
import { exampleId, gateLines, quoteParts, storedLines, toolCallLines } from '@/lib/tracedExample'

// Key phrases bolded in ink so each muted paragraph carries one scannable claim.
function Key({ children }: { children: React.ReactNode }) {
  return <strong className="font-semibold text-ink">{children}</strong>
}

// Code panel for each step. The figures are REAL: each visit shows one published insight figure and the exact logged
// tool-return row it traces to (GET /insights/traced, cycled so every example is shown once before any repeats). A
// block's label says when it is an excerpt, a summary or static, not a verbatim log. In a line, {{x}} is the traced
// figure (accent) and "key": is dimmed. Lines wrap rather than scroll, so the page keeps one scroll system.
function CodeLine({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\{\{.*?\}\}|"[A-Za-z_]+":)/).map((t, i) =>
        t.startsWith('{{') ? (
          <span key={i} className="text-accent">
            {t.slice(2, -2)}
          </span>
        ) : /^"[A-Za-z_]+":$/.test(t) ? (
          <span key={i} className="text-muted">
            {t}
          </span>
        ) : (
          t
        ),
      )}
    </>
  )
}

function CodeBlock({ label, lines }: { label: string; lines: string[] }) {
  return (
    <figure className="mt-5 border-[1.5px] border-ink bg-surface">
      <figcaption className="kicker flex items-center gap-2 border-b-[1.5px] border-ink px-3 py-1.5 text-muted">
        <span aria-hidden className="inline-block h-1.5 w-1.5 bg-accent" />
        {label}
      </figcaption>
      <pre className="num m-0 py-3 text-xs leading-6 text-ink sm:text-sm">
        <code className="block">
          {lines.map((line, i) => (
            <span key={i} className="grid grid-cols-[2.25rem_minmax(0,1fr)]">
              <span aria-hidden className="select-none pr-3 text-right text-muted/70">
                {i + 1}
              </span>
              {/* Indent as padding, not spaces, so a wrapped line never breaks inside its own indent. */}
              <span
                className="whitespace-pre-wrap pr-3 [overflow-wrap:break-word]"
                style={{ paddingLeft: `${line.length - line.trimStart().length}ch` }}
              >
                <CodeLine text={line.trimStart()} />
              </span>
            </span>
          ))}
        </code>
      </pre>
    </figure>
  )
}

// Shown only if the examples endpoint is empty or unreachable (an older API, no insights yet): the 2026 Bahrain
// Grand Prix insight, with the real logged return behind its figure. 0.16695... is get_constructor_ranking's value for
// Mercedes; the published prose rounds it to 0.167 (serialize.round_prose_numbers).
const FALLBACK: TracedExample = {
  year: 2026,
  round: 0,
  event_name: 'Bahrain Grand Prix',
  header: 'Red Bull Racing set the pace',
  explanation_web:
    "Max Verstappen's Red Bull Racing car finished first, and the team set the fastest race pace, with Mercedes 0.167 seconds per lap behind.",
  traced: '0.167',
  traced_with_unit: '0.167 seconds',
  raw: '0.16695454545454425',
  key: 'gap_to_team_ahead_s',
  tool: 'get_constructor_ranking',
  args: {},
  row: {
    constructor: 'Mercedes',
    overall_rank: 2,
    race_pace_gap_s: 0.16695454545454425,
    gap_to_team_ahead_s: 0.16695454545454425,
    clean_air_median_s: 101.056,
    clean_air_gap_to_fastest_s: 0.181,
    clean_air_n_laps: 60,
  },
}

// Steps 2 and 4 are the same for every example (the clean-air filter and the first tool call), so they stay as the
// real Bahrain excerpts and say so; steps 1, 3, 5 and 6 follow the chosen example.
function buildLayers(ex: TracedExample) {
  return [
    {
      title: 'Official timing in.',
      body: (
        <>
          Every session is pulled from <Key>FastF1&apos;s official timing</Key> once it has started.
          A race is held back until the official results are complete, so a half-loaded finishing
          order can never become a verdict.
        </>
      ),
      code: {
        label: 'source (summary)',
        lines: ['source:  FastF1 official timing', 'session: Race', `event:   ${ex.year} ${ex.event_name}`],
      },
    },
    {
      title: 'Only laps that count.',
      body: (
        <>
          <Key>Green-flag laps only</Key>, the opening lap left out, and every race lap corrected to
          an empty-tank reference so a heavy early stint is not read as slow. A separate clean-air
          pass keeps only laps with no car within half a second ahead.
        </>
      ),
      code: {
        label: 'clean-air laps counted (excerpt, 2026 Bahrain Grand Prix)',
        lines: [
          '{"constructor": "Red Bull Racing", "clean_air_n_laps": 64}',
          '{"constructor": "Mercedes", "clean_air_n_laps": 60}',
        ],
      },
    },
    {
      title: 'Numbers first, words later.',
      body: (
        <>
          Pace, sector and straight-line deltas, tyre degradation and energy deployment are computed
          and stored in the database <Key>before any model runs</Key>. A language model never
          produces a figure.
        </>
      ),
      code: { label: 'stored value, written before the agent runs', lines: storedLines(ex) },
    },
    {
      title: 'Findings compete.',
      body: (
        <>
          Signal miners score every gap they find. When one team shows up in several channels at once,
          such as corners, straights and race pace, the findings are fused and{' '}
          <Key>outrank any single-channel one</Key>. The agent only sees this ranked list.
        </>
      ),
      code: {
        label: 'first tool call (every insight starts here)',
        lines: ['get_candidate_insights({"n": 10, "category": ""})'],
      },
    },
    {
      title: 'The agent looks things up.',
      body: (
        <>
          It writes using <Key>13 database tools</Key> and has no other source. Every call and its
          return is logged against the insight it helped write.
        </>
      ),
      code: { label: 'logged tool call, one row of the return', lines: toolCallLines(ex) },
    },
    {
      title: 'The gate.',
      body: (
        <>
          Every draft is checked twice: against a blocklist for claims one weekend cannot prove, like
          first-lap drama or career milestones, and against the tool log, where{' '}
          <Key>every number in the prose must match a logged return</Key>. A failing draft goes back
          with specific feedback. Three attempts, then it stops, and{' '}
          <Key>nothing is published until it passes</Key>.
        </>
      ),
      code: { label: 'check (illustrative)', lines: gateLines(ex) },
    },
  ]
}

const REPLIES = [
  {
    quote:
      'Neat job on Telogify, the extra layer of analytics is an interesting touch, worth developing.',
    from: 'Race strategy team member, Formula 1 team',
  },
  {
    quote: 'We took a look at the platform and it’s impressive work, especially for a solo developer.',
    from: 'F1 timing and data project',
  },
  { quote: 'Hey, this is really great.', from: 'Video producer, F1 YouTube channel' },
  { quote: 'Love the design.', from: 'F1 data project maintainers' },
]

const rowGrid = 'grid grid-cols-[3.25rem_minmax(0,1fr)] gap-x-4 sm:grid-cols-[5rem_minmax(0,1fr)] sm:gap-x-6'
const cell = 'min-w-0 lg:grid lg:grid-cols-[minmax(0,4fr)_minmax(0,6fr)] lg:gap-12'
const numeral = 'font-display text-4xl leading-none text-accent sm:text-6xl'

export function HowItWorksPage() {
  const examples = useApi<TracedExample[]>('/insights/traced?limit=48')
  const pool = examples.data ?? []
  // The visitor's bag survives reloads (localStorage), so a returning visitor sees every example once before any
  // repeat. Only picked once the pool has loaded.
  const bagRef = useRef<Bag | null>(null)
  const [pickedId, setPickedId] = useState<string | null>(null)
  const ids = pool.map(exampleId)
  const idsKey = ids.join('|')

  const pick = () => {
    bagRef.current ??= loadBag()
    const next = nextFromBag(ids, bagRef.current)
    if (!next) return
    bagRef.current = next.bag
    saveBag(next.bag)
    setPickedId(next.id)
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (ids.length > 0) pick() }, [idsKey])

  const example = pool.find((e) => exampleId(e) === pickedId) ?? (pool.length === 0 ? FALLBACK : null)
  const waiting = examples.loading || (pool.length > 0 && !example)
  const layers = example ? buildLayers(example) : []
  const quote = example ? quoteParts(example) : null

  return (
    <main className="mx-auto max-w-[1312px] px-6 py-16 sm:py-24">
      <BlurFade>
        <div className="mb-6">
          <BackHomeButton />
        </div>
        <div className="border-b-2 border-ink pb-3">
          <h1 className="font-display text-[3.375rem] leading-[0.95] tracking-tight sm:text-7xl">
            How it works.
          </h1>
        </div>
        <p className="mt-4 max-w-3xl font-display text-3xl leading-tight tracking-tight sm:text-4xl">Follow one number.</p>
        <p className="mt-3 max-w-3xl text-lg leading-relaxed text-muted">
          One sentence from a published verdict, traced back through every step that produced it.
        </p>
      </BlurFade>

      <LoadingSwap loading={waiting} placeholder={<SkeletonCard className="mt-12 min-h-[1400px] lg:mt-16" />}>
        {example && quote && (
          <div className="mt-12 lg:mt-16">
            <BlurFade delay={0.08} className="max-w-5xl">
              <p className="font-display text-[2.025rem] leading-[1.12] tracking-tight sm:text-[2.7rem] lg:text-[3.375rem]">
                &ldquo;{quote.before}
                {quote.figure && (
                  <span className="text-accent">
                    <span className="num">{quote.figure}</span>
                  </span>
                )}
                {quote.after}&rdquo;
              </p>
              <p className="mt-4 flex flex-wrap items-baseline gap-x-5 gap-y-2 text-sm text-muted">
                <span>
                  Worked example: {example.year} {example.event_name}
                </span>
                {pool.length > 1 && (
                  <button
                    type="button"
                    onClick={pick}
                    className="min-h-8 cursor-pointer font-medium text-ink underline underline-offset-4 hover:text-accent"
                  >
                    Another example
                  </button>
                )}
              </p>
            </BlurFade>

            <ol className="mt-12 list-none border-t-2 border-ink lg:mt-16">
              {layers.map((layer, i) => (
                <li key={layer.title} className="border-b border-ink py-8 sm:py-10">
                  <ScrollReveal>
                    <div className={rowGrid}>
                      <span className={numeral} aria-hidden>
                        {String(i + 1).padStart(2, '0')}
                      </span>
                      <div className={cell}>
                        <h2 className="font-display text-3xl tracking-tight sm:text-4xl">{layer.title}</h2>
                        <div className="min-w-0">
                          <p className="mt-3 leading-relaxed text-muted lg:mt-1.5">{layer.body}</p>
                          <CodeBlock label={layer.code.label} lines={layer.code.lines} />
                        </div>
                      </div>
                    </div>
                  </ScrollReveal>
                </li>
              ))}
            </ol>
          </div>
        )}
      </LoadingSwap>

      <ScrollReveal className="mt-10 max-w-3xl">
        <p className="font-display text-3xl leading-tight tracking-tight sm:text-4xl">
          Each weekend ends in three race verdicts and two qualifying verdicts, on the page and in
          the email digest.
        </p>
      </ScrollReveal>

      <section className="mt-24 sm:mt-32">
        <SectionTitle>What people said</SectionTitle>
        <ul className="grid list-none gap-6 sm:grid-cols-2 sm:gap-8">
          {REPLIES.map((r, i) => (
            <li key={r.from} className="min-w-0">
              <ScrollReveal delay={0.06 * (i % 2)} className="h-full">
                <figure className="glass flex h-full flex-col rounded-panel p-7">
                  <blockquote>
                    <p className="font-display text-3xl leading-[1.15] tracking-tight sm:text-4xl">
                      &ldquo;{r.quote}&rdquo;
                    </p>
                  </blockquote>
                  <figcaption className="mt-auto pt-6 text-sm text-muted">{r.from}</figcaption>
                </figure>
              </ScrollReveal>
            </li>
          ))}
        </ul>
      </section>

      <BackToTopButton />
    </main>
  )
}
