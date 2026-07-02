import { Link } from 'react-router-dom'
import { BlurFade } from '@/components/BlurFade'
import { Tooltip } from '@/components/Tooltip'

const STEPS = [
  {
    title: 'Ingest',
    body: 'A full FastF1 race weekend goes in: every lap, telemetry trace, tyre stint, sector, and result.',
  },
  {
    title: 'Measure',
    body: 'Deterministic analysis computes every number into the database: pace, degradation, car character, and sectors.',
  },
  {
    title: 'Read',
    body: 'An agent retrieves the exact values and writes three plain-language insights. Every figure traces back to the data, nothing invented.',
  },
]

function CTAs() {
  return (
    <div className="flex flex-wrap gap-4">
      <Tooltip label="See every analysed race weekend">
        <Link
          to="/weekends"
          className="lift inline-flex items-center border-[1.5px] border-ink bg-accent px-6 py-2.5 font-display text-2xl text-accent-ink shadow-[4px_4px_0_var(--color-shadow)]"
        >
          Browse
        </Link>
      </Tooltip>
      <Tooltip label="Get the weekly digest in your inbox">
        <Link
          to="/subscribe"
          className="lift inline-flex items-center border-[1.5px] border-ink bg-surface px-6 py-2.5 font-display text-2xl text-ink shadow-[4px_4px_0_var(--color-shadow)]"
        >
          Subscribe
        </Link>
      </Tooltip>
    </div>
  )
}

export function Landing() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-20 sm:py-28">
      <section>
        <BlurFade>
          <h1 className="font-display text-7xl leading-[1.04] tracking-tight sm:text-[9rem]">
            Every weekend,
            <br />
            read like a <span className="italic text-accent">verdict</span>.
          </h1>
        </BlurFade>

        <BlurFade delay={0.08}>
          <p className="mt-8 max-w-2xl text-xl leading-relaxed text-muted">
            Three telemetry-grounded insights per race weekend, every number traced back to the
            data.
          </p>
        </BlurFade>

        <BlurFade delay={0.14}>
          <div className="mt-10">
            <CTAs />
          </div>
        </BlurFade>
      </section>

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
              <div className="border-t-2 border-ink pt-5">
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
