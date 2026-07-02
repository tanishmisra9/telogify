import { describe, it, expect } from 'vitest'
import { isValidElement, type ReactElement } from 'react'
import { emphasize } from './emphasize'

// The accented segments are the odd-index spans carrying `text-accent`; pull their text.
function accents(text: string): string[] {
  return emphasize(text)
    .filter(
      (n): n is ReactElement<{ className?: string; children: string }> =>
        isValidElement(n) && String((n.props as { className?: string }).className).includes('text-accent'),
    )
    .map((n) => n.props.children)
}

describe('emphasize', () => {
  it('keeps a number and its spelled/symbol unit as one accent unit', () => {
    expect(accents('gained 3.994 seconds')).toEqual(['3.994 seconds'])
    expect(accents('hit 329 km/h at the line')).toEqual(['329 km/h'])
    expect(accents('used 95% of the lap')).toEqual(['95%'])
  })
  it('keeps ordinals whole', () => {
    expect(accents('finished 11th, up from 22nd')).toEqual(['11th', '22nd'])
  })
  it('emphasizes nothing when there are no figures', () => {
    expect(accents('a clean lap')).toEqual([])
  })
})
