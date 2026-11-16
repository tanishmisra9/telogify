// A section's "what am I looking at" line, ABOVE its data (a caption under the chart is read after the chart,
// i.e. not at all). Caveats still go in a small caption below. See CLAUDE.md "Trends standard".
export function SectionLede({ children }: { children: React.ReactNode }) {
  return <p className="mb-6 max-w-3xl text-lg leading-relaxed text-muted">{children}</p>
}

// A chart's own heading inside a ranked section ("Gap by round" under "Pace ranking"): smaller than the section's
// h2 and every page h1, with its own one-line lede under it.
export function SubTitle({ children, lede }: { children: React.ReactNode; lede?: React.ReactNode }) {
  return (
    <div className="mb-5 mt-14">
      <h3 className="font-display text-[2.025rem] font-semibold leading-tight tracking-tight sm:text-[2.7rem]">{children}</h3>
      {lede && <p className="mt-2 max-w-3xl text-lg leading-relaxed text-muted">{lede}</p>}
    </div>
  )
}
