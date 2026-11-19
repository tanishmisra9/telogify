import { useEffect, useState } from 'react'

// True on a device with a real hovering pointer (mouse, trackpad). A touch device has no hover, so a readout there is docked
// instead of following a cursor. The capability, not the width: a narrow desktop window still has a cursor.
const QUERY = '(hover: hover) and (pointer: fine)'

export function useCanHover(): boolean {
  const [can, setCan] = useState(() => window.matchMedia(QUERY).matches)
  useEffect(() => {
    const mql = window.matchMedia(QUERY)
    const onChange = () => setCan(mql.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [])
  return can
}
