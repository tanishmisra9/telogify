import { useEffect, useState } from 'react'
import { Tooltip } from '@/components/Tooltip'

type Theme = 'light' | 'dark'

function initialTheme(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initialTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
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
        className="flex h-10 w-10 items-center justify-center border-[1.5px] border-ink text-ink transition-colors hover:bg-ink hover:text-bg"
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
