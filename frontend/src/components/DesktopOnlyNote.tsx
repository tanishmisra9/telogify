// Flags a visualization that's been swapped out on mobile. A real `.glass` panel (solid border,
// hard shadow) rather than muted placeholder text or a dashed box, so it reads as a deliberate
// callout instead of something a reader skims past.
export function DesktopOnlyNote({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`glass rounded-[--radius-panel] p-5 md:hidden ${className}`}>
      <p className="kicker text-accent">Desktop experience</p>
      <p className="mt-1.5 text-sm leading-relaxed text-ink">{children}</p>
    </div>
  )
}
