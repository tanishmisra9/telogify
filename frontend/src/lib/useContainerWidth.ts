import { useEffect, useState, type RefObject } from 'react'

// Rendered width of a chart's container, floored (a fractional width makes the svg a sub-pixel wider than its box and
// reads as a phantom scrollbar). A width of 0 means the chart sits in a collapsed section (display:none): keep the last
// real width so re-opening does not re-lay out and visibly morph.
export function useContainerWidth(ref: RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => entry.contentRect.width > 0 && setWidth(Math.floor(entry.contentRect.width)))
    observer.observe(el)
    return () => observer.disconnect()
  }, [ref])
  return width
}
