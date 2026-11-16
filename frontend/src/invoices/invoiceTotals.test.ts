import { describe, expect, it } from 'vitest'
import type { InvoiceDocument } from '../types'
import { totalRows, totalsNote } from './invoiceTotals'

// Intl separates thousands with a narrow no-break space in some places; compare without caring which.
const plain = (text: string | null) => text?.replace(/\s/g, ' ') ?? null

const invoice = (over: Partial<InvoiceDocument> = {}) =>
  ({
    currency: 'RON', total_without_vat: '334.05', total_vat: '34.86', total_with_vat: '368.91',
    total_payable: '368.91', total_prepaid: null, total_rounding: null, ...over,
  }) as InvoiceDocument
const shown = (document: InvoiceDocument) => totalRows(document).map((row) => `${row.label}: ${plain(row.amount)}`)

describe('the totals under an invoice', () => {
  it('are the three usual rows when nothing was paid before and nothing is owed from before', () => {
    const usual = ['Fără TVA: 334,05 lei', 'TVA: 34,86 lei', 'Total: 368,91 lei']

    expect(shown(invoice())).toEqual(usual)
    expect(shown(invoice({ total_prepaid: '0.00', total_rounding: '0' }))).toEqual(usual)
    expect(totalRows(invoice()).map((row) => row.weight)).toEqual(['plain', 'plain', 'large'])
  })

  it('show an earlier unpaid balance apart from what the invoice is worth', () => {
    // The supplier writes it as a negative paid amount.
    const withDebt = invoice({ total_prepaid: '-3123.88', total_payable: '3492.79' })

    expect(shown(withDebt)).toEqual([
      'Fără TVA: 334,05 lei', 'TVA: 34,86 lei', 'Total factură: 368,91 lei',
      'Datorie restantă (sold anterior): 3.123,88 lei', 'De plată: 3.492,79 lei',
    ])
    expect(totalRows(withDebt).map((row) => row.weight)).toEqual(['plain', 'plain', 'bold', 'plain', 'large'])
  })

  it('take an advance already paid off what is left to pay', () => {
    const paidInPart = invoice({ total_without_vat: '1000.00', total_vat: '190.00', total_with_vat: '1190.00', total_prepaid: '200.00', total_payable: '990.00' })

    expect(shown(paidInPart)).toEqual([
      'Fără TVA: 1.000,00 lei', 'TVA: 190,00 lei', 'Total factură: 1.190,00 lei',
      'Plătit în avans: −200,00 lei', 'De plată: 990,00 lei',
    ])
    expect(shown(invoice({ total_prepaid: '368.91', total_payable: '0.00' })).slice(-2)).toEqual([
      'Plătit în avans: −368,91 lei', 'De plată: 0,00 lei',
    ])
  })

  it('show a rounding of what is left to pay, with its sign', () => {
    expect(shown(invoice({ total_rounding: '-0.01', total_payable: '368.90' })).slice(-3)).toEqual([
      'Total factură: 368,91 lei', 'Rotunjire: −0,01 lei', 'De plată: 368,90 lei',
    ])
    expect(shown(invoice({ total_rounding: '0.09', total_payable: '369.00' })).slice(-2)).toEqual([
      'Rotunjire: 0,09 lei', 'De plată: 369,00 lei',
    ])
  })

  it('keep the invoice\'s own currency', () => {
    expect(shown(invoice({ currency: 'EUR', total_prepaid: '-10.00', total_payable: '378.91' }))[3])
      .toBe('Datorie restantă (sold anterior): 10,00 EUR')
  })
})

describe('the note under the totals', () => {
  it('is missing on a usual invoice, and when only a rounding was made', () => {
    expect(totalsNote(invoice(), true)).toBeNull()
    expect(totalsNote(invoice({ total_prepaid: '0.00' }), true)).toBeNull()
    expect(totalsNote(invoice({ total_rounding: '-0.01' }), true)).toBeNull()
  })

  it('says that the earlier balance is not part of the invoice, and what SAGA gets', () => {
    expect(plain(totalsNote(invoice({ total_prepaid: '-3123.88', total_payable: '3492.79' }), true))).toBe(
      'Suma de plată cuprinde și o datorie mai veche, care nu face parte din această factură. În fișierul pentru SAGA intră doar valoarea facturii: 368,91 lei.',
    )
  })

  it('says that an advance was taken off, and that SAGA gets the whole invoice', () => {
    expect(plain(totalsNote(invoice({ total_prepaid: '200.00', total_payable: '168.91' }), true))).toBe(
      'Din suma de plată s-a scăzut ce s-a plătit în avans. În fișierul pentru SAGA intră valoarea întreagă a facturii: 368,91 lei.',
    )
  })

  it('leaves SAGA out for an invoice that is not written for it', () => {
    expect(totalsNote(invoice({ total_prepaid: '-3123.88' }), false))
      .toBe('Suma de plată cuprinde și o datorie mai veche, care nu face parte din această factură.')
    expect(totalsNote(invoice({ total_prepaid: '200.00' }), false))
      .toBe('Din suma de plată s-a scăzut ce s-a plătit în avans.')
  })
})
