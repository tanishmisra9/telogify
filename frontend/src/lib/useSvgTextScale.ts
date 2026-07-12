import { useEffect, useRef, useState } from 'react'

// These charts render a fixed-width viewBox stretched to the container's actual rendered width
// (uniform scale, no preserveAspectRatio="none") so bars/lines always fit without ever needing
// overflow-x. Text sized in the same viewBox units shrinks right along with that scale: fine on
// desktop where rendered width is close to the viewBox width, illegible on mobile where it isn't
// (measured as low as 4px). `textPx` sizes text in viewBox units that render at a constant true
// pixel size regardless of container width, while bars/lines/gridlines keep scaling as before.
export function useSvgTextScale(viewBoxWidth: number) {
  const ref = useRef<SVGSVGElement>(null)
  const [scale, setScale] = useState(1)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => {
      const renderedWidth = entry.contentRect.width
      if (renderedWidth > 0) setScale(renderedWidth / viewBoxWidth)
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [viewBoxWidth])

  return { ref, scale, textPx: (px: number) => px / scale }
}
