// One section heading used across every page so headers share the same size, weight, rule, and
// left edge. Pages wrap their content in a single `max-w-[1312px] px-6` container (see WeekendPage
// / SeasonPage) so these titles line up from page to page.
export function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-8 border-b-2 border-ink pb-3">
      <h2 className="font-display text-[2.7rem] leading-[0.95] tracking-tight sm:text-[4.05rem]">{children}</h2>
    </div>
  )
}
