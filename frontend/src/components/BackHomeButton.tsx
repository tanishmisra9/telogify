import { Link } from 'react-router-dom'
import { Tooltip } from '@/components/Tooltip'

// Icon-only back link with a tooltip label, same shape as WeekendPage's "Back to weekends"
// control (-m-3 + p-3 gives the same 40px circular hover/active target as the copy/collapse
// buttons) so this reads as the same affordance wherever it appears.
export function BackHomeButton({ className }: { className?: string }) {
  return (
    <Tooltip label="Back to home" align="start">
      <Link
        to="/"
        aria-label="Back to home"
        className={`-m-3 inline-flex shrink-0 items-center justify-center rounded-full p-3 text-muted transition-colors hover:bg-accent/10 hover:text-accent active:bg-accent/20 ${className ?? ''}`}
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="m15 18-6-6 6-6" />
        </svg>
      </Link>
    </Tooltip>
  )
}
