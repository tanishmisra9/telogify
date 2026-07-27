import { BlurFade } from '@/components/BlurFade'

// One section heading used across every page so headers share the same size, weight, rule, and
// left edge. Pages wrap their content in a single `max-w-[1312px] px-6` container (see WeekendPage
// / SeasonPage) so these titles line up from page to page. Wrapped in BlurFade (same reveal as the
// hero above it) so a page's headings blur in top-down instead of the hero animating while every
// heading below it is already fully sharp; `delay` staggers that top-down order down the page.
//
// Size must stay BELOW every page's h1, or a section reads as outranking the page it sits in.
// This was `sm:text-[5rem]` (80px), which outsized SeasonPage's 72px h1 on desktop -- "Ranking"
// rendered larger than "Season at a glance". Now 0.9x that h1 (64.8px), which also clears
// WeekendPage's larger 86.4px h1. If any page's h1 shrinks, re-check this against it.
export function SectionTitle({ children, delay = 0 }: { children: React.ReactNode; delay?: number }) {
  return (
    <BlurFade delay={delay} className="mb-8 border-b-2 border-ink pb-3">
      <h2 className="font-display text-[2.5rem] leading-[0.95] tracking-tight sm:text-[4.05rem]">{children}</h2>
    </BlurFade>
  )
}
