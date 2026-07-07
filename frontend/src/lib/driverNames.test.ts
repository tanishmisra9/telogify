import { describe, expect, it } from 'vitest'
import { driverName } from '@/lib/drivers'

describe('driverName', () => {
  it('maps known codes to full names', () => {
    expect(driverName('VER')).toBe('Max Verstappen')
    expect(driverName('LIN')).toBe('Arvid Lindblad')
  })

  it('falls back to the code for unknown drivers', () => {
    expect(driverName('ZZZ')).toBe('ZZZ')
  })
})
