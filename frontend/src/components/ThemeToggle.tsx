import { useEffect, useRef, useState } from 'react'
import { Tooltip } from '@/components/Tooltip'

type Theme = 'light' | 'dark'

// Same hex --color-bg's oklch() renders to in each theme (sampled via canvas getImageData, not
// hand-converted -- theme-color support for oklch() itself is not dependable). Mirrors the
// pre-paint script's dark value in index.html so both agree.
const THEME_COLOR: Record<Theme, string> = { light: '#fffdd0', dark: '#181310' }

// Kept for Safari 15-18.6 and Chrome/Android, which do honour theme-color. It is NOT what tints
// the bar on Safari 26+: that version still parses the tag and then discards the value entirely,
// deriving its toolbar colour from CSS instead -- the background-color of a fixed/sticky element
// at the viewport edge (here Nav's `sticky top-0` <header>), falling back to <body>. So do not
// add complexity here trying to fix the iOS strip; a previous attempt to force a repaint by
// replacing this node outright changed nothing on-device, because the value is never read.
function applyThemeColor(theme: Theme) {
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLOR[theme])
}

// Safari 26 derives its toolbar tint from the sticky header's background but samples it at paint
// time, so flipping `data-theme` (which only changes the custom property the header resolves) does
// not re-tint the strip -- it keeps the previous theme's colour until a reload, which is exactly
// the reported symptom. Because the header is translucent (`bg-glass` + `backdrop-blur-md`), what
// Safari samples is a blend of the bar and whatever is scrolled under it, so it must re-sample as
// content moves; nudging the scroll position by a single pixel for one frame is the cheapest way
// to trigger that without touching the design. Imperceptible, and restores the exact offset.
function nudgeSafariToolbarResample() {
  const y = window.scrollY
  window.scrollBy(0, 1)
  requestAnimationFrame(() => window.scrollTo(0, y))
}

function initialTheme(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const isFirstRun = useRef(true)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    applyThemeColor(theme)
    // Skip on mount: the strip is already correct from the pre-paint script in index.html, and
    // scrolling the page on first load would fight ScrollToTop and any deep link.
    if (isFirstRun.current) {
      isFirstRun.current = false
    } else {
      nudgeSafariToolbarResample()
    }
    try {
      localStorage.setItem('theme', theme)
    } catch {
      /* private mode: theme still applies for the session */
    }
  }, [theme])

  const next: Theme = theme === 'light' ? 'dark' : 'light'

  return (
    <Tooltip label={`Switch to ${next} mode`}>
      <button
        type="button"
        onClick={() => setTheme(next)}
        aria-label={`Switch to ${next} mode`}
        className="flex h-10 w-10 items-center justify-center text-ink transition-colors hover:bg-ink hover:text-bg"
      >
        {theme === 'light' ? (
          // Moon: click to go dark.
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
          </svg>
        ) : (
          // Sun: click to go light.
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.4 1.4M17.6 17.6 19 19M19 5l-1.4 1.4M6.4 17.6 5 19" />
          </svg>
        )}
      </button>
    </Tooltip>
  )
}
