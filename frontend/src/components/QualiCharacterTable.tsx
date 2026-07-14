import { useRef, useState } from 'react'
import { AnimatePresence, m } from 'framer-motion'
import { ScrollFadeEdge } from '@/components/ScrollFadeEdge'
import { TeamMark, TeamRule } from '@/components/TeamMark'
import { Tooltip } from '@/components/Tooltip'
import { bindMetricSpaces, emphasize } from '@/lib/emphasize'
import { heatBg, rankAsc, rankDesc } from '@/lib/heat'
import { driverName } from '@/lib/drivers'
import { expandTransition } from '@/lib/motion'
import { teamColorWithAlpha } from '@/lib/teamColors'
import { useScrollFade } from '@/lib/useScrollFade'
import type { QualiCharacterData, QualiInsightItem } from '@/lib/api'

// Collapsible to just its heading on mobile, open by default; desktop always shows the full
// card outright (the chevron only renders on mobile, and the CSS override on the text keeps it
// visible on desktop even in the state's closed default, so there's no toggle to reach for there).
function InsightCard({ item }: { item: QualiInsightItem }) {
  const [open, setOpen] = useState(true)
  return (
    <div
      className="rounded-[--radius-panel] border border-border p-5"
      style={item.team ? { backgroundColor: teamColorWithAlpha(item.team, 0.09) } : undefined}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 text-left md:pointer-events-none"
      >
        <div className="flex items-center gap-2">
          {item.team && <TeamRule team={item.team} />}
          <p className="kicker text-accent">{item.team ?? 'Qualifying'}</p>
        </div>
        <Tooltip label={open ? 'Collapse' : 'Expand'}>
          <span
            // Same 40px tap-target convention as Insight.tsx's chevron: the hover-color area is
            // scoped to the icon, not the whole (also-clickable) header row.
            className="-m-3 flex shrink-0 items-center justify-center rounded-full p-3 text-muted transition-colors hover:bg-accent/10 hover:text-accent active:bg-accent/20 md:hidden"
          >
            <m.svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden
              animate={{ rotate: open ? 180 : 0 }}
              transition={expandTransition}
            >
              <path d="m6 9 6 6 6-6" />
            </m.svg>
          </span>
        </Tooltip>
      </button>
      {/* Desktop: always shown, nothing to animate. Mobile: animated height/opacity collapse,
          matching every other disclosure on the site instead of CSS `hidden`'s instant snap. */}
      <div className="hidden md:block">
        <p className="mt-3 text-[15px] font-semibold leading-snug text-ink">{bindMetricSpaces(item.header)}</p>
        <p className="mt-2 text-[15px] leading-relaxed text-ink">{emphasize(item.explanation_web)}</p>
      </div>
      <div className="md:hidden">
        <AnimatePresence initial={false}>
          {open && (
            <m.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={expandTransition}
              className="overflow-hidden"
            >
              <p className="mt-3 text-[15px] font-semibold leading-snug text-ink">{bindMetricSpaces(item.header)}</p>
              <p className="mt-2 text-[15px] leading-relaxed text-ink">{emphasize(item.explanation_web)}</p>
            </m.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

function CharacterInsights({ insights }: { insights: QualiInsightItem[] }) {
  if (insights.length === 0) return null
  return (
    <div className="mt-5 grid gap-4 border-b border-border pb-6 sm:grid-cols-2">
      {insights.map((item) => (
        <InsightCard key={item.slot} item={item} />
      ))}
    </div>
  )
}

function Cell({ children, bg }: { children: React.ReactNode; bg: string }) {
  return (
    <td className="num px-4 py-3 text-right text-sm whitespace-nowrap" style={{ backgroundColor: bg }}>
      {children}
    </td>
  )
}

function HeadCell({ label, hint, align = 'right' }: { label: React.ReactNode; hint: string; align?: 'left' | 'right' }) {
  return (
    <th className={`px-4 py-2.5 font-medium ${align === 'right' ? 'text-right' : 'text-left'}`}>
      <Tooltip label={hint}>
        <span tabIndex={0} className="cursor-help">{label}</span>
      </Tooltip>
    </th>
  )
}

export function QualiCharacterTable({
  data,
  insights,
}: {
  data: QualiCharacterData
  insights: QualiInsightItem[]
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canScrollRight = useScrollFade(containerRef)

  if (data.rows.length === 0) {
    return <p className="text-sm text-muted">No qualifying car-character data yet.</p>
  }

  const rows = data.rows
  const n = rows.length
  const lapRanks = rankAsc(rows.map((r) => r.lap_time_s))
  const topSpeedRanks = rankDesc(rows.map((r) => r.top_speed_kmh))
  const minSpeedRanks = rankDesc(rows.map((r) => r.min_speed_kmh))
  const cornerRanks = rankDesc(rows.map((r) => r.fastest_corner_kmh))
  const throttleRanks = rankDesc(rows.map((r) => r.full_throttle_pct))

  return (
    <div className="glass rounded-[--radius-panel] p-6">
      <h2 className="font-display text-[2.025rem] font-semibold tracking-tight sm:text-[2.7rem]">Car character</h2>

      <CharacterInsights insights={insights} />

      <div className="relative mt-6">
      <div ref={containerRef} className="overflow-x-auto overscroll-x-contain">
        <table className="w-full min-w-[680px] border-collapse text-sm" aria-label="Qualifying car character by team">
          <thead>
            <tr className="text-left text-xs text-muted">
              <th className="px-4 py-2.5 font-medium">Team</th>
              <HeadCell label="Lap time (s)" hint="Best single-lap qualifying time" />
              <HeadCell label="Top speed (km/h)" hint="Highest speed reached on the lap" />
              <HeadCell label="Min speed (km/h)" hint="Slowest point on the lap, in the tightest corner: a read on mechanical grip" />
              <HeadCell
                label={`Fastest corner (km/h)${data.fastest_corner_number != null ? ` (T${data.fastest_corner_number})` : ''}`}
                hint="Speed carried through the lap's fastest corner: a read on downforce"
              />
              <HeadCell label="Full throttle (%)" hint="Share of the lap spent at full throttle" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              return (
                <tr key={r.constructor} className="border-t border-border">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <TeamMark team={r.constructor} className="font-medium" />
                      <span className="whitespace-nowrap text-xs text-muted">{driverName(r.driver)}</span>
                    </div>
                  </td>
                  <Cell bg={heatBg(lapRanks[i], n)}>{r.lap_time_s.toFixed(3)}s</Cell>
                  <Cell bg={heatBg(topSpeedRanks[i], n)}>{r.top_speed_kmh.toFixed(0)} km/h</Cell>
                  <Cell bg={heatBg(minSpeedRanks[i], n)}>{r.min_speed_kmh.toFixed(0)} km/h</Cell>
                  <Cell bg={heatBg(cornerRanks[i], n)}>
                    {r.fastest_corner_kmh != null ? `${r.fastest_corner_kmh.toFixed(0)} km/h` : '–'}
                  </Cell>
                  <Cell bg={heatBg(throttleRanks[i], n)}>{(r.full_throttle_pct * 100).toFixed(1)}%</Cell>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <ScrollFadeEdge visible={canScrollRight} />
      </div>

      {data.sector_dominance.length > 0 && (
        <div className="mt-6 border-t border-border pt-5">
          <p className="kicker text-muted">Sector dominance</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            {data.sector_dominance.map((d) => (
              <div
                key={d.sector}
                className="rounded-[--radius-panel] border border-border p-3"
                style={d.constructor ? { backgroundColor: teamColorWithAlpha(d.constructor, 0.09) } : undefined}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-muted">Sector {d.sector}</span>
                  {d.constructor && <TeamRule team={d.constructor} />}
                </div>
                {d.constructor ? (
                  <>
                    <p className="mt-1 text-sm font-medium text-ink">{d.constructor}</p>
                    {/* margin_s is the cushion OVER the next-best team; "+X.XXXs" reads as a
                        deficit everywhere else on the site, so phrase it as an advantage. */}
                    <p className="num mt-0.5 text-sm text-muted">
                      {d.best_time_s.toFixed(3)}s
                      {d.margin_s != null && <span className="text-accent"> {d.margin_s.toFixed(3)}s clear</span>}
                    </p>
                  </>
                ) : (
                  <p className="mt-1 text-sm text-muted">No clear best</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      <p className="mt-2 text-xs text-muted">
        Every figure is from each team's fastest representative lap in this session; cells shade toward the accent as a
        car ranks higher on that metric. A driver who never set a representative lap is not shown.
      </p>
    </div>
  )
}
