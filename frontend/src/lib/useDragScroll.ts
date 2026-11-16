import { useEffect, type RefObject } from 'react'

// Click-and-drag panning for a scrolling box, mouse only: touch already pans natively, and a two-finger
// pinch is useChartZoom's. Nothing happens until the pointer moves DRAG_PX, so a plain click or hover on
// whatever is inside is untouched. Once dragging, the box captures the pointer: the drag survives leaving
// the box or the window, and the dots under the cursor stop receiving mouseenter (no readout swapping).
// The panning itself is just scrollLeft/scrollTop, so every scroll listener (axis sync, readout close) runs
// as it does for the scrollbars. A press in the scrollbar gutter is left to the browser.
const DRAG_PX = 4

export function useDragScroll(ref: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const el = ref.current
    if (!el) return
    let drag: { id: number; x: number; y: number; left: number; top: number; active: boolean } | null = null
    const scrollable = () => el.scrollWidth > el.clientWidth || el.scrollHeight > el.clientHeight

    const onDown = (e: PointerEvent) => {
      if (e.pointerType !== 'mouse' || e.button !== 0 || !scrollable()) return
      const r = el.getBoundingClientRect()
      if (e.clientX - r.left >= el.clientWidth || e.clientY - r.top >= el.clientHeight) return
      drag = { id: e.pointerId, x: e.clientX, y: e.clientY, left: el.scrollLeft, top: el.scrollTop, active: false }
    }
    const onMove = (e: PointerEvent) => {
      if (e.pointerType !== 'mouse') return
      // Button already up: the press ended where we never heard of it (released outside the box before the
      // threshold, so no capture and no pointerup here). Disarm, or hovering back in would scroll the chart.
      if (drag && !(e.buttons & 1)) onEnd(e)
      if (!drag) {
        el.style.cursor = scrollable() ? 'grab' : '' // only promise a drag where there is somewhere to go
        return
      }
      if (e.pointerId !== drag.id) return
      const dx = e.clientX - drag.x
      const dy = e.clientY - drag.y
      if (!drag.active) {
        if (Math.hypot(dx, dy) < DRAG_PX) return
        drag.active = true
        el.setPointerCapture(e.pointerId)
        el.style.cursor = 'grabbing'
      }
      el.scrollLeft = drag.left - dx
      el.scrollTop = drag.top - dy
    }
    const onEnd = (e: PointerEvent) => {
      if (!drag || e.pointerId !== drag.id) return
      drag = null
      el.style.cursor = scrollable() ? 'grab' : ''
    }

    el.addEventListener('pointerdown', onDown)
    el.addEventListener('pointermove', onMove)
    el.addEventListener('pointerup', onEnd)
    el.addEventListener('pointercancel', onEnd)
    el.addEventListener('lostpointercapture', onEnd)
    return () => {
      el.removeEventListener('pointerdown', onDown)
      el.removeEventListener('pointermove', onMove)
      el.removeEventListener('pointerup', onEnd)
      el.removeEventListener('pointercancel', onEnd)
      el.removeEventListener('lostpointercapture', onEnd)
    }
  }, [ref])
}
