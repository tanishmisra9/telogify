// The Pace spread's value axis. Whiskers are already 1.5 x IQR fences, so they bound a column's "normal" laps; an OUTLIER can
// be anything (a safety-car lap 30 seconds slow stretched the axis until every box sat in the bottom quarter of the plot).
// The axis is the whiskers plus a margin of half their spread, at most; an outlier beyond that is not dropped, it is clipped
// to the edge, drawn as a marker there, and counted in the readout, so the picture is honest about what it is not showing.

export interface PaceStatsLike {
  whisker_low: number
  whisker_high: number
  outliers: number[]
}

export interface PaceAxis {
  yMin: number
  yMax: number
  capLo: number
  capHi: number
}

export function paceAxis(stats: PaceStatsLike[]): PaceAxis {
  if (stats.length === 0) return { yMin: 0, yMax: 1, capLo: 0, capHi: 1 }
  const wLo = Math.min(...stats.map((s) => s.whisker_low))
  const wHi = Math.max(...stats.map((s) => s.whisker_high))
  const margin = (wHi - wLo) * 0.5 || 0.5
  const capLo = wLo - margin
  const capHi = wHi + margin
  let lo = wLo
  let hi = wHi
  for (const s of stats) {
    for (const o of s.outliers) {
      if (o >= capLo && o <= capHi) {
        lo = Math.min(lo, o)
        hi = Math.max(hi, o)
      }
    }
  }
  const pad = (hi - lo) * 0.06 || 0.5
  return { yMin: lo - pad, yMax: hi + pad, capLo, capHi }
}

/** Split one column's outliers into those the axis shows and the counts it had to clip to an edge. */
export function splitOutliers(outliers: number[], axis: PaceAxis): { inside: number[]; slower: number; faster: number } {
  const inside: number[] = []
  let slower = 0
  let faster = 0
  for (const o of outliers) {
    if (o > axis.capHi) slower++
    else if (o < axis.capLo) faster++
    else inside.push(o)
  }
  return { inside, slower, faster }
}
