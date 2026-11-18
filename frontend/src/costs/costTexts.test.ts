import { describe, expect, it } from 'vitest'
import { perThousandLine } from './costTexts'

const plain = (text: string | null) => text?.replace(/\s/g, ' ') ?? null

describe('the average cost of an invoice', () => {
  it('under one cent, says what a thousand invoices cost, which can be read', () => {
    expect(plain(perThousandLine(0.000028))).toBe('La 1.000 de facturi: 0,03 $')
    expect(plain(perThousandLine(0.0000021))).toBe('La 1.000 de facturi: < 0,01 $')
  })

  it('from one cent up, or with nothing classified yet, needs no second line', () => {
    expect(perThousandLine(0.02)).toBeNull()
    expect(perThousandLine(null)).toBeNull()
    expect(perThousandLine(0)).toBeNull()
  })
})
