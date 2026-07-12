import { LogoWaveform } from '@/components/Logo'

// App-wide footer: gives every page a bottom instead of stopping after its content. The
// noise-resolving-to-signal mark runs truly edge-to-edge (outside the site's usual max-w-[1312px]
// px-6 container) instead of sitting as a small corner icon, so the site's one glyph reads at
// the scale its idea deserves; the text label stays in the normal padded container above it.
// Purely decorative — not a link.
export function Footer() {
  return (
    <footer className="mt-24 border-t-[1.5px] border-ink pb-10">
      <div className="mx-auto max-w-[1312px] px-6 pt-8">
        <p className="text-right text-sm text-muted">Timing data via FastF1</p>
      </div>
      <div className="mt-6 text-ink">
        <LogoWaveform className="h-16 w-full sm:h-24" />
      </div>
    </footer>
  )
}
