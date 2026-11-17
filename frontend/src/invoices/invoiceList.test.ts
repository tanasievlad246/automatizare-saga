import { describe, expect, it } from 'vitest'
import type { Invoice, LineAccount } from '../types'
import {
  DEFAULT_LIST, NO_ACCOUNT, type Order, accountOptions, clearFilters, filterInvoices, filtersOn, foundLine, orderOptions,
  readListState, sortInvoices, writeListState,
} from './invoiceList'

const invoice = (fields: Partial<Invoice>) =>
  ({
    id: '1', invoice_number: null, invoice_issue_date: null, supplier_name: null, supplier_cui: null,
    customer_name: null, customer_cui: null, total_with_vat: null, cont: null, line_accounts: null, ...fields,
  }) as Invoice
const line = (fields: Partial<LineAccount>) => ({ line: 1, cont: null, method: null, ...fields }) as LineAccount

const FUEL = invoice({
  id: '101', supplier_name: 'Stația Carburant SRL', supplier_cui: 'RO 1234567', invoice_number: 'FV-1042',
  invoice_issue_date: '2026-11-09', total_with_vat: '595.00', cont: '6022',
})
const PHONE = invoice({
  id: '102', supplier_name: 'Telefonie Mobilă SA', supplier_cui: '7654321', invoice_number: 'TM 88213',
  invoice_issue_date: '2026-10-08', total_with_vat: '238.00', cont: '626',
})
const BUILD = invoice({
  id: '103', supplier_name: 'Materiale Construcții S.R.L.', supplier_cui: '5551234', invoice_number: 'MC 5521',
  invoice_issue_date: '2026-10-31', total_with_vat: '1071.00',
  line_accounts: [line({ line: 1, cont: '6022' }), line({ line: 2, cont: null }), line({ line: 3, cont: null, method: 'follows' })],
})
const WATER = invoice({
  id: '104', supplier_name: 'Compania de Apă', supplier_cui: '9990001', invoice_number: 'CO 1879',
  invoice_issue_date: '2026-10-01', total_with_vat: '368.91', cont: '605',
  line_accounts: [line({ line: 1, cont: '605' }), line({ line: 2, cont: '6022' })],
})
const SOLD = invoice({
  id: '105', customer_name: 'Beta Distribuție SRL', customer_cui: '4445556', invoice_number: 'AC 2207',
  invoice_issue_date: '2026-11-12', total_with_vat: '4165.00',
})
const ALL = [FUEL, PHONE, BUILD, WATER]

const state = (fields: Partial<typeof DEFAULT_LIST>) => ({ ...DEFAULT_LIST, ...fields })
const ids = (invoices: Invoice[]) => invoices.map((each) => each.id)
const found = (fields: Partial<typeof DEFAULT_LIST>) => ids(filterInvoices(ALL, state(fields), 'supplier'))

describe('searching a client\'s invoices', () => {
  it('finds every invoice while nothing is set', () => {
    expect(found({})).toEqual(['101', '102', '103', '104'])
  })

  it('finds by the supplier\'s name, whatever the case, diacritics and dots', () => {
    expect(found({ text: 'carburant' })).toEqual(['101'])
    expect(found({ text: 'statia' })).toEqual(['101'])
    expect(found({ text: 'srl' })).toEqual(['101', '103'])
    expect(found({ text: 'telefonie mobila' })).toEqual(['102'])
  })

  it('finds by the supplier\'s CUI, with or without RO', () => {
    expect(found({ text: '1234567' })).toEqual(['101'])
    expect(found({ text: 'RO1234567' })).toEqual(['101'])
    expect(found({ text: 'ro 765' })).toEqual(['102'])
  })

  it('finds by the invoice\'s number, written with or without its signs', () => {
    expect(found({ text: 'FV-1042' })).toEqual(['101'])
    expect(found({ text: 'fv1042' })).toEqual(['101'])
    expect(found({ text: '88213' })).toEqual(['102'])
  })

  it('needs every word typed', () => {
    expect(found({ text: 'carburant 1042' })).toEqual(['101'])
    expect(found({ text: 'carburant 88213' })).toEqual([])
  })

  it('finds an issued invoice by its buyer, not by a supplier', () => {
    expect(ids(filterInvoices([SOLD], state({ text: 'beta' }), 'customer'))).toEqual(['105'])
    expect(ids(filterInvoices([SOLD], state({ text: '4445556' }), 'customer'))).toEqual(['105'])
    expect(ids(filterInvoices([SOLD], state({ text: 'beta' }), 'supplier'))).toEqual([])
  })
})

