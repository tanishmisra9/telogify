// The header of one ladder band: (optionally) a rule across the top, the band title and a count. With `onToggle` the whole
// strip is a fold toggle (a full-width target, keyboard operable, with a chevron): the qualifying segments use that. Without
// it the header is plain text: the race columns are not foldable, and they share ONE rule drawn by the chart (`rule={false}`).
export function LadderStrip({
  top, x0, x1, name, count, open = true, onToggle, rule = true, maxWidth,
}: { top: number; x0: number; x1: number; name: string; count?: string; open?: boolean; onToggle?: () => void; rule?: boolean; maxWidth?: number }) {
  // One <text> so the count follows the title's REAL width (an estimate left "Lead lap" 40px short of its count).
  // A title wider than its column would run into the next column's header, so it shrinks to fit (never below 15px).
  const size = maxWidth ? Math.max(15, Math.min(26, Math.floor(maxWidth / Math.max(1, name.length * 0.54)))) : 26
  const title = name ? (
    <text x={x0} y={top + 26} fill="var(--color-ink)" fontSize={size} fontWeight={500} className="font-display">
      {name}
      {count && <tspan dx={8} fill="var(--color-muted)" fontSize={12} fontWeight={400} className="num">{count}</tspan>}
    </text>
  ) : null
  return (
    <>
      {rule && <line x1={x0} x2={x1} y1={top} y2={top} stroke="var(--color-ink)" strokeWidth={1.5} />}
      {onToggle ? (
        <g
          role="button" tabIndex={0} aria-expanded={open} aria-label={count ? `${name}, ${count}` : name}
          className="cursor-pointer outline-none hover:[&>rect]:fill-[var(--color-border)] focus-visible:[&>rect]:stroke-[var(--color-accent)]"
          onClick={onToggle}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              onToggle()
            }
          }}
        >
          <rect x={x0 - 6} y={top + 1} width={x1 - x0 + 12} height={44} fill="transparent" stroke="transparent" strokeWidth={2} />
          {title}
          <path
            transform={`translate(${x1 - 8} ${top + 18})`}
            d={open ? 'M-5 -2.5 L0 2.5 L5 -2.5' : 'M-2.5 -5 L2.5 0 L-2.5 5'}
            fill="none" stroke="var(--color-ink)" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round"
          />
        </g>
      ) : (
        title
      )}
    </>
  )
}
