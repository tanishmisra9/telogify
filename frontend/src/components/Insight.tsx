import { emphasize } from '@/lib/emphasize'
import type { InsightItem } from '@/lib/api'

export function Insight({ item, showSlot = true }: { item: InsightItem; showSlot?: boolean }) {
  return (
    <article className="glass lift rounded-[--radius-panel] p-7 sm:p-8">
      <div className="flex items-start gap-4 sm:gap-5">
        {showSlot && (
          <span className="font-display text-[2.7rem] font-semibold leading-none text-accent sm:text-[4.05rem]">
            {String(item.slot).padStart(2, '0')}
          </span>
        )}
        <div className="min-w-0 flex-1">
          <h3 className="font-display text-[1.6875rem] font-semibold leading-[1.05] tracking-tight sm:text-[2.025rem] lg:text-[2.7rem]">
            {item.header}
          </h3>
          <p className="mt-4 text-[17px] leading-relaxed text-ink">
            {emphasize(item.explanation_web)}
          </p>
        </div>
      </div>
    </article>
  )
}
