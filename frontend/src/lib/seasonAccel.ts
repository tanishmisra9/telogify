/** Per-team season ERS deployment/harvesting scatter -> a smoothed trend line: bin points by
 * speed and take the median longitudinal accel per bin, so 11 teams' worth of raw points (each
 * a few hundred) read as one legible line per team instead of an unreadable point cloud. */

export interface AccelBin {
  speedMid: number
  medianAccel: number
  n: number
}

export function binBySpeed(points: [number, number][], binWidthKmh = 10): AccelBin[] {
  if (points.length === 0) return []
  const buckets = new Map<number, number[]>()
  for (const [speed, accel] of points) {
    const bucket = Math.floor(speed / binWidthKmh) * binWidthKmh
    const list = buckets.get(bucket)
    if (list) list.push(accel)
    else buckets.set(bucket, [accel])
  }
  const bins: AccelBin[] = []
  for (const [bucket, accels] of buckets) {
    const sorted = [...accels].sort((a, b) => a - b)
    const mid = sorted.length / 2
    const median =
      sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[Math.floor(mid)]
    bins.push({ speedMid: bucket + binWidthKmh / 2, medianAccel: median, n: accels.length })
  }
  return bins.sort((a, b) => a.speedMid - b.speedMid)
}
