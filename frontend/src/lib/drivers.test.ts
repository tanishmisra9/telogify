import { describe, expect, it } from 'vitest'
import { driverName } from '@/lib/drivers'

describe('driverName', () => {
  it('maps known FIA codes to full names', () => {
    expect(driverName('VER')).toBe('Max Verstappen')
    expect(driverName('ANT')).toBe('Kimi Antonelli')
  })

  it('falls back to the code for unknown drivers', () => {
    expect(driverName('ZZZ')).toBe('ZZZ')
  })

  it('returns empty string for missing input', () => {
    expect(driverName(null)).toBe('')
    expect(driverName(undefined)).toBe('')
    expect(driverName('')).toBe('')
  })
})
