import { TeamMark } from '@/components/TeamMark'
import { Tooltip } from '@/components/Tooltip'
import { heatBg, rankAsc, rankDesc } from '@/lib/heat'
import { summarizeCarCharacter } from '@/lib/qualiSummary'
import type { QualiCharacterData } from '@/lib/api'

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
        <span className="cursor-help underline decoration-dotted decoration-muted/60 underline-offset-4">{label}</span>
      </Tooltip>
    </th>
  )
}

export function QualiCharacterTable({ data }: { data: QualiCharacterData }) {
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
  const summary = summarizeCarCharacter(rows)

  return (
    <div className="glass rounded-[--radius-panel] p-6">
      <h2 className="font-display text-[2.025rem] font-semibold tracking-tight sm:text-[2.7rem]">Car character</h2>

      <ul className="mt-4 grid gap-2 border-b border-border pb-6 sm:grid-cols-2">
        {summary.map((line, i) => {
          const splitAt = line.indexOf(':')
          const who = splitAt === -1 ? line : line.slice(0, splitAt)
          const rest = splitAt === -1 ? '' : line.slice(splitAt)
          return (
            <li key={rows[i].constructor} className="text-sm leading-relaxed text-muted">
              <span className="font-medium text-ink">{who}</span>
              {rest}
            </li>
          )
        })}
      </ul>

      <div className="mt-6 overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs text-muted">
              <th className="px-4 py-2.5 font-medium">Team</th>
              <HeadCell label="Lap time" hint="Best single-lap qualifying time" />
              <HeadCell label="Top speed" hint="Highest speed reached on the lap (km/h)" />
              <HeadCell label="Min speed" hint="Slowest point on the lap, in the tightest corner: a read on mechanical grip" />
              <HeadCell
                label={`Fastest corner${data.fastest_corner_number != null ? ` (T${data.fastest_corner_number})` : ''}`}
                hint="Speed carried through the lap's fastest corner: a read on downforce"
              />
              <HeadCell label="Full throttle" hint="Share of the lap spent at full throttle" />
              <HeadCell label="Character" hint="Plain-language read on the car's balance, from the numbers to the left" align="left" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              return (
                <tr key={r.constructor} className="border-t border-border">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <TeamMark team={r.constructor} className="font-medium" />
                      <span className="whitespace-nowrap text-xs text-muted">({r.driver})</span>
                    </div>
                  </td>
                  <Cell bg={heatBg(lapRanks[i], n)}>{r.lap_time_s.toFixed(3)}s</Cell>
                  <Cell bg={heatBg(topSpeedRanks[i], n)}>{r.top_speed_kmh.toFixed(0)} km/h</Cell>
                  <Cell bg={heatBg(minSpeedRanks[i], n)}>{r.min_speed_kmh.toFixed(0)} km/h</Cell>
                  <Cell bg={heatBg(cornerRanks[i], n)}>
                    {r.fastest_corner_kmh != null ? `${r.fastest_corner_kmh.toFixed(0)} km/h` : '\u2013'}
                  </Cell>
                  <Cell bg={heatBg(throttleRanks[i], n)}>{(r.full_throttle_pct * 100).toFixed(1)}%</Cell>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Tooltip label="Drag read, set by top speed against full-throttle time">
                        <span className="cursor-help whitespace-nowrap rounded-full border border-border px-2 py-0.5 text-xs text-muted">
                          {r.drag_label}
                        </span>
                      </Tooltip>
                      {r.is_top_speed_leader && (
                        <Tooltip label="Highest top speed in the field">
                          <span className="cursor-help whitespace-nowrap rounded-full bg-accent/15 px-2 py-0.5 text-xs text-accent">
                            best top speed
                          </span>
                        </Tooltip>
                      )}
                      {r.is_corner_speed_leader && (
                        <Tooltip label="Highest speed through the lap's fastest corner">
                          <span className="cursor-help whitespace-nowrap rounded-full bg-accent/15 px-2 py-0.5 text-xs text-accent">
                            best downforce
                          </span>
                        </Tooltip>
                      )}
                      {r.is_grip_leader && (
                        <Tooltip label="Highest minimum corner speed">
                          <span className="cursor-help whitespace-nowrap rounded-full bg-accent/15 px-2 py-0.5 text-xs text-accent">
                            best grip
                          </span>
                        </Tooltip>
                      )}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {data.sector_dominance.length > 0 && (
        <p className="mt-5 text-xs text-muted">
          Sector dominance:{' '}
          {data.sector_dominance
            .map((d) => `S${d.sector} ${d.constructor}${d.margin_s != null ? ` (+${d.margin_s.toFixed(3)}s)` : ''}`)
            .join(', ')}
        </p>
      )}
      <p className="mt-2 text-xs text-muted">
        Labels fall out of the measured numbers only: top speed and full-throttle time set the
        drag read, minimum speed flags strong grip in the slow stuff.
      </p>
    </div>
  )
}
