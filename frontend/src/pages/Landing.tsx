import { Link } from 'react-router-dom'
import { BlurFade } from '@/components/BlurFade'
import { Countdown } from '@/components/Countdown'
import { Insight } from '@/components/Insight'
import { Tooltip } from '@/components/Tooltip'
import { useApi, type LatestInsight } from '@/lib/api'

const STEPS = [
  {
    title: 'Ingest',
    body: 'A full race weekend goes in: every lap, telemetry trace, tyre stint, sector, and result.',
  },
  {
    title: 'Measure',
    body: 'Deterministic analysis computes every number into the database: pace, degradation, car character, and sectors.',
  },
  {
    title: 'Read',
    body: 'An agent writes three plain-language insights, every figure traced back to the data.',
  },
]

function CTAs() {
  return (
    <div className="flex flex-wrap gap-4">
      <Tooltip label="See every analysed race weekend">
        <Link
          to="/weekends"
          aria-label="Browse analysed race weekends"
          className="lift inline-flex items-center border-[1.5px] border-ink bg-accent px-6 py-2.5 font-display text-2xl text-accent-ink shadow-[4px_4px_0_var(--color-shadow)]"
        >
          Browse
        </Link>
      </Tooltip>
      <Tooltip label="Get the weekly digest in your inbox">
        <Link
          to="/subscribe"
          aria-label="Subscribe to the weekly email digest"
          className="lift inline-flex items-center border-[1.5px] border-ink bg-surface px-6 py-2.5 font-display text-2xl text-ink shadow-[4px_4px_0_var(--color-shadow)]"
        >
          Subscribe
        </Link>
      </Tooltip>
    </div>
  )
}

// The proof: the strongest insight from the most recent weekend, in the exact component and
// voice the weekend page uses. Renders nothing until it has real data, so it never ships broken.
function LiveInsight() {
  const { data, loading } = useApi<LatestInsight>('/insights/latest')
  if (loading || !data) return null
  // No BlurFade here: this content mounts only after the fetch resolves, and BlurFade's
  // mount reveal is unreliable for content that appears after an async gate (it can stay at
  // opacity 0). The data-load itself is the reveal.
  return (
    <section className="mt-24 sm:mt-32">
      <p className="kicker text-accent">Latest verdict · {data.event_name}</p>
      <div className="mt-4">
        <Insight item={data} showSlot={false} />
      </div>
      <p className="mt-3 text-xs text-muted">Every figure traced to official timing data. Nothing estimated.</p>
    </section>
  )
}

export function Landing() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-20 sm:py-28">
      <section>
        <BlurFade>
          <h1 className="font-display text-6xl leading-[1.04] tracking-tight sm:text-8xl xl:text-[9rem]">
            Every weekend,
            <br />
            cut the <span className="text-accent">noise</span>.
          </h1>
        </BlurFade>

        <BlurFade delay={0.08}>
          <div className="mt-10">
            <CTAs />
          </div>
        </BlurFade>

        <BlurFade delay={0.14}>
          <p className="mt-10 max-w-2xl font-display text-3xl leading-tight tracking-tight text-ink sm:text-4xl">
            The result tells you who won. The number tells you why.
          </p>
        </BlurFade>
      </section>

      <Countdown />

      <LiveInsight />

      <section className="mt-28 sm:mt-40">
        <BlurFade>
          <div className="border-b-2 border-ink pb-3">
            <h2 className="font-display text-5xl leading-none tracking-tight sm:text-7xl">
              How it works
            </h2>
          </div>
        </BlurFade>

        <div className="mt-12 grid gap-10 sm:grid-cols-3 sm:gap-8">
          {STEPS.map((step, i) => (
            <BlurFade key={step.title} delay={0.06 * i}>
              <div>
                <span className="font-display text-6xl leading-none text-accent">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <h3 className="mt-4 font-display text-3xl tracking-tight">{step.title}</h3>
                <p className="mt-3 leading-relaxed text-muted">{step.body}</p>
              </div>
            </BlurFade>
          ))}
        </div>
      </section>
    </main>
  )
}