describe('the period of a client\'s invoices', () => {
  it('keeps the invoices dated from the first day to the last, both days included', () => {
    expect(found({ from: '2026-10-01', until: '2026-10-31' })).toEqual(['102', '103', '104'])
  })

  it('works with one of the two days alone', () => {
    expect(found({ from: '2026-10-31' })).toEqual(['101', '103'])
    expect(found({ until: '2026-10-08' })).toEqual(['102', '104'])
  })

  it('reads the day of a date written with its time zone, as some suppliers write it', () => {
    const zoned = invoice({ id: '8', invoice_issue_date: '2026-10-31+02:00' })
    expect(ids(filterInvoices([zoned], state({ until: '2026-10-31' }), 'supplier'))).toEqual(['8'])
    expect(ids(filterInvoices([zoned], state({ from: '2026-10-31' }), 'supplier'))).toEqual(['8'])
    expect(ids(filterInvoices([zoned], state({ from: '2026-11-01' }), 'supplier'))).toEqual([])
  })

  it('leaves out an invoice without a date once a day is set', () => {
    const undated = invoice({ id: '9' })
    expect(ids(filterInvoices([undated], state({ from: '2026-01-01' }), 'supplier'))).toEqual([])
    expect(ids(filterInvoices([undated], state({}), 'supplier'))).toEqual(['9'])
  })
})

describe('the account of a client\'s invoices', () => {
  it('keeps the invoices with a line on that account', () => {
    expect(found({ cont: '6022' })).toEqual(['101', '103', '104'])
    expect(found({ cont: '605' })).toEqual(['104'])
  })

  it('keeps under "no account yet" an invoice without one, or with a line still without one', () => {
    const waiting = invoice({ id: '7' })
    expect(ids(filterInvoices([...ALL, waiting], state({ cont: NO_ACCOUNT }), 'supplier'))).toEqual(['103', '7'])
  })

  it('offers the accounts this client\'s invoices are on, in the order of the chart of accounts, with their names', () => {
    expect(accountOptions(ALL, { '6022': 'Combustibili', '605': 'Apă' }, '')).toEqual([
      { value: '', label: 'Toate conturile' },
      { value: NO_ACCOUNT, label: 'Fără cont încă' },
      { value: '6022', label: '6022 · Combustibili' },
      { value: '605', label: '605 · Apă' },
      { value: '626', label: '626' },
    ])
  })

  it('names an account by the start of its description, which is written for Jev and can be long', () => {
    const labels = (description: string) => accountOptions([PHONE], { '626': description }, '')[2].label
    expect(labels('Materiale consumabile: papetărie, ambalaje.')).toBe('626 · Materiale consumabile')
    expect(labels('Telefonie, internet, servicii poștale și de curierat.')).toBe('626 · Telefonie, internet, servicii poștale…')
    expect(labels('Alte servicii prestate de terți care nu au un cont propriu.')).toBe('626 · Alte servicii prestate de terți care…')
    expect(labels('Telefonie')).toBe('626 · Telefonie')
  })

  it('keeps offering the account chosen when no invoice is on it any more', () => {
    expect(accountOptions([PHONE], {}, '628').map((option) => option.value)).toEqual(['', NO_ACCOUNT, '626', '628'])
  })
})

describe('the order of a client\'s invoices', () => {
  const ordered = (order: Order) => ids(sortInvoices(ALL, order, 'supplier'))

  it('starts with the newest by the date on the invoice', () => {
    expect(ordered('noi')).toEqual(['101', '103', '102', '104'])
    expect(ordered('vechi')).toEqual(['104', '102', '103', '101'])
  })

  it('puts an invoice without a date last either way, and two of one day by ANAF\'s number', () => {
    const listed = [invoice({ id: '3400' }), invoice({ id: '9001', invoice_issue_date: '2026-11-12' }), invoice({ id: '10002', invoice_issue_date: '2026-11-12' })]
    expect(ids(sortInvoices(listed, 'noi', 'supplier'))).toEqual(['10002', '9001', '3400'])
    expect(ids(sortInvoices(listed, 'vechi', 'supplier'))).toEqual(['9001', '10002', '3400'])
  })

  it('goes by the supplier\'s name from A to Z, diacritics where they belong', () => {
    expect(ordered('nume')).toEqual(['104', '103', '101', '102'])
    const pair = [invoice({ id: '1', supplier_name: 'Bun Gust SRL' }), invoice({ id: '2', supplier_name: 'Ăla Bun SRL' })]
    expect(ids(sortInvoices(pair, 'nume', 'supplier'))).toEqual(['2', '1'])
    const tees = [invoice({ id: '1', supplier_name: 'Tz Trans' }), invoice({ id: '2', supplier_name: 'Ţesătoria' }), invoice({ id: '3', supplier_name: 'Zeta' })]
    expect(ids(sortInvoices(tees, 'nume', 'supplier'))).toEqual(['1', '2', '3'])
  })

  it('puts an invoice without a name last', () => {
    const listed = [invoice({ id: '1' }), invoice({ id: '2', supplier_name: 'Zeta' })]
    expect(ids(sortInvoices(listed, 'nume', 'supplier'))).toEqual(['2', '1'])
  })

  it('goes by the total, largest or smallest first', () => {
    expect(ordered('total-mare')).toEqual(['103', '101', '104', '102'])
    expect(ordered('total-mic')).toEqual(['102', '104', '101', '103'])
  })

  it('counts a credit note\'s negative total as the smallest, and puts an invoice without a total last either way', () => {
    const listed = [invoice({ id: '1', total_with_vat: '100.00' }), invoice({ id: '2' }), invoice({ id: '3', total_with_vat: '-250.00' })]
    expect(ids(sortInvoices(listed, 'total-mare', 'supplier'))).toEqual(['1', '3', '2'])
    expect(ids(sortInvoices(listed, 'total-mic', 'supplier'))).toEqual(['3', '1', '2'])
  })

  it('leaves the list given as it was', () => {
    sortInvoices(ALL, 'nume', 'supplier')
    expect(ids(ALL)).toEqual(['101', '102', '103', '104'])
  })

  it('names the party the list is about', () => {
    expect(orderOptions('supplier').map((option) => option.label)).toEqual([
      'Cele mai noi întâi', 'Cele mai vechi întâi', 'Furnizorul, de la A la Z', 'Totalul, cel mai mare întâi', 'Totalul, cel mai mic întâi',
    ])
    expect(orderOptions('customer')[2].label).toBe('Cumpărătorul, de la A la Z')
  })
})

