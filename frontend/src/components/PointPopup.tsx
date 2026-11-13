import type { RefObject } from 'react'
import { AnimatePresence, m } from 'framer-motion'
import type { HoveredPoint } from '@/lib/useChartPointHover'

const TIP_W = 220

// The readout for a hovered/tapped dot on a "by round" chart. A plain HTML box outside the scrolling
// container (never an SVG foreignObject, which corrupts position on iOS Safari), with a stable key so
// moving between points slides it in place instead of closing and reopening it. Clamped to `wrapRef`
// so it can't run off either edge of the card.
export function PointPopup({
  hovered,
  tip,
  wrapRef,
}: {
  hovered: HoveredPoint | null
  tip: { title: string; lines: string[] } | null
  wrapRef: RefObject<HTMLElement | null>
}) {
  const wrapW = wrapRef.current?.clientWidth ?? 0
  const left = hovered ? Math.min(Math.max(hovered.left - TIP_W / 2, 0), Math.max(0, wrapW - TIP_W)) : 0
  return (
    <AnimatePresence>
      {tip && hovered && (
        <m.div
          key="point-tip"
          className="glass pointer-events-none absolute z-10 rounded-xl px-3 py-2 text-xs text-ink"
          style={{ width: TIP_W }}
          initial={{ opacity: 0, left, top: hovered.top + 16 }}
          animate={{ opacity: 1, left, top: hovered.top + 16 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.14 }}
        >
          <div className="font-medium">{tip.title}</div>
          {tip.lines.map((l) => (
            <div key={l} className="mt-0.5 text-muted">
              {l}
            </div>
          ))}
        </m.div>
      )}
    </AnimatePresence>
  )
}
