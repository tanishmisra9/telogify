import { useEffect, useState } from 'react'

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
  subtitle?: string
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

      {/* Flex, not an equal-width grid: a grid column stretches each unit to the same width
          regardless of content, so the units end up scattered at inconsistent distances from
          each other and from the panel's own left edge. Flex sizes each "02 Days" chunk to its
          own content and keeps a uniform gap between them. */}
      <div
        className={`${title ? (compact ? 'mt-6' : 'mt-10') : 'mt-8'} ${compact ? 'gap-x-6' : 'gap-x-10'} flex flex-wrap gap-y-4`}
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
