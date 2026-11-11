// Catmull-Rom to cubic-Bezier: turns a sequence of points into a smooth curve instead of
// straight polyline segments, without pulling in a shape/interpolation library. Shared by every
// chart that draws one smooth line per team (Gap by round, Deployment).
export function smoothPath(points: { x: number; y: number }[]): string {
  if (points.length < 2) return points.map((p) => `M${p.x},${p.y}`).join('')
  let d = `M${points[0].x},${points[0].y}`
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i === 0 ? i : i - 1]
    const p1 = points[i]
    const p2 = points[i + 1]
    const p3 = points[i + 2 === points.length ? i + 1 : i + 2]
    const cp1x = p1.x + (p2.x - p0.x) / 6
    const cp1y = p1.y + (p2.y - p0.y) / 6
    const cp2x = p2.x - (p3.x - p1.x) / 6
    const cp2y = p2.y - (p3.y - p1.y) / 6
    d += ` C${cp1x},${cp1y} ${cp2x},${cp2y} ${p2.x},${p2.y}`
  }
  return d
}

// Monotone cubic (Fritsch-Carlson) through the points, x strictly increasing: smooth like
// `smoothPath`, but a segment's curve never leaves the vertical range of its two end points, so it
// cannot overshoot. That matters for a gap chart whose floor is 0 (the round's best): Catmull-Rom
// can bulge above 0 between two points, drawing a team "faster than the best" where there is no
// data. Used by the season Race starts chart.
export function monotonePath(points: { x: number; y: number }[]): string {
  const n = points.length
  if (n < 2) return points.map((p) => `M${p.x},${p.y}`).join('')
  const h: number[] = []
  const s: number[] = [] // secant slope of each segment
  for (let i = 0; i < n - 1; i++) {
    h.push(points[i + 1].x - points[i].x)
    s.push(h[i] > 0 ? (points[i + 1].y - points[i].y) / h[i] : 0)
  }
  // Tangent at each point: 0 at a local extremum (sign change), else the harmonic mean of the two
  // neighbouring secants; the ends take their one secant.
  const t: number[] = new Array(n)
  t[0] = s[0]
  t[n - 1] = s[n - 2]
  for (let i = 1; i < n - 1; i++) {
    t[i] = s[i - 1] * s[i] <= 0 ? 0 : (2 * s[i - 1] * s[i]) / (s[i - 1] + s[i])
  }
  // Keep every segment monotone: cap tangents so (t_i/s)^2 + (t_{i+1}/s)^2 <= 9.
  for (let i = 0; i < n - 1; i++) {
    if (s[i] === 0) {
      t[i] = 0
      t[i + 1] = 0
      continue
    }
    const a = t[i] / s[i]
    const b = t[i + 1] / s[i]
    const r = a * a + b * b
    if (r > 9) {
      const k = 3 / Math.sqrt(r)
      t[i] = k * a * s[i]
      t[i + 1] = k * b * s[i]
    }
  }
  let d = `M${points[0].x},${points[0].y}`
  for (let i = 0; i < n - 1; i++) {
    const p0 = points[i]
    const p1 = points[i + 1]
    d += ` C${p0.x + h[i] / 3},${p0.y + (t[i] * h[i]) / 3} ${p1.x - h[i] / 3},${p1.y - (t[i + 1] * h[i]) / 3} ${p1.x},${p1.y}`
  }
  return d
}
