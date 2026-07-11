import { Link } from 'react-router-dom'
import { LogoWaveform } from '@/components/Logo'

// App-wide footer: gives every page a bottom instead of stopping after its content. The
// noise-resolving-to-signal mark runs full-bleed across the footer instead of sitting as a
// small corner icon, so the site's one glyph reads at the scale its idea deserves.
export function Footer() {
  return (
    <footer className="mt-24 border-t-[1.5px] border-ink">
      <div className="mx-auto max-w-[1312px] px-6 py-8">
        <p className="text-right text-sm text-muted">Timing data via FastF1</p>
        <Link to="/" aria-label="Telogify home" className="mt-4 block text-ink">
          <LogoWaveform className="h-10 w-full sm:h-14" />
        </Link>
      </div>
    </footer>
  )
}
