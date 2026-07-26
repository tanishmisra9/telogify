import { useEffect, useState } from 'react'
import { Tooltip } from '@/components/Tooltip'

type Theme = 'light' | 'dark'

// Same hex --color-bg's oklch() renders to in each theme (sampled via canvas getImageData, not
// hand-converted -- theme-color support for oklch() itself is not dependable). Mirrors the
// pre-paint script's dark value in index.html so both agree.
const THEME_COLOR: Record<Theme, string> = { light: '#fffdd0', dark: '#181310' }

// Replaces the theme-color meta node outright rather than mutating the existing one's `content`.
// Mutating in place does update the DOM (verified), but Safari doesn't reliably repaint the
// browser chrome / iOS status-bar strip off an attribute change -- the strip kept the old theme's
// colour until a reload, which is exactly the reported symptom. Removing and re-appending forces
// it to re-read. Removes *all* matches, not just the first, so repeated toggles can't accumulate
// stale duplicates that a later querySelector might pick up instead.
function applyThemeColor(theme: Theme) {
  document.querySelectorAll('meta[name="theme-color"]').forEach((el) => el.remove())
  const meta = document.createElement('meta')
  meta.setAttribute('name', 'theme-color')
  meta.setAttribute('content', THEME_COLOR[theme])
  document.head.appendChild(meta)
}

function initialTheme(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initialTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    applyThemeColor(theme)
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
