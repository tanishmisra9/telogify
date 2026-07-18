import { LogoWaveform } from '@/components/Logo'
import { Tooltip } from '@/components/Tooltip'
import { useApi, type WeekendSummary } from '@/lib/api'

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
  // Same "current season" derivation as SeasonRedirect/SeasonStats (max year among ingested
  // weekends), not a hardcoded year -- omit the season clause entirely rather than show a stale
  // or blank one before this resolves.
  const { data: weekends } = useApi<WeekendSummary[]>('/weekends')
  const years = (weekends ?? []).map((w) => w.year)
  const year = years.length > 0 ? Math.max(...years) : null

  return (
    <footer className="mt-24 border-t-[1.5px] border-ink pb-10">
      <div className="mx-auto max-w-[1312px] px-6 pt-8">
        {/* Two stacks with one shared gap so the vertical rhythm is even on both sides: the
            copyright sits directly under the FastF1 line, and on mobile (DOM order) it still
            reads as the footer's actual final line. */}
        <div className="flex flex-col gap-1.5 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
          <div className="flex flex-col gap-1.5">
            <p className="text-sm text-muted">
              Methodology inputs by{' '}
              <Tooltip label="Instagram account">
                <a
                  href="https://www.instagram.com/fdataanalysis/"
                  target="_blank"
                  rel="noopener noreferrer"
                  // -mx/-my offset the padding so the pill highlight appears without shifting the
                  // prose; same accent hover recipe as the copy/collapse icon buttons. -mx-1 (not
                  // -mx-1.5): the wider pill bled far enough left to overlap the "y" in the
                  // preceding "by".
                  className="-mx-1 -my-1 inline-flex items-center gap-1 rounded-full px-1 py-1 text-ink transition-colors hover:bg-accent/10 hover:text-accent active:bg-accent/20"
                >
                  Mirco Bartolozzi
                  {/* The icon stands in for "@" entirely (no literal @ character) -- gap-0.5, not
                      the outer gap-1, since it's replacing a character glued to the handle, not a
                      word-space. */}
                  <span className="inline-flex items-center gap-0.5">
                    <InstagramIcon />
                    fdataanalysis
                  </span>
                </a>
              </Tooltip>
              : clean-air filtering, fuel correction model, ERS depletion signal.
            </p>
            <p className="text-sm text-muted">Every figure computed from official timing data. Nothing estimated.</p>
            <p className="text-sm text-muted">Let&apos;s telogify this weekend.</p>
          </div>
          <div className="flex shrink-0 flex-col gap-1.5 sm:items-end sm:text-right">
            <p className="text-sm text-muted">Timing data via FastF1{year != null ? ` · ${year} season` : ''}</p>
            <p className="text-sm text-muted">© 2026 Tanish Misra</p>
          </div>
        </div>
      </div>
      <div className="mt-6 text-ink">
        <LogoWaveform className="h-16 w-full sm:h-24" />
      </div>
    </footer>
  )
}
