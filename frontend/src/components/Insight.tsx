import { emphasize } from '@/lib/emphasize'
import type { InsightItem } from '@/lib/api'

export function Insight({ item }: { item: InsightItem }) {
  return (
    <article className="glass rounded-[--radius-panel] p-7">
      <div className="flex items-baseline gap-4">
        <span className="num text-sm text-accent">{String(item.slot).padStart(2, '0')}</span>
        <h3 className="text-xl font-semibold leading-snug tracking-tight">{item.header}</h3>
      </div>
      <p className="mt-3 pl-9 text-[15px] leading-relaxed text-muted">
        {emphasize(item.explanation_web)}
      </p>
    </article>
  )
}
