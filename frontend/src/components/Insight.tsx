import { useState } from 'react'
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
}: {
  item: InsightItem
  showSlot?: boolean
  collapsible?: boolean
  // Race weekend the insight belongs to (e.g. "British Grand Prix"), prefixed onto the copied
  // text so it still identifies itself once pasted somewhere without the page around it.
  contextLabel?: string
  // Optional label line rendered inside the card, above the heading ("Latest verdict · ..."),
  // so a standalone card can carry its own context within the panel.
  kicker?: string
  // Optional background wash (e.g. teamColorWithAlpha(team, 0.09)), overriding .glass's plain
  // surface color. Undefined preserves the default neutral panel used everywhere else.
  tintColor?: string
}) {
  const [open, setOpen] = useState(true)
  const titleId = `insight-${item.slot}-title`
  const heading = (
    <h3 id={titleId} className="font-display text-[1.5625rem] font-semibold leading-[1.05] tracking-tight sm:text-[1.875rem] lg:text-[2.5rem]">
      {bindMetricSpaces(item.header)}
    </h3>
  )
  const copyText = `${contextLabel ? `${contextLabel} · ` : ''}${item.header}\n\n${item.explanation_web}`

  return (
    <article
      className="glass lift rounded-[--radius-panel] p-7 sm:p-8"
      style={tintColor ? { backgroundColor: tintColor } : undefined}
      aria-labelledby={titleId}
    >
      {kicker && <p className="kicker mb-4 text-sm! text-accent">{kicker}</p>}
      <div className="flex items-start gap-4 sm:gap-5">
        {showSlot && (
          <span className="font-display text-[2.7rem] font-semibold leading-none text-accent sm:text-[4.05rem]" aria-hidden>
            {String(item.slot).padStart(2, '0')}
          </span>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-6">
            {collapsible ? (
              <button
                type="button"
                onClick={() => setOpen((o) => !o)}
                aria-expanded={open}
                className="flex flex-1 items-start justify-between gap-4 text-left"
              >
                {heading}
                <Tooltip label={open ? 'Collapse' : 'Expand'}>
                  <span
                    // -m-3 + p-3 matches CopyButton's 40px tap target: the hover-color trigger
                    // area is scoped to just this icon, not the whole heading row (which is
                    // also clickable to toggle), so it's close-but-comfortable, not room-wide.
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
              </button>
            ) : (
              <div className="flex-1">{heading}</div>
            )}
            <CopyButton text={copyText} />
          </div>
          <AnimatePresence initial={false}>
            {(!collapsible || open) && (
              <m.div
                initial={collapsible ? { height: 0, opacity: 0 } : false}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={expandTransition}
                className="overflow-hidden"
              >
                <p className="mt-4 text-[17px] leading-relaxed text-ink">
                  {emphasize(item.explanation_web)}
                </p>
              </m.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </article>
  )
}
