import { describe, expect, it } from 'vitest'
import { detailText } from './details'

describe('a detail of a journal line', () => {
  it('writes objects and lists as JSON, not as [object Object]', () => {
    expect(detailText({ days: 7 })).toBe('{"days":7}')
    expect(detailText(['08:00', '12:00'])).toBe('["08:00","12:00"]')
  })

  it('writes the rest as it is', () => {
    expect(detailText('Alfa')).toBe('Alfa')
    expect(detailText(3)).toBe('3')
    expect(detailText(true)).toBe('true')
    expect(detailText(null)).toBe('null')
  })
})
