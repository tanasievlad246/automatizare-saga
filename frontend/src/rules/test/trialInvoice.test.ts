import { describe, expect, it } from 'vitest'
import { ApiError } from '../../api'
import { errorMessage } from '../../errorMessages'
import { EMPTY, EXAMPLES, REFUSED_HERE, changeLine, fromDocument, hasCodes, toRequest } from './trialInvoice'

const line = (description: string, quantity: string, unitPrice: string) =>
  ({ description, quantity, unitPrice, sellerCode: '', barcode: '', commodityCodes: '', unit: null, vatPercent: null, value: null })

const savedView = (lines: object[]) => ({
  invoice: { cui: '12345674' },
  document: {
    number: 'FV-1042', currency: 'EUR', is_credit_note: false, supplier: { name: 'Dedeman SRL', cui: 'RO2816464' }, lines,
  },
}) as never

describe('a trial invoice', () => {
  it('is sent with numbers the program can read', () => {
    const sent = toRequest({ ...EMPTY, clientCui: '12345674', supplierName: ' Dedeman SRL ', supplierCui: '2816464', lines: [line('Ciment', ' 20 ', '28,50')] }, 'rules_then_jev')
    expect(sent).toEqual({
      client_cui: '12345674', supplier_name: 'Dedeman SRL', supplier_cui: '2816464', currency: 'RON', credit_note: false, ask: 'rules_then_jev',
      lines: [{ description: 'Ciment', quantity: '20', unit_price: '28.50', seller_code: null, barcode: null, commodity_codes: [], unit: null, vat_percent: null, value: null }],
    })
  })

  it.each([
    ['12 000', '12000'],
    ['12 000', '12000'],
    ['1.234,50', '1234.50'],
    ['28,50', '28.50'],
    ['28.50', '28.50'],
    ['', ''], // the program reads a blank quantity as 1 and a blank price as 0
    ['1,234,50', '1.234.50'], // still not a number: the program refuses it
  ])('sends %j, written as Romanians write numbers, as %j', (typed, sent) => {
    const [row] = toRequest({ ...EMPTY, lines: [line('Ciment', typed, typed)] }, 'rules_then_jev').lines
    expect([row.quantity, row.unit_price]).toEqual([sent, sent])
  })

  it('says, when a number is refused, how numbers are written', () => {
    const refused = new ApiError('invalid_input', 'The quantity of line 1 must be a number.')
    expect(errorMessage(refused, REFUSED_HERE)).toBe('Cantitatea și prețul se scriu ca numere, de exemplu 20 și 28,50.')
  })

  it('leaves out the rows nothing was written on, and splits the codes', () => {
    const sent = toRequest({ ...EMPTY, lines: [line('', '', ''), { ...line('Adeziv', '6', '41'), commodityCodes: '32141010, 3214' }] }, 'jev_only')
    expect(sent.lines).toHaveLength(1)
    expect(sent.lines[0].commodity_codes).toEqual(['32141010', '3214'])
    expect(sent.client_cui).toBeNull()
  })

  it('starts from a saved invoice with its codes shown and its unit, VAT rate, currency and line value kept', () => {
    const trial = fromDocument(savedView([{
      number: 1, description: 'Ciment', seller_code: 'ART-77', barcode: '5941234567890', commodity_codes: ['44111200', '4411'],
      unit: 'KGM', unit_name: 'KG', quantity: '20.000', unit_price: '28.5', value: '541.50', vat_percent: '9',
    }]))
    expect(trial).toEqual({
      clientCui: '12345674', supplierName: 'Dedeman SRL', supplierCui: 'RO2816464', currency: 'EUR', creditNote: false, startedFrom: 'FV-1042',
      lines: [{
        description: 'Ciment', quantity: '20,000', unitPrice: '28,5', sellerCode: 'ART-77', barcode: '5941234567890', commodityCodes: '44111200, 4411',
        // The unit code, as Jev was asked with it, not the name SAGA shows.
        unit: 'KGM', vatPercent: '9', value: '541.50',
      }],
    })
    // Sent unchanged, it is the question the real invoice put.
    expect(toRequest(trial, 'rules_then_jev').lines[0]).toEqual({
      description: 'Ciment', quantity: '20.000', unit_price: '28.5', seller_code: 'ART-77', barcode: '5941234567890',
      commodity_codes: ['44111200', '4411'], unit: 'KGM', vat_percent: '9', value: '541.50',
    })
  })

  it('starts from a saved invoice that could not be read with one blank row', () => {
    expect(fromDocument({ invoice: { cui: '12345674' }, document: null } as never).lines).toEqual(EMPTY.lines)
  })

  it('drops the value carried by a row once its quantity or price is changed', () => {
    const carried = { ...line('Ciment', '20,000', '28,5'), value: '541.50' }
    expect(changeLine(carried, { unitPrice: '30' })).toMatchObject({ unitPrice: '30', value: null })
    expect(changeLine(carried, { quantity: '10' })).toMatchObject({ quantity: '10', value: null })
    // The description and the codes are not in the value: it stays.
    expect(changeLine(carried, { description: 'Ciment gri', sellerCode: 'X1' })).toMatchObject({ description: 'Ciment gri', value: '541.50' })
  })

  it('knows whether any row has a code, so the codes are shown', () => {
    expect(hasCodes(EXAMPLES.materiale)).toBe(false)
    expect(hasCodes({ ...EMPTY, lines: [line('a', '1', '1'), { ...line('b', '1', '1'), barcode: '594' }] })).toBe(true)
    expect(hasCodes({ ...EMPTY, lines: [{ ...line('a', '1', '1'), commodityCodes: ' ' }] })).toBe(false)
  })

  it('has two examples, each with something on it', () => {
    expect(EXAMPLES.materiale.lines.length).toBeGreaterThan(0)
    expect(EXAMPLES.combustibil.lines[0].description).toMatch(/motorin/i)
  })
})
