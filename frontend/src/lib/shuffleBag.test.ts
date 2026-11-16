import { describe, expect, it } from 'vitest'
import { emptyBag, nextFromBag, type Bag } from './shuffleBag'

const ids = ['a', 'b', 'c', 'd', 'e']
// Deterministic pseudo-random so the tests are repeatable.
const seeded = (seed: number) => () => {
  seed = (seed * 1664525 + 1013904223) % 4294967296
  return seed / 4294967296
}

function draw(n: number, pool = ids, start: Bag = emptyBag, rand = seeded(7)) {
  const out: string[] = []
  let bag = start
  for (let i = 0; i < n; i++) {
    const r = nextFromBag(pool, bag, rand)!
    out.push(r.id)
    bag = r.bag
  }
  return out
}

describe('nextFromBag', () => {
  it('shows every id once before any repeats', () => {
    for (const seed of [1, 2, 3, 4, 5, 6]) {
      const first = draw(5, ids, emptyBag, seeded(seed))
      expect([...first].sort()).toEqual(ids)
    }
  })

  it('never repeats the id just shown across a refill', () => {
    for (const seed of [1, 2, 3, 4, 5, 6, 7, 8]) {
      const seq = draw(40, ids, emptyBag, seeded(seed))
      seq.slice(1).forEach((id, i) => expect(id).not.toBe(seq[i]))
    }
  })

  it('refills after exhaustion and keeps going', () => {
    const seq = draw(12)
    expect(seq.slice(5, 10).sort()).toEqual(ids)
  })

  it('handles empty and single-item pools', () => {
    expect(nextFromBag([], emptyBag)).toBeNull()
    expect(draw(3, ['only'])).toEqual(['only', 'only', 'only']) // nothing else to show
  })

  it('drops ids that left the pool instead of serving them from a stale bag', () => {
    const stale: Bag = { remaining: ['gone', 'a'], last: 'gone' }
    expect(nextFromBag(['a', 'b'], stale, () => 0)!.id).toBe('a')
    expect(nextFromBag(['x', 'y'], stale, () => 0)!.bag.remaining).toEqual(['y'])
  })
})
