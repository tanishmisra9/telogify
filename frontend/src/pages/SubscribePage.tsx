import { BackHomeButton } from '@/components/BackHomeButton'
import { BlurFade } from '@/components/BlurFade'

export function SubscribePage() {
  return (
    // Outer container matches every other page so the heading's left edge lines up
    // sitewide; the lg cap keeps the content itself at a comfortable reading width.
    <main className="mx-auto max-w-[1312px] px-6 py-24">
      <div className="max-w-2xl">
      <BlurFade>
        <div className="mb-6">
          <BackHomeButton />
        </div>
        <h1 className="select-none font-display text-7xl leading-[1.05] tracking-tight sm:text-8xl">
          Telo<span className="text-accent">gify</span> your weekend
        </h1>
        <p className="mt-4 text-lg text-muted">
          Three insights per race weekend, speeding to your inbox.
        </p>
      </BlurFade>

      <BlurFade delay={0.06}>
        <p className="glass lift mt-12 rounded-[--radius-panel] p-8 font-display text-3xl tracking-tight text-ink">
          Coming soon!
        </p>
      </BlurFade>
      </div>
    </main>
  )
}
