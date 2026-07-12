// Right-edge hint that a horizontally-scrolling chart has more content off-screen: a soft fade
// to the card's own paper color (not a blur -- this site's editorial-brutalist cards don't do
// decorative blur) that disappears once there's nothing left to scroll to.
export function ScrollFadeEdge({ visible }: { visible: boolean }) {
  return (
    <div
      aria-hidden
      className={`pointer-events-none absolute inset-y-0 right-0 w-14 bg-gradient-to-l from-surface to-transparent transition-opacity duration-200 ${
        visible ? 'opacity-100' : 'opacity-0'
      }`}
    />
  )
}
