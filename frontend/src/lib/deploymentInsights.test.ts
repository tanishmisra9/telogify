import { describe, it, expect } from 'vitest'
import { deploymentInsights } from './deploymentInsights'
import type { SeasonDeploymentScatter } from './api'

// n points inside one 10 km/h bucket, all at the same accel so the bin median is exact.
const bin = (speed: number, accel: number, n = 5): [number, number][] =>
  Array.from({ length: n }, (_, i) => [speed + (i % 5) * 0.1, accel])

// A full profile: four mid-band bins (250-290) at `mid`, two top-band bins (290+) at `top`.
const profile = (mid: number, top: number, n = 5): [number, number][] => [
  ...bin(255, mid, n),
  ...bin(265, mid, n),
  ...bin(275, mid, n),
  ...bin(285, mid, n),
  ...bin(295, top, n),
  ...bin(305, top, n),
]

describe('deploymentInsights', () => {
  // Mercedes: punch 5 / hold 1 (strongest mid-range, biggest fade)
  // Ferrari: punch 3 / hold 2 (best top-speed hold, smallest fade = most constant)
  // Honda (Aston Martin): punch 1 / hold -0.5 (leanest mid-range, runs dry up top)
  const scatter: SeasonDeploymentScatter = {
    Mercedes: profile(5, 1),
    Ferrari: profile(3, 2),
    'Aston Martin': profile(1, -0.5),
  }

  it('ranks the extremes and cites the real medians', () => {
    const rows = deploymentInsights(scatter)
    expect(rows.map((r) => r.name)).toEqual(['Mercedes', 'Ferrari', 'Honda'])

    const merc = rows[0].text
    expect(merc).toContain('Strongest mid-range deployment (+5.0 m/s² through 250-290 km/h)')
    expect(merc).toContain('sheds the most once deployment runs out (+5.0 mid-range down to +1.0 m/s² past 290)')

    const fer = rows[1].text
    expect(fer).toContain('Holds its deployment best at top speed (+2.0 m/s² past 290 km/h)')
    expect(fer).toContain('most constant deployment across the range (+3.0 mid-range vs +2.0 up top)')

    const honda = rows[2].text
    expect(honda).toContain('Leanest mid-range deployment (+1.0 m/s² through 250-290 km/h)')
    expect(honda).toContain('first to run dry up top (-0.5 m/s² past 290 km/h)')
  })

  it('caps each verdict at two clauses', () => {
    for (const row of deploymentInsights(scatter)) {
      expect(row.text.split(';').length).toBeLessThanOrEqual(2)
    }
  })

  it('lists only the member teams present in the data, keeping the works color', () => {
    const rows = deploymentInsights({ ...scatter, Mercedes: [], Alpine: profile(5, 1) })
    const mercPu = rows.find((r) => r.name === 'Mercedes')!
    expect(mercPu.teams).toEqual(['Alpine'])
    expect(mercPu.worksTeam).toBe('Mercedes')
  })

  it('goes silent with fewer than three rankable groups instead of making unanchored claims', () => {
    expect(deploymentInsights({ Mercedes: profile(5, 1), Ferrari: profile(3, 2) })).toEqual([])
  })

  it('drops a group whose bins are too sparse to trust', () => {
    // Aston's bins hold 4 samples each, below MIN_BIN_N: with it gone only two rankable
    // groups remain, so the whole block stays silent.
    const rows = deploymentInsights({
      Mercedes: profile(5, 1),
      Ferrari: profile(3, 2),
      'Aston Martin': profile(1, -0.5, 4),
    })
    expect(rows).toEqual([])
  })

  it('skips a metric with no spread rather than inventing a leader', () => {
    // Identical punch everywhere; only hold separates the groups.
    const rows = deploymentInsights({
      Mercedes: profile(3, 2.5),
      Ferrari: profile(3, 1.5),
      'Aston Martin': profile(3, 0.5),
    })
    expect(rows.length).toBe(3)
    for (const row of rows) {
      expect(row.text).not.toContain('mid-range deployment')
    }
    expect(rows[0].text).toContain('Holds its deployment best at top speed')
  })

  it('gives a between-the-extremes fallback to a group with no extreme trait', () => {
    // Red Bull sits mid-pack on both metrics among five groups.
    const rows = deploymentInsights({
      Mercedes: profile(5, 1),
      Ferrari: profile(4, 2),
      'Red Bull Racing': profile(3, 0.8),
      'Aston Martin': profile(1, -0.5),
      Audi: profile(2, 0.2),
    })
    const rbr = rows.find((r) => r.name === 'Red Bull')!
    expect(rbr.text).toBe('Sits between the extremes on every deployment measure here.')
  })
})
