import { describe, it, expect } from 'vitest'
import { monotonePath, smoothPath } from './svgPath'

type Point = { x: number; y: number }

// Parses the `M{x},{y} C{cp1x},{cp1y} {cp2x},{cp2y} {x},{y} ...` shape smoothPath produces,
// so tests can assert on structure/values instead of matching the raw string.
function parsePath(d: string) {
  const nums = (s: string) => s.split(',').map(Number)
  const [moveCmd, ...curveCmds] = d.split(' ').filter(Boolean)
  const moveTo: Point | null = moveCmd
    ? (([x, y]) => ({ x, y }))(nums(moveCmd.slice(1)))
    : null
  const curves: { cp1: Point; cp2: Point; to: Point }[] = []
  for (let i = 0; i < curveCmds.length; i += 3) {
    const [cp1x, cp1y] = nums(curveCmds[i].slice(1))
    const [cp2x, cp2y] = nums(curveCmds[i + 1])
    const [x, y] = nums(curveCmds[i + 2])
    curves.push({ cp1: { x: cp1x, y: cp1y }, cp2: { x: cp2x, y: cp2y }, to: { x, y } })
  }
  return { moveTo, curves }
}

describe('smoothPath', () => {
  it('returns an empty string for no points', () => {
    expect(smoothPath([])).toBe('')
  })

  it('returns a single M command for one point, no curve', () => {
    expect(smoothPath([{ x: 5, y: 10 }])).toBe('M5,10')
  })

  it('draws one curve segment through two points', () => {
    const points: Point[] = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
    ]
    const { moveTo, curves } = parsePath(smoothPath(points))
    expect(moveTo).toEqual({ x: 0, y: 0 })
    expect(curves).toHaveLength(1)
    expect(curves[0].to).toEqual({ x: 10, y: 0 })
    // Catmull-Rom with a duplicated endpoint (no p_-1/p_n+1 neighbor) as the tangent source.
    expect(curves[0].cp1.x).toBeCloseTo(1.6667, 3)
    expect(curves[0].cp1.y).toBeCloseTo(0, 3)
  })

  it('passes through every input point as an on-curve endpoint, one curve per segment', () => {
    const points: Point[] = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 20, y: 10 },
    ]
    const { moveTo, curves } = parsePath(smoothPath(points))
    expect(moveTo).toEqual(points[0])
    expect(curves).toHaveLength(2)
    expect(curves[0].to).toEqual(points[1])
    expect(curves[1].to).toEqual(points[2])
    // Hand-computed from the Catmull-Rom formula for the second segment's leading control
    // point: p1 + (p2 - p0) / 6, with p0 = points[0], p1 = points[1], p2 = points[2].
    expect(curves[1].cp1.x).toBeCloseTo(10 + (20 - 0) / 6, 4)
    expect(curves[1].cp1.y).toBeCloseTo(0 + (10 - 0) / 6, 4)
  })
})

describe('monotonePath', () => {
  const lerpX = (n: number) => Array.from({ length: n }, (_, i) => i * 10)
  const mk = (ys: number[]): Point[] => ys.map((y, i) => ({ x: lerpX(ys.length)[i], y }))
  // A cubic Bezier lies inside the hull of its 4 control points, so if both inner control points
  // stay within the segment's end-point range the curve cannot leave it.
  const stays = (ys: number[]) => {
    const { curves, moveTo } = parsePath(monotonePath(mk(ys)))
    let prev = moveTo!
    return curves.every((c) => {
      const lo = Math.min(prev.y, c.to.y) - 1e-9
      const hi = Math.max(prev.y, c.to.y) + 1e-9
      const ok = [c.cp1.y, c.cp2.y].every((y) => y >= lo && y <= hi)
      prev = c.to
      return ok
    })
  }

  it('passes through every point, in order', () => {
    const { moveTo, curves } = parsePath(monotonePath(mk([5, 20, 8, 8, 30])))
    expect(moveTo).toEqual({ x: 0, y: 5 })
    expect(curves.map((c) => c.to)).toEqual(mk([5, 20, 8, 8, 30]).slice(1))
  })

  it('never overshoots a segment: a zigzag, a plateau into a jump, a spike', () => {
    expect(stays([0, 30, 0, 30, 0])).toBe(true)
    expect(stays([0, 0, 30, 30])).toBe(true)
    expect(stays([10, 10, 10, 50, 10, 10])).toBe(true)
    expect(stays([3, 4, 40, 41, 2, 90, 0])).toBe(true)
  })

  it('is exactly the case Catmull-Rom (smoothPath) gets wrong: it bulges above the floor', () => {
    const pts = mk([0, 0, 30, 30]) // floor is y = 0 (the round's best start)
    const catmull = parsePath(smoothPath(pts)).curves
    expect(Math.min(...catmull.flatMap((c) => [c.cp1.y, c.cp2.y]))).toBeLessThan(0)
    const mono = parsePath(monotonePath(pts)).curves
    expect(Math.min(...mono.flatMap((c) => [c.cp1.y, c.cp2.y]))).toBeGreaterThanOrEqual(0)
  })

  it('a flat run stays flat', () => {
    const { curves } = parsePath(monotonePath(mk([7, 7, 7])))
    expect(curves.flatMap((c) => [c.cp1.y, c.cp2.y])).toEqual([7, 7, 7, 7])
  })

  it('degenerate inputs: one point is a bare move, none is empty, two is a straight run', () => {
    expect(monotonePath([])).toBe('')
    expect(monotonePath([{ x: 1, y: 2 }])).toBe('M1,2')
    const { curves } = parsePath(monotonePath(mk([0, 10])))
    expect(curves[0].cp1.y).toBeCloseTo(10 / 3)
    expect(curves[0].cp2.y).toBeCloseTo((2 * 10) / 3)
  })
})
