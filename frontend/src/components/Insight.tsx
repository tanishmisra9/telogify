import { useState } from 'react'
import { AnimatePresence, m } from 'framer-motion'
import { emphasize, bindMetricSpaces } from '@/lib/emphasize'
import { expandTransition } from '@/lib/motion'
import type { InsightItem } from '@/lib/api'

export function Insight({
  item,
  showSlot = true,
  collapsible = false,
}: {
  item: InsightItem
  showSlot?: boolean
  collapsible?: boolean
}) {
  const [open, setOpen] = useState(true)
  const titleId = `insight-${item.slot}-title`
  const heading = (
    <h3 id={titleId} className="font-display text-[1.5625rem] font-semibold leading-[1.05] tracking-tight sm:text-[1.875rem] lg:text-[2.5rem]">
      {bindMetricSpaces(item.header)}
    </h3>
  )

  return (
    <article className="glass lift rounded-[--radius-panel] p-7 sm:p-8" aria-labelledby={titleId}>
      <div className="flex items-start gap-4 sm:gap-5">
        {showSlot && (
          <span className="font-display text-[2.7rem] font-semibold leading-none text-accent sm:text-[4.05rem]" aria-hidden>
            {String(item.slot).padStart(2, '0')}
          </span>
        )}
        <div className="min-w-0 flex-1">
          {collapsible ? (
            <button
              type="button"
              onClick={() => setOpen((o) => !o)}
              aria-expanded={open}
              className="flex w-full items-start justify-between gap-4 text-left"
            >
              {heading}
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
                className="mt-1.5 shrink-0 text-muted"
                animate={{ rotate: open ? 180 : 0 }}
                transition={expandTransition}
              >
                <path d="m6 9 6 6 6-6" />
              </m.svg>
            </button>
          ) : (
            heading
          )}
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
