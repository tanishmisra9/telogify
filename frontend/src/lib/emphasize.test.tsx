import { describe, it, expect } from 'vitest'
import { isValidElement, type ReactElement } from 'react'
import { emphasize, bindMetricSpaces } from './emphasize'

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
    expect(accents('530 metres before the braking zone')).toEqual(['530 metres'])
    expect(accents('240 meters of clipping')).toEqual(['240 meters'])
  })
  it('keeps ordinals whole', () => {
    expect(accents('finished 11th, up from 22nd')).toEqual(['11th', '22nd'])
  })
  it('keeps an acceleration and its m/s² unit whole (deployment verdicts)', () => {
    expect(accents('deployment (+4.6 m/s² through 250-290 km/h)')).toEqual(['4.6 m/s²', '250', '290 km/h'])
    expect(accents('run dry up top (-0.1 m/s² past 290 km/h)')).toEqual(['0.1 m/s²', '290 km/h'])
  })
  it('emphasizes nothing when there are no figures', () => {
    expect(accents('a clean lap')).toEqual([])
  })
  it('emphasizes bare numbers and decimals', () => {
    expect(accents('gained 0.22 seconds a lap')).toEqual(['0.22 seconds'])
    expect(accents('a gap of +2 positions')).toEqual(['2'])
  })
  it('does not swallow the first letter of the next word after a bare number', () => {
    expect(accents('on lap 7, served notice that it could win')).toEqual(['7,'])
  })
  it('does not read digits embedded in name tokens as data', () => {
    expect(accents('Haas F1 Team lost 0.3 seconds')).toEqual(['0.3 seconds'])
    expect(accents('the W17 chassis')).toEqual([])
  })
  it('still accents the second number of a hyphenated range', () => {
    expect(accents('through 250-290 km/h')).toEqual(['250', '290 km/h'])
  })
})

describe('bindMetricSpaces', () => {
  it('keeps a number glued to its unit', () => {
    expect(bindMetricSpaces('0.058 s per lap')).toBe('0.058\u00a0s per lap')
    expect(bindMetricSpaces('~1150 m before braking')).toBe('~1150\u00a0m before braking')
    expect(bindMetricSpaces('329 km/h on the straight')).toBe('329\u00a0km/h on the straight')
  })
})
