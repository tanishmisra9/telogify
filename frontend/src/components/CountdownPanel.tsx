import { useEffect, useState, type ReactNode } from 'react'

const pad = (n: number) => String(n).padStart(2, '0')

function parts(target: number) {
  const s = Math.max(0, Math.floor((target - Date.now()) / 1000))
  const days = Math.floor(s / 86400)
  return [
    [days === 1 ? 'Day' : 'Days', days],
    ['Hours', Math.floor((s % 86400) / 3600)],
    ['Minutes', Math.floor((s % 3600) / 60)],
    ['Seconds', s % 60],
  ] as const
}

// Shared "paper panel with ticking mono digits" language: the landing page's next-race
// centerpiece (Countdown.tsx) and the weekend page's per-session countdowns both render one of
// these, so a design change to either applies to both at once. `compact` scales the type down
// from the landing page's hero sizing to fit a normal content-grid panel.
export function CountdownPanel({
  kicker,
  title,
  subtitle,
  targetIso,
  compact = false,
}: {
  kicker: string
  // Optional: omit when a heading above the panel already states the same thing (e.g. the
  // weekend page's own "Race" SectionTitle), so the panel doesn't repeat it.
  title?: string
  // ReactNode (not just string) so a caller with two distinct pieces (e.g. a date and a
  // location) can render them as two explicit lines instead of one string that soft-wraps
  // wherever it happens to overflow.
  subtitle?: ReactNode
  targetIso: string
  compact?: boolean
}) {
  const target = new Date(targetIso).getTime()
  const [, tick] = useState(0)

  useEffect(() => {
    const id = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className={`glass rounded-[--radius-panel] ${compact ? 'p-6' : 'p-8 sm:p-12'}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <p className="kicker text-sm! text-accent">{kicker}</p>
        {/* Same kicker voice as the line above (mono, uppercase, tracked), just muted instead
            of accent-red, so the two lines read as one typographic family, not two. */}
        {subtitle && <p className="kicker text-sm! text-muted">{subtitle}</p>}
      </div>

      {/* -0.07em compensates for font-metric optical misalignment, not a layout bug: this
          heading's box-left edge is pixel-identical to the kicker/digit rows above and below
          it (verified via getBoundingClientRect), but Instrument Sans (font-display) carries
          noticeably more built-in left-side-bearing on a capital letter than the mono font
          does. An em unit keeps the correction proportional as the heading scales. */}
      {title && (
        <h2
          className={`mt-4 ml-[-0.07em] font-display leading-[0.95] tracking-tight ${
            compact
              ? 'text-[2.025rem] font-semibold sm:text-[2.7rem]'
              : 'text-5xl sm:text-7xl xl:text-8xl'
          }`}
        >
          {title}
        </h2>
      )}

      {/* Auto-sized grid columns (repeat(N,auto)), not equal-width (1fr) columns and not flex:
          an equal-width grid would stretch every unit to the same width regardless of content,
          wasting space around "Days"/"Hours". Flex avoided that but doesn't align wrapped rows
          into columns at all -- each unit sizes to its own content, so row 2 starts at a
          different x-offset than row 1 the moment 4 units don't fit one line. Auto-sized grid
          columns get both: each column is only as wide as its own widest cell (still no forced
          uniform width across all 4), but every row shares the same column boundaries, so
          wrapped rows land aligned. 2 columns (2x2) below `sm`, all 4 in one row at `sm` and up. */}
      <div
        className={`grid grid-cols-[repeat(2,auto)] sm:grid-cols-[repeat(4,auto)] ${title ? (compact ? 'mt-6' : 'mt-10') : 'mt-8'} ${compact ? 'gap-x-6' : 'gap-x-10'} gap-y-4`}
        aria-live="polite"
        aria-atomic="true"
      >
        {parts(target).map(([label, value]) => (
          <div key={label} className="flex items-baseline gap-2">
            <span
              className={`num leading-none tracking-tight text-ink tabular-nums ${
                compact ? 'text-3xl sm:text-5xl' : 'text-4xl sm:text-6xl xl:text-8xl'
              }`}
            >
              {pad(value)}
            </span>
            {/* kicker (not a bare uppercase/tracking utility stack) so this sits in the same
                mono fontface as the digits above it and every other kicker on the panel. */}
            <span className="kicker text-xs! text-muted sm:text-sm!">{label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
