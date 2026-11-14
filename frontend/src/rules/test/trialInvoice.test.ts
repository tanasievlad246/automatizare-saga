import { describe, expect, it } from 'vitest'
import { EMPTY, EXAMPLES, fromDocument, toRequest } from './trialInvoice'

const line = (description: string, quantity: string, unitPrice: string) =>
  ({ description, quantity, unitPrice, sellerCode: '', barcode: '', commodityCodes: '', unit: null, vatPercent: null })

describe('a trial invoice', () => {
  it('is sent with numbers the program can read', () => {
    const sent = toRequest({ ...EMPTY, clientCui: '12345674', supplierName: ' Dedeman SRL ', supplierCui: '2816464', lines: [line('Ciment', ' 20 ', '28,50')] }, 'rules_then_jev')
    expect(sent).toEqual({
      client_cui: '12345674', supplier_name: 'Dedeman SRL', supplier_cui: '2816464', currency: 'RON', credit_note: false, ask: 'rules_then_jev',
      lines: [{ description: 'Ciment', quantity: '20', unit_price: '28.50', seller_code: null, barcode: null, commodity_codes: [], unit: null, vat_percent: null }],
    })
  })

  it('leaves out the rows nothing was written on, and splits the codes', () => {
    const sent = toRequest({ ...EMPTY, lines: [line('', '', ''), { ...line('Adeziv', '6', '41'), commodityCodes: '32141010, 3214' }] }, 'jev_only')
    expect(sent.lines).toHaveLength(1)
    expect(sent.lines[0].commodity_codes).toEqual(['32141010', '3214'])
    expect(sent.client_cui).toBeNull()
  })

  it('starts from a saved invoice', () => {
    // The page's copy of an invoice has no codes on its lines, so those stay blank. The unit,
    // the VAT rate and the currency are carried, so Jev is asked what it was asked for that invoice.
    const trial = fromDocument({
      invoice: { cui: '12345674' },
      document: {
        number: 'FV-1042', currency: 'EUR', is_credit_note: false, supplier: { name: 'Dedeman SRL', cui: 'RO2816464' },
        lines: [{ number: 1, description: 'Ciment', unit_name: 'KGM', quantity: '20', unit_price: '28.5', vat_percent: '9' }],
      },
    } as never)
    expect(trial).toEqual({
      clientCui: '12345674', supplierName: 'Dedeman SRL', supplierCui: 'RO2816464', currency: 'EUR', creditNote: false, startedFrom: 'FV-1042',
      lines: [{ description: 'Ciment', quantity: '20', unitPrice: '28,5', sellerCode: '', barcode: '', commodityCodes: '', unit: 'KGM', vatPercent: '9' }],
    })
  })

  it('has two examples, each with something on it', () => {
    expect(EXAMPLES.materiale.lines.length).toBeGreaterThan(0)
    expect(EXAMPLES.combustibil.lines[0].description).toMatch(/motorin/i)
  })
})
