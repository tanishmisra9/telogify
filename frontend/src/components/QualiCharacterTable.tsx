import { TeamMark, TeamRule } from '@/components/TeamMark'
import { Tooltip } from '@/components/Tooltip'
import { emphasize } from '@/lib/emphasize'
import { heatBg, rankAsc, rankDesc } from '@/lib/heat'
import { qualiInsights } from '@/lib/qualiInsights'
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
  const insights = qualiInsights(rows, data.fastest_corner_number)

  return (
    <div className="glass rounded-[--radius-panel] p-6">
      <h2 className="font-display text-[2.025rem] font-semibold tracking-tight sm:text-[2.7rem]">Car character</h2>

      {insights.length > 0 && (
        <div className="mt-5 grid gap-4 border-b border-border pb-6 sm:grid-cols-2">
          {insights.map((ins) => (
            <div key={ins.kicker} className="rounded-[--radius-panel] border border-border p-5">
              <div className="flex items-center gap-2">
                <TeamRule team={ins.team} />
                <p className="kicker text-accent">{ins.kicker}</p>
              </div>
              <p className="mt-3 text-[15px] leading-relaxed text-ink">{emphasize(ins.text)}</p>
            </div>
          ))}
        </div>
      )}

      <div className="mt-6 overflow-x-auto">
        <table className="w-full min-w-[680px] border-collapse text-sm">
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
                    {r.fastest_corner_kmh != null ? `${r.fastest_corner_kmh.toFixed(0)} km/h` : '–'}
                  </Cell>
                  <Cell bg={heatBg(throttleRanks[i], n)}>{(r.full_throttle_pct * 100).toFixed(1)}%</Cell>
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
        Every figure is from each team's fastest clean lap in this session; cells shade toward the accent as a
        car ranks higher on that metric. A driver who crashed or never set a representative lap is not shown.
      </p>
    </div>
  )
}