describe('what the address keeps of a list', () => {
  it('reads nothing as the whole list, newest first, on its first page', () => {
    expect(readListState(new URLSearchParams())).toEqual(DEFAULT_LIST)
  })

  it('reads what was chosen, each list under its own names', () => {
    const search = new URLSearchParams('pagina=3&cauta=apa&de-la=2026-10-01&pana-la=2026-10-31&cont=605&ordine=total-mare&emise-pagina=2')
    expect(readListState(search)).toEqual({ page: 3, text: 'apa', from: '2026-10-01', until: '2026-10-31', cont: '605', order: 'total-mare' })
    expect(readListState(search, 'emise-')).toEqual({ ...DEFAULT_LIST, page: 2 })
  })

  it('reads a day or an order it does not know as none', () => {
    expect(readListState(new URLSearchParams('de-la=31.10.2026&ordine=random'))).toEqual(DEFAULT_LIST)
  })

  it('reads a day that does not exist as none, since the calendar field could not show it', () => {
    expect(readListState(new URLSearchParams('de-la=2026-02-31&pana-la=2026-13-01')).from).toBe('')
    expect(readListState(new URLSearchParams('pana-la=2026-13-01')).until).toBe('')
    expect(readListState(new URLSearchParams('de-la=2028-02-29')).from).toBe('2028-02-29')
  })

  it('writes only what differs from the whole list, and keeps what else is there', () => {
    const written = writeListState(new URLSearchParams('arata=toate'), '', { text: 'apa', order: 'noi' })
    expect(written.toString()).toBe('arata=toate&cauta=apa')
  })

  it('goes back to the first page when anything but the page changes', () => {
    const search = new URLSearchParams('pagina=4&ordine=vechi')
    expect(writeListState(search, '', { cont: '605' }).toString()).toBe('ordine=vechi&cont=605')
    expect(writeListState(search, '', { page: 5 }).toString()).toBe('pagina=5&ordine=vechi')
    expect(writeListState(search, '', { page: 1 }).toString()).toBe('ordine=vechi')
  })

  it('writes the issued list under its own names', () => {
    const written = writeListState(new URLSearchParams('pagina=2'), 'emise-', { text: 'beta' })
    expect(written.toString()).toBe('pagina=2&emise-cauta=beta')
  })

  it('clears the search, the period and the account, but keeps the order', () => {
    const search = new URLSearchParams('arata=toate&pagina=2&cauta=apa&de-la=2026-10-01&pana-la=2026-10-31&cont=605&ordine=vechi')
    expect(clearFilters(search, '').toString()).toBe('arata=toate&ordine=vechi')
  })

  it('clears only the issued list\'s choices when asked for the issued list', () => {
    const search = new URLSearchParams('cauta=apa&pagina=2&emise-cauta=beta&emise-pagina=3&emise-ordine=vechi')
    expect(clearFilters(search, 'emise-').toString()).toBe('cauta=apa&pagina=2&emise-ordine=vechi')
  })
})

describe('whether a list is narrowed', () => {
  it('is so with a search, a day or an account, but not with another order', () => {
    expect(filtersOn(DEFAULT_LIST)).toBe(false)
    expect(filtersOn(state({ order: 'vechi', page: 3 }))).toBe(false)
    expect(filtersOn(state({ text: '  ' }))).toBe(false)
    expect(filtersOn(state({ text: ' - . ' }))).toBe(false) // signs alone find everything, so they narrow nothing
    expect(filtersOn(state({ text: 'apa' }))).toBe(true)
    expect(filtersOn(state({ until: '2026-10-31' }))).toBe(true)
    expect(filtersOn(state({ cont: NO_ACCOUNT }))).toBe(true)
  })

  it('says how many invoices are seen of all', () => {
    expect(foundLine(6, 312)).toBe('Se văd 6 facturi din 312.')
    expect(foundLine(1, 312)).toBe('Se vede o factură din 312.')
    expect(foundLine(20, 312)).toBe('Se văd 20 de facturi din 312.')
  })
})
