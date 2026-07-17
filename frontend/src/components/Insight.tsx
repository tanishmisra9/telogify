import { useState, type ReactNode } from 'react'
import { AnimatePresence, m } from 'framer-motion'
import { Tooltip } from '@/components/Tooltip'
import { emphasize, bindMetricSpaces } from '@/lib/emphasize'
import { expandTransition } from '@/lib/motion'
import type { InsightItem } from '@/lib/api'

// Hand-rolled to match the codebase's icon convention (no lucide-react dependency installed):
// Lucide's own "copy" and "check" glyphs, redrawn as plain stroke SVG.
function CopyIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
      <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
    </svg>
  )
}
function CheckIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M20 6 9 17l-5-5" />
    </svg>
  )
}

// The insight is the shareable unit of the product; this is the one affordance to grab it as
// plain text. `contextLabel` (event name) is folded into the copied text itself -- not just
// shown on-page -- so a pasted insight is still self-contained once it's left the app.
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // ponytail: clipboard write only fails on a permission/context issue we can't recover
      // from here (no fallback UI); silently no-op rather than throw.
    }
  }

  return (
    <Tooltip label={copied ? 'Copied' : 'Copy insight'}>
      <button
        type="button"
        onClick={handleCopy}
        aria-label={copied ? 'Copied insight to clipboard' : 'Copy insight to clipboard'}
        // -m-3 + p-3 grows the tap target to a real 40px square (matches ThemeToggle's h-10
        // w-10 convention) without shifting the visible icon's position in the header row.
        // rounded-full turns that square into a circular hover/active highlight behind the icon.
        className="-m-3 mt-[-2px] flex shrink-0 cursor-pointer items-center justify-center rounded-full p-3 text-muted transition-colors hover:bg-accent/10 hover:text-accent active:bg-accent/20"
      >
        {copied ? <CheckIcon /> : <CopyIcon />}
      </button>
    </Tooltip>
  )
}

export function Insight({
  item,
  showSlot = true,
  collapsible = false,
  contextLabel,
  kicker,
  tintColor,
  accentColor,
}: {
  item: InsightItem
  showSlot?: boolean
  collapsible?: boolean
  // Race weekend the insight belongs to (e.g. "British Grand Prix"), prefixed onto the copied
  // text so it still identifies itself once pasted somewhere without the page around it.
  contextLabel?: string
  // Optional label line rendered inside the card, above the heading ("Latest verdict · ..."),
  // so a standalone card can carry its own context within the panel. A plain string renders
  // the default accent-red kicker; pass markup (e.g. a manufacturer name in its own color
  // plus a neutral customer-team list) when one uniform color doesn't fit the content.
  kicker?: ReactNode
  // Optional background wash (e.g. teamColorWithAlpha(team, 0.09)), overriding .glass's plain
  // surface color. Undefined preserves the default neutral panel used everywhere else.
  tintColor?: string
  // Optional full-strength color for the big slot number, overriding the default site accent
  // red (e.g. resolveTeamColor(team), so the number carries team identity too).
  accentColor?: string
}) {
  const [open, setOpen] = useState(true)
  const titleId = `insight-${item.slot}-title`
  const toggle = () => setOpen((o) => !o)
  const heading = (
    <h3 id={titleId} className="font-display text-[1.5625rem] font-semibold leading-[1.05] tracking-tight sm:text-[1.875rem] lg:text-[2.5rem]">
      {bindMetricSpaces(item.header)}
    </h3>
  )
  const copyText = `${contextLabel ? `${contextLabel} · ` : ''}${item.header}\n\n${item.explanation_web}`

  // Kicker + number + heading-row + body, all inside one clickable region when collapsible: a
  // reader clicking anywhere in the visually "clickable-looking" top of the card (not just the
  // heading text) gets the same toggle.
  //
  // Grid, not flex, for the number/heading/body relationship: the number sits in row 1 only
  // (shared with just the heading row), vertically centered against that row's own height via
  // align-items, which the browser computes fresh from row 1's actual content alone -- row 2
  // (body) never enters into it. That makes the number's position structurally constant across
  // collapse state, so nothing needs to flip alignment (and jump) when body's height animates;
  // a state-dependent items-center/items-start swap was tried first and caused exactly that
  // jump, since the class swap is instant while the height transition isn't. Column 1's width
  // is real grid auto-sizing (the number's actual rendered width), not a guessed padding value,
  // so body still lines up under the heading with no per-font-metrics arithmetic.
  const gridCols = showSlot ? 'grid-cols-[auto_1fr] gap-x-4 sm:gap-x-5' : 'grid-cols-1'
  const contentCol = showSlot ? 'col-start-2' : 'col-start-1'
  const content = (
    <>
      {kicker && <p className="kicker mb-4 text-sm! text-accent">{kicker}</p>}
      <div className={`grid items-center ${gridCols}`}>
        {showSlot && (
          <span
            className="col-start-1 row-start-1 font-display text-[2.7rem] font-semibold leading-none sm:text-[4.05rem]"
            style={{ color: accentColor ?? 'var(--color-accent)' }}
            aria-hidden
          >
            {String(item.slot).padStart(2, '0')}
          </span>
        )}
        <div className={`${contentCol} row-start-1 flex min-w-0 items-start justify-between gap-6`}>
          {heading}
          {/* Copy is a real nested interactive element, so its click must not also bubble
              into the outer toggle; the chevron is purely decorative and deliberately left
              un-stopped, so clicking it (or anywhere else in the header) still toggles.
              gap-6 (not tighter): both icons' -m-3 tap targets reach 12px past their own
              visible glyph, so anything less than 24px between them lets the two invisible
              hit-boxes overlap and steal each other's clicks. */}
          <div className="flex shrink-0 items-start gap-6">
            <span onClick={(e) => e.stopPropagation()}>
              <CopyButton text={copyText} />
            </span>
            {collapsible && (
              <Tooltip label={open ? 'Collapse' : 'Expand'}>
                <span
                  // -m-3 + p-3 matches CopyButton's 40px tap target.
                  className="-m-3 mt-[-0.375rem] flex shrink-0 items-center justify-center rounded-full p-3 text-muted transition-colors hover:bg-accent/10 hover:text-accent active:bg-accent/20"
                >
                  <m.svg
                    width="20"
                    height="20"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden
                    animate={{ rotate: open ? 180 : 0 }}
                    transition={expandTransition}
                  >
                    <path d="m6 9 6 6 6-6" />
                  </m.svg>
                </span>
              </Tooltip>
            )}
          </div>
        </div>
        <AnimatePresence initial={false}>
          {(!collapsible || open) && (
            <m.div
              initial={collapsible ? { height: 0, opacity: 0 } : false}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={expandTransition}
              className={`${contentCol} overflow-hidden`}
            >
              <p className="mt-4 text-[17px] leading-relaxed text-ink">
                {emphasize(item.explanation_web)}
              </p>
            </m.div>
          )}
        </AnimatePresence>
      </div>
    </>
  )

  return (
    <article
      className="glass lift rounded-[--radius-panel] p-7 sm:p-8"
      style={tintColor ? { backgroundColor: tintColor } : undefined}
      aria-labelledby={titleId}
    >
      {collapsible ? (
        <button type="button" onClick={toggle} aria-expanded={open} className="block w-full cursor-pointer text-left">
          {content}
        </button>
      ) : (
        content
      )}
    </article>
  )
}
