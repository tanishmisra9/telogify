// "Random until exhausted": every id is shown once, in random order, before any repeats; across a refill the id just
// shown is not repeated back to back. Ported from the portfolio's radio sample picker. Pure (the caller owns the
// bag and the random source) so it is testable; `loadBag`/`saveBag` persist it per visitor.
export interface Bag {
  remaining: string[]
  last: string | null
}

export const emptyBag: Bag = { remaining: [], last: null }

export function nextFromBag(ids: string[], bag: Bag, rand: () => number = Math.random): { id: string; bag: Bag } | null {
  if (ids.length === 0) return null
  // Ids that left the pool (an insight regenerated, an example dropped) must not be served from a stale bag.
  let remaining = bag.remaining.filter((id) => ids.includes(id))
  if (remaining.length === 0) remaining = [...ids] // exhausted: refill
  let candidates = remaining
  if (bag.last != null && candidates.length > 1) {
    const others = candidates.filter((id) => id !== bag.last)
    if (others.length > 0) candidates = others
  }
  const id = candidates[Math.min(candidates.length - 1, Math.floor(rand() * candidates.length))]
  return { id, bag: { remaining: remaining.filter((r) => r !== id), last: id } }
}

const KEY = 'telogify.how-it-works.bag'

// localStorage can be missing, blocked or throw (private windows): the page must render without it.
export function loadBag(): Bag {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? 'null')
    if (raw && Array.isArray(raw.remaining) && raw.remaining.every((r: unknown) => typeof r === 'string')) {
      return { remaining: raw.remaining, last: typeof raw.last === 'string' ? raw.last : null }
    }
  } catch {
    /* fall through to an empty bag */
  }
  return emptyBag
}

export function saveBag(bag: Bag): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(bag))
  } catch {
    /* not persisted: the in-memory bag still works for this visit */
  }
}
