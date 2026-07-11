import { Tooltip } from '@/components/Tooltip'

export interface ChartTab<T extends string> {
  value: T
  label: string
  hint?: string
}

// Underline tab switcher for a chart's view control (Pace spread's Drivers/Constructors, Tyre
// degradation's compound, Gap by round's metric): the same accent-underline active state Nav.tsx
// uses for the page tabs, not a filled rounded-full pill — that read as a generic soft SaaS
// toggle, out of step with the site's editorial-brutalist sharp corners and hard-line accents.
// Sized up for in-content prominence (Nav's kicker is deliberately small wayfinding text; a
// chart tab materially changes what data is on screen, so it earns the bigger, heavier label).
export function ChartTabs<T extends string>({
  tabs,
  active,
  onChange,
  ariaLabel,
}: {
  tabs: ChartTab<T>[]
  active: T
  onChange: (value: T) => void
  ariaLabel: string
}) {
  return (
    <div className="flex items-center gap-5" role="group" aria-label={ariaLabel}>
      {tabs.map((tab) => {
        const isActive = active === tab.value
        const button = (
          <button
            type="button"
            onClick={() => onChange(tab.value)}
            aria-pressed={isActive}
            aria-label={tab.label}
            className={`inline-flex min-h-11 items-center border-b-2 font-display text-base font-medium tracking-tight transition-colors sm:text-lg ${
              isActive ? 'border-accent text-ink' : 'border-transparent text-muted hover:border-ink hover:text-ink'
            }`}
          >
            {tab.label}
          </button>
        )
        return tab.hint ? (
          <Tooltip key={tab.value} label={tab.hint}>
            {button}
          </Tooltip>
        ) : (
          <span key={tab.value}>{button}</span>
        )
      })}
    </div>
  )
}
