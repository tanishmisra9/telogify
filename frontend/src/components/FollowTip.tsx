import { useEffect, useRef, type MutableRefObject, type RefObject } from 'react'
import { createPortal } from 'react-dom'
import { useReducedMotion } from 'framer-motion'
import { useCanHover } from '@/lib/useCanHover'
import { placeFollow, type Box } from '@/lib/placeBubble'
import type { FollowTipAt } from '@/lib/useFollowTip'

const TIP_MAX_W = 270
// Tuning knobs for how the tip feels: the share of the remaining distance covered each frame (higher = snappier), and the
// fade-in. 0.28 settles in ~250ms and still reads as the tip being pulled along by the cursor.
const EASE = 0.28

const docBox = (el: Element): Box => {
  const r = el.getBoundingClientRect()
  return { left: r.left + window.scrollX, top: r.top + window.scrollY, right: r.right + window.scrollX, bottom: r.bottom + window.scrollY }
}

// The readout for whatever the pointer is on. It FOLLOWS the pointer (a frame loop eases it toward the target spot beside
// the pointer, so it glides after the cursor and between rows instead of sitting still), and it stays clear of the thing
// being read: the element marked `data-row={key}` inside `container` (a car's glyph + label, a box-plot column's marks).
// It never delays (a hover delay reads as broken), fades in, and snaps instead of easing under prefers-reduced-motion.
// In a portal on <body> in document coordinates, never an SVG foreignObject; pointer-events-none so it never steals the hover.
export function FollowTip({
  at, tip, pointer, container,
}: {
  at: FollowTipAt | null
  tip: { title: string; lines: string[] } | null
  pointer: MutableRefObject<{ x: number; y: number }>
  container?: RefObject<Element | null>
}) {
  const ref = useRef<HTMLDivElement>(null)
  const reduce = useReducedMotion()
  // Touch: sit ABOVE the tap (a finger hides what is below and beside it); a mouse gets the default below-right.
  const canHover = useCanHover()
  const keyRef = useRef<string | null>(null)
  keyRef.current = at?.key ?? null
  const live = !!at && !!tip

  useEffect(() => {
    const el = ref.current
    if (!live || !el) return
    let raf = 0
    let cur: { x: number; y: number } | null = null
    let sig = ''
    let settled = false
    let stick = { x: false, y: false } // which flips were in effect last frame (hysteresis: see placeFollow)
    const tick = () => {
      // Once the tip has reached its spot and nothing it depends on changed (hovered key, pointer, page scroll), skip the DOM
      // reads: the loop keeps ticking so it wakes the frame the pointer moves, but costs nothing while the cursor rests.
      const k = keyRef.current
      const p = pointer.current
      const s = `${k}|${p.x}|${p.y}|${window.scrollX}|${window.scrollY}`
      if (settled && s === sig) {
        raf = requestAnimationFrame(tick)
        return
      }
      sig = s
      const own = k && container?.current ? container.current.querySelector(`[data-row="${k.replace(/["\\]/g, '\\$&')}"]`) : null
      const view = { w: document.documentElement.clientWidth, h: window.innerHeight, scrollX: window.scrollX, scrollY: window.scrollY }
      const target = placeFollow(p, { w: el.offsetWidth, h: el.offsetHeight }, view, own ? docBox(own) : null, 16, 18, 8, 8, 4, !canHover, stick)
      stick = { x: target.flipX, y: target.flipY }
      if (!cur || reduce) cur = { x: target.left, y: target.top } // first frame (or reduced motion): no travel from the corner
      else {
        cur.x += (target.left - cur.x) * EASE
        cur.y += (target.top - cur.y) * EASE
      }
      settled = Math.abs(target.left - cur.x) < 0.3 && Math.abs(target.top - cur.y) < 0.3
      if (settled) cur = { x: target.left, y: target.top }
      el.style.transform = `translate3d(${cur.x}px, ${cur.y}px, 0)`
      el.style.opacity = '1'
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [live, reduce, pointer, container, canHover])

  if (!live || !tip || typeof window === 'undefined') return null
  return createPortal(
    <div
      ref={ref}
      role="tooltip"
      className="glass pointer-events-none absolute left-0 top-0 z-50 rounded-xl px-3 py-2 text-xs text-ink"
      style={{ width: 'max-content', maxWidth: `min(${TIP_MAX_W}px, calc(100vw - 16px))`, opacity: 0, transition: 'opacity 100ms ease-out', willChange: 'transform' }}
    >
      <div className="font-medium">{tip.title}</div>
      {tip.lines.map((l, i) => (
        <div key={`${i}-${l}`} className="mt-0.5 text-muted">
          {l}
        </div>
      ))}
    </div>,
    document.body,
  )
}
