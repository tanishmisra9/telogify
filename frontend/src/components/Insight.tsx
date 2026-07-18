import { useState, type ReactNode } from 'react'
import { AnimatePresence, m } from 'framer-motion'
import { Link } from 'react-router-dom'
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
  defaultOpen = true,
  contextLabel,
  kicker,
  tintColor,
  accentColor,
  href,
}: {
  item: InsightItem
  showSlot?: boolean
  collapsible?: boolean
  // Initial open/closed state when collapsible; only matters if collapsible is true.
  defaultOpen?: boolean
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
  // Optional route (e.g. `/weekends/2026/12`) that makes the whole card clickable. Rendered as
  // a stretched link (an absolutely-positioned <Link> under the content, inset-0) rather than
  // wrapping the card in an <a>, since the CopyButton inside is a real nested <button> and an
  // <a> containing interactive content is invalid HTML / confusing to screen readers.
  href?: string
}) {
  const [open, setOpen] = useState(defaultOpen)
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
  // Copy is a real nested interactive element, so its click must not also bubble into the
  // outer toggle; the chevron is purely decorative and deliberately left un-stopped, so
  // clicking it (or anywhere else in the header) still toggles when nested inside the
  // collapsible <button> (showSlot=true). When !showSlot, this whole group instead renders as
  // an absolutely-positioned corner overlay OUTSIDE that button (see below), so the chevron
  // needs its own onClick + stopPropagation to still toggle there -- harmless when it IS nested
  // (stops the bubble, then fires the identical toggle directly, so it's still exactly one
  // toggle per click either way). gap-6 (not tighter): both icons' -m-3 tap targets reach 12px
  // past their own visible glyph, so anything less than 24px between them lets the two
  // invisible hit-boxes overlap and steal each other's clicks.
  const buttonGroup = (
    <div className="flex shrink-0 items-start gap-6">
      <span onClick={(e) => e.stopPropagation()}>
        <CopyButton text={copyText} />
      </span>
      {collapsible && (
        <Tooltip label={open ? 'Collapse' : 'Expand'}>
          <span
            onClick={(e) => {
              e.stopPropagation()
              toggle()
            }}
            // -m-3 + p-3 matches CopyButton's 40px tap target.
            className="-m-3 mt-[-0.375rem] flex shrink-0 cursor-pointer items-center justify-center rounded-full p-3 text-muted transition-colors hover:bg-accent/10 hover:text-accent active:bg-accent/20"
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
  )
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
        {/* gap-10 (not gap-6): with justify-between, `gap` is a hard minimum flexbox will
            enforce by shrinking/wrapping the heading before it lets the two items get closer
            than that. A short-but-not-short-enough header can fit on one line right at a 24px
            minimum, reading as crowded against the buttons even though longer headers (forced
            to wrap) end their last line well short of the boundary. The larger minimum guarantees
            the same breathing room regardless of where a given header happens to wrap.
            Without a slot number, there's no rank digit to line the button row up against, so
            the buttons move out of the heading's row entirely (see the absolutely-positioned
            copy of buttonGroup below) and the heading gets the row to itself. */}
        <div className={`${contentCol} row-start-1 flex min-w-0 items-start ${showSlot ? 'justify-between gap-10' : ''}`}>
          {heading}
          {showSlot && buttonGroup}
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
      className="glass lift relative rounded-[--radius-panel] p-7 sm:p-8"
      style={tintColor ? { backgroundColor: tintColor } : undefined}
      aria-labelledby={titleId}
    >
      {href && (
        <Link
          to={href}
          aria-label={item.header}
          // Stretched link: fills the whole card so it's clickable anywhere, sitting below
          // (z-0) the copy button's own z-10 so that button keeps intercepting its own clicks
          // rather than the click falling through to this link underneath it.
          className="absolute inset-0 z-0 rounded-[--radius-panel]"
        />
      )}
      {/* Pinned to the card's own top-right corner (not the heading's row): without a slot
          number there's no rank digit for the button row to line up against, so it reads
          better as a corner affordance on the card itself than floating beside wherever the
          heading happens to sit. */}
      {!showSlot && (
        <div className="absolute right-7 top-7 z-10 sm:right-8 sm:top-8">{buttonGroup}</div>
      )}
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
