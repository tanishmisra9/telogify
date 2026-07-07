import { describe, it, expect } from 'vitest'
import { rankDesc, rankAsc, heatBg } from './heat'

describe('rankDesc', () => {
  it('ranks the highest value as 1', () => {
    expect(rankDesc([10, 30, 20])).toEqual([3, 1, 2])
  })
  it('sinks nulls to the worst rank', () => {
    expect(rankDesc([10, null, 20])).toEqual([2, 3, 1])
  })
  it('assigns tied values the same rank band', () => {
    expect(rankDesc([20, 20, 10])).toEqual([1, 2, 3])
  })
})

describe('rankAsc', () => {
  it('ranks the lowest value as 1', () => {
    expect(rankAsc([10, 30, 20])).toEqual([1, 3, 2])
  })
})

describe('heatBg', () => {
  it('is transparent with one or zero items', () => {
    expect(heatBg(1, 1)).toBe('transparent')
  })
  it('gives the top rank the strongest mix and the last rank none', () => {
    expect(heatBg(1, 4)).toBe('color-mix(in oklch, var(--color-accent) 50%, transparent)')
    expect(heatBg(4, 4)).toBe('color-mix(in oklch, var(--color-accent) 0%, transparent)')
  })
})
