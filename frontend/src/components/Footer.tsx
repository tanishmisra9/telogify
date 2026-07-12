import { LogoWaveform } from '@/components/Logo'

// Hand-rolled to match the codebase's icon convention (no lucide-react dependency installed).
function InstagramIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <rect width="20" height="20" x="2" y="2" rx="5" ry="5" />
      <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
      <line x1="17.5" x2="17.51" y1="6.5" y2="6.5" />
    </svg>
  )
}

// App-wide footer: gives every page a bottom instead of stopping after its content. The
// noise-resolving-to-signal mark runs truly edge-to-edge (outside the site's usual max-w-[1312px]
// px-6 container) instead of sitting as a small corner icon, so the site's one glyph reads at
// the scale its idea deserves; the text label stays in the normal padded container above it.
// Purely decorative — not a link.
export function Footer() {
  return (
    <footer className="mt-24 border-t-[1.5px] border-ink pb-10">
      <div className="mx-auto max-w-[1312px] px-6 pt-8">
        <div className="flex flex-col gap-1.5 sm:flex-row sm:items-baseline sm:justify-between sm:gap-6">
          <p className="text-sm text-muted">
            Methodology inputs by{' '}
            <a
              href="https://www.instagram.com/fdataanalysis/"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-ink transition-colors hover:text-accent"
            >
              Mirco Bartolozzi @fdataanalysis
              <InstagramIcon />
            </a>{' '}
            : clean-air filtering, fuel correction model, ERS depletion signal.
          </p>
          <p className="shrink-0 text-sm text-muted">Timing data via FastF1 · 2026 season</p>
        </div>
        {/* Ahead of the copyright row, not after: on mobile everything stacks in DOM order, and
            the copyright line should read as the footer's actual final line. */}
        <p className="mt-3 text-sm text-muted">Every figure computed from official timing data. Nothing estimated.</p>
        <div className="mt-1.5 flex flex-col gap-1.5 sm:flex-row sm:items-baseline sm:justify-between sm:gap-6">
          <p className="text-sm text-muted">Let&apos;s telogify this weekend.</p>
          <p className="shrink-0 text-sm text-muted">© 2026 Tanish Misra</p>
        </div>
      </div>
      <div className="mt-6 text-ink">
        <LogoWaveform className="h-16 w-full sm:h-24" />
      </div>
    </footer>
  )
}
