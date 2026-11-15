import { describe, expect, it } from 'vitest'
import { knowsCode } from './errorMessages'

describe('knowsCode', () => {
  it('knows a code that has a sentence of its own', () => {
    expect(knowsCode('invalid_input')).toBe(true)
  })

  it('does not take a name inherited from Object for a code', () => {
    expect(knowsCode('constructor')).toBe(false)
    expect(knowsCode('toString')).toBe(false)
  })
})
