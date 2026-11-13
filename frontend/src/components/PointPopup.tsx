import { useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, m } from 'framer-motion'
import { placeBubble } from '@/lib/placeBubble'
import type { HoveredPoint } from '@/lib/useChartPointHover'

const TIP_W = 220

// The readout for a hovered/tapped dot on a "by round" chart. Rendered in a portal on <body> in document
// coordinates (never an SVG foreignObject, which corrupts position on iOS Safari), so it sits on the page
// surface: it overlaps whatever is beside the chart, is never clipped by the card, and is kept inside the
// viewport (flipping above the dot when there is no room below). A stable key means moving between points
// slides it in place instead of closing and reopening it.
export function PointPopup({
  hovered,
  tip,
}: {
  hovered: HoveredPoint | null
  tip: { title: string; lines: string[] } | null
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [h, setH] = useState(60)
  const text = tip ? `${tip.title}|${tip.lines.join('|')}` : ''
  // Height decides whether it fits below the dot; measure it before paint (re-measured when the text changes).
  useLayoutEffect(() => {
    if (ref.current) setH(ref.current.offsetHeight)
  }, [text])

  const view =
    typeof window === 'undefined'
      ? null
      : { w: document.documentElement.clientWidth, h: window.innerHeight, scrollX: window.scrollX, scrollY: window.scrollY }
  const pos = hovered && view ? placeBubble(hovered.box, { w: TIP_W, h }, view, 'center', 0) : null

  return createPortal(
    <AnimatePresence>
      {tip && hovered && pos && (
        <m.div
          ref={ref}
          key="point-tip"
          className="glass pointer-events-none absolute z-50 rounded-xl px-3 py-2 text-xs text-ink"
          style={{ width: TIP_W }}
          initial={{ opacity: 0, left: pos.left, top: pos.top }}
          animate={{ opacity: 1, left: pos.left, top: pos.top }}
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
    </AnimatePresence>,
    document.body,
  )
}
