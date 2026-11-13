import { Tooltip } from '@/components/Tooltip'
import { MAX_ZOOM, MIN_ZOOM } from '@/lib/zoom'

const BTN =
  'inline-flex h-10 min-w-10 items-center justify-center border-[1.5px] border-ink bg-surface px-2 font-display text-lg leading-none text-ink transition-colors enabled:hover:bg-ink enabled:hover:text-bg disabled:cursor-not-allowed disabled:opacity-35'

// Zoom controls for a "by round" chart: zoom out, current level, zoom in, reset. A plain mouse has no pinch,
// so these are the discoverable way in (pinch and trackpad / ctrl-scroll work too, hinted on the buttons).
export function ZoomControls({
  zoom,
  onIn,
  onOut,
  onReset,
}: {
  zoom: number
  onIn: () => void
  onOut: () => void
  onReset: () => void
}) {
  return (
    <div className="flex items-center gap-2" role="group" aria-label="Zoom the chart">
      <Tooltip label="Zoom out">
        <button type="button" onClick={onOut} disabled={zoom <= MIN_ZOOM} aria-label="Zoom out" className={BTN}>
          −
        </button>
      </Tooltip>
      <span className="num min-w-[3rem] text-center text-sm text-muted" aria-live="polite">
        {zoom.toFixed(1)}x
      </span>
      <Tooltip label="Zoom in (or pinch)">
        <button type="button" onClick={onIn} disabled={zoom >= MAX_ZOOM} aria-label="Zoom in" className={BTN}>
          +
        </button>
      </Tooltip>
      <button type="button" onClick={onReset} disabled={zoom <= MIN_ZOOM} aria-label="Reset zoom" className={`${BTN} text-xs uppercase tracking-wider`}>
        Reset
      </button>
    </div>
  )
}
