import { Tooltip } from '@/components/Tooltip'

// Icon-only, same hover treatment as BackHomeButton/CopyButton (-m-3 + p-3 for a real 40px
// target, accent tint on hover) so all of these icon-only controls read as one family.
export function BackToTopButton() {
  return (
    <div className="mt-16 flex justify-center">
      <Tooltip label="Back to top">
        <button
          type="button"
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          aria-label="Back to top"
          className="-m-3 flex shrink-0 items-center justify-center rounded-full p-3 text-muted transition-colors hover:bg-accent/10 hover:text-accent active:bg-accent/20"
        >
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="m5 12 7-7 7 7" />
            <path d="M12 19V5" />
          </svg>
        </button>
      </Tooltip>
    </div>
  )
}
