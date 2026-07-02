import { emphasize } from '@/lib/emphasize'
import type { InsightItem } from '@/lib/api'

export function Insight({ item }: { item: InsightItem }) {
  return (
    <article className="glass lift rounded-[--radius-panel] p-7 sm:p-8">
      <div className="flex items-start gap-5">
        <span className="font-display text-6xl leading-none text-accent sm:text-7xl">
          {String(item.slot).padStart(2, '0')}
        </span>
        <div className="flex-1">
          <h3 className="font-display text-4xl leading-[1.05] tracking-tight sm:text-5xl">
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
