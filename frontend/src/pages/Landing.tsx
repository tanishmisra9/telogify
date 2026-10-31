import { Link } from 'react-router-dom'
import { BlurFade } from '@/components/BlurFade'
import { Countdown } from '@/components/Countdown'
import { Insight } from '@/components/Insight'
import { SeasonStats } from '@/components/SeasonStats'
import { Tooltip } from '@/components/Tooltip'
import { useAppSettled, useApi, type LatestInsight } from '@/lib/api'
import { useIsMobile } from '@/lib/useIsMobile'

function CTAs() {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:gap-4">
      <Tooltip label="See every analysed race weekend">
        <Link
          to="/weekends"
          aria-label="Browse analysed race weekends"
          className="lift inline-flex w-full items-center justify-center border-[1.5px] border-ink bg-accent px-6 py-2.5 font-display text-2xl text-accent-ink shadow-[4px_4px_0_var(--color-shadow)] sm:w-auto"
        >
          Browse
        </Link>
      </Tooltip>
      <Tooltip label="See season-wide rankings and trends">
        <Link
          to="/season"
          aria-label="View season rankings and trends"
          className="lift inline-flex w-full items-center justify-center border-[1.5px] border-ink bg-surface px-6 py-2.5 font-display text-2xl text-ink shadow-[4px_4px_0_var(--color-shadow)] sm:w-auto"
        >
          Trends
        </Link>
      </Tooltip>
      <Tooltip label="Get the weekly digest in your inbox">
        <Link
          to="/subscribe"
          aria-label="Subscribe to the weekly email digest"
          className="lift inline-flex w-full items-center justify-center border-[1.5px] border-ink bg-surface px-6 py-2.5 font-display text-2xl text-ink shadow-[4px_4px_0_var(--color-shadow)] sm:w-auto"
        >
          Subscribe
        </Link>
      </Tooltip>
    </div>
  )
}

// The proof: the strongest insight from the most recent weekend, in the exact component and
// voice the weekend page uses. Renders nothing until it has real data, so it never ships broken.
//
// Fetches immediately on mount regardless of `settled` (this request is one of the ones
// useAppSettled() itself waits on); the reveal waits for settled so this doesn't pop in crisp
// ahead of -- or independently of -- Countdown above it. (Previously had no BlurFade at all, on
// the theory that BlurFade's mount reveal "doesn't fire reliably" for content gated behind an
// async fetch -- disproved by LoadingSwap successfully doing exactly that; the real cause was a
// BlurFade mounted *before* the gate, animating to completion while its child rendered null.
// Mounting BlurFade only once both `data` and `settled` are true avoids that shape entirely.)
function LiveInsight() {
  const { data, loading } = useApi<LatestInsight>('/insights/latest')
  const isMobile = useIsMobile()
  const settled = useAppSettled()
  if (loading || !data || !settled) return null
  return (
    <BlurFade delay={0.06}>
      <section className="mt-24 sm:mt-32">
        <Insight
          item={data}
          showSlot={false}
          collapsible
          defaultOpen={!isMobile}
          contextLabel={data.event_name}
          kicker={
            // Two lines, not one "Latest verdict · Event Name" string: showSlot={false} puts the
            // copy/collapse buttons in an absolutely-positioned top-right corner overlay (see
            // Insight.tsx), and a long combined line ran wide enough to pass underneath them.
            <>
              <span className="block">Latest verdict</span>
              <span className="block text-muted">{data.event_name}</span>
            </>
          }
          href={`/weekends/${data.year}/${data.round}`}
        />
        <p className="mt-3 text-xs text-muted">Every figure traced to official timing data. Nothing estimated.</p>
      </section>
    </BlurFade>
  )
}

export function Landing() {
  return (
    <main className="mx-auto max-w-[1312px] px-6 py-20 sm:py-28">
      <section>
        <BlurFade>
          <h1 className="font-display text-6xl leading-[1.04] tracking-tight sm:text-7xl xl:text-8xl">
            Every weekend,
            <br />
            cut the <span className="text-accent">noise</span>.
          </h1>
        </BlurFade>

        <BlurFade delay={0.08}>
          <p className="mt-8 max-w-2xl font-display text-3xl leading-tight tracking-tight text-ink sm:text-4xl">
            The result tells you who won. The number tells you why.
          </p>
        </BlurFade>

        <BlurFade delay={0.14}>
          <div className="mt-10">
            <CTAs />
          </div>
        </BlurFade>
      </section>

      <Countdown />

      <LiveInsight />

      <SeasonStats />
    </main>
  )
}
