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
