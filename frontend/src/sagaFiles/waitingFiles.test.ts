import { describe, expect, it } from 'vitest'
import type { Invoice } from '../types'
import {
  type Sort, fileSummary, fileTotals, invoicesOf, lineRows, nextSort, sortFileInvoices, sortedLine,
} from './waitingFiles'

/** An invoice as the lists give it, with only what these functions read. */
function invoice(id: string, fields: Partial<Invoice> = {}): Invoice {
  return {
    id, cui: '12345674', message_type: 'FACTURA PRIMITA', invoice_number: id, invoice_issue_date: '2026-11-10',
    supplier_name: 'Beton Plus SRL', customer_name: 'Alfa Construct SRL', currency: 'RON', total_with_vat: '100.00',
    cont: '628', line_accounts: null, ...fields,
  } as Invoice
}

const issued = (id: string, fields: Partial<Invoice> = {}) =>
  invoice(id, { message_type: 'FACTURA TRIMISA', supplier_name: 'Alfa Construct SRL', customer_name: 'Beta Instal SRL', ...fields })

describe('the invoices of a file', () => {
  it('are found in both lists, in the order the file has them', () => {
    const received = [invoice('3001'), invoice('3002')]
    const sent = [issued('4001')]

    expect(invoicesOf(['4001', '3002', '3001'], received, sent).map((each) => each.id)).toEqual(['4001', '3002', '3001'])
  })

  it('leave out one that is in neither list', () => {
    expect(invoicesOf(['3001', '9999'], [invoice('3001')], []).map((each) => each.id)).toEqual(['3001'])
    expect(invoicesOf(['3001'], undefined, undefined)).toEqual([])
  })
})

describe('the total of a file', () => {
  it('adds what the invoices are worth, to the cent', () => {
    const invoices = [invoice('1', { total_with_vat: '1071.00' }), invoice('2', { total_with_vat: '856.80' }), invoice('3', { total_with_vat: '0.10' }), invoice('4', { total_with_vat: '0.20' })]

    expect(fileTotals(invoices)).toEqual([{ currency: 'RON', amount: '1928.10' }])
  })

  it('keeps each currency apart, lei first', () => {
    const invoices = [
      invoice('1', { total_with_vat: '1200.00', currency: 'EUR' }), invoice('2', { total_with_vat: '2070.60' }),
      invoice('3', { total_with_vat: '50.00', currency: 'CHF' }), invoice('4', { total_with_vat: '10', currency: null }),
    ]

    expect(fileTotals(invoices)).toEqual([
      { currency: 'RON', amount: '2080.60' }, { currency: 'CHF', amount: '50.00' }, { currency: 'EUR', amount: '1200.00' },
    ])
  })

  it('takes a credit note off, and skips an invoice without a total', () => {
    const invoices = [invoice('1', { total_with_vat: '500.00' }), invoice('2', { total_with_vat: '-120.50' }), invoice('3', { total_with_vat: null })]

    expect(fileTotals(invoices)).toEqual([{ currency: 'RON', amount: '379.50' }])
    expect(fileTotals([])).toEqual([])
  })
})

describe('what a file holds, in words', () => {
  it('says how many invoices and their total', () => {
    const invoices = [invoice('1', { total_with_vat: '1071.00' }), invoice('2', { total_with_vat: '856.80' })]

    expect(fileSummary(invoices)).toEqual({ count: '2 facturi primite', total: '1.927,80 lei', kinds: null })
  })

  it('says one invoice by its kind', () => {
    expect(fileSummary([invoice('1', { total_with_vat: '1071.00' })]).count).toBe('O factură primită')
    expect(fileSummary([issued('1')]).count).toBe('O factură emisă')
    expect(fileSummary([issued('1'), issued('2'), issued('3')]).count).toBe('3 facturi emise')
  })

  it('splits the total by kind when the file holds both', () => {
    const invoices = [
      invoice('1', { total_with_vat: '1071.00' }), invoice('2', { total_with_vat: '856.80' }),
      issued('3', { total_with_vat: '2380.00' }),
    ]

    expect(fileSummary(invoices)).toEqual({
      count: '3 facturi', total: '4.307,80 lei', kinds: '2 primite: 1.927,80 lei · o emisă: 2.380,00 lei',
    })
  })

  it('writes each currency of the total', () => {
    const invoices = [invoice('1', { total_with_vat: '2070.60' }), invoice('2', { total_with_vat: '1200.00', currency: 'EUR' })]

    expect(fileSummary(invoices).total).toBe('2.070,60 lei + 1.200,00 EUR')
  })

  it('says the count of the file when its invoices are not in the lists yet', () => {
    expect(fileSummary([], 12)).toEqual({ count: '12 facturi', total: '', kinds: null })
    expect(fileSummary([], 1).count).toBe('O factură')
    expect(fileSummary([], 25).count).toBe('25 de facturi')
  })
})

describe('the order of a file\'s invoices', () => {
  const file = [
    invoice('a', { invoice_number: 'FV-10', invoice_issue_date: '2026-11-12', total_with_vat: '856.80', cont: '6022', supplier_name: 'carburant Nord SRL' }),
    issued('b', { invoice_number: 'AC-2031', invoice_issue_date: '2026-11-10', total_with_vat: '2380.00', cont: '704', customer_name: 'Beta Instal SRL' }),
    invoice('c', { invoice_number: 'FV-9', invoice_issue_date: '2026-11-11', total_with_vat: '1071.00', cont: '302', supplier_name: 'Ștefan Construct SRL' }),
    invoice('d', { invoice_number: 'FV-9', invoice_issue_date: '2026-11-11', total_with_vat: '142.80', cont: '626', supplier_name: 'Atlas SA' }),
  ]
  const ids = (sort: Sort | null) => sortFileInvoices(file, sort).map((each) => each.id)

  it('is the order of the file until a column is chosen', () => {
    expect(ids(null)).toEqual(['a', 'b', 'c', 'd'])
  })

  it('puts numbers inside a text in their own order: FV-9 before FV-10', () => {
    expect(ids({ column: 'number', direction: 'asc' })).toEqual(['b', 'c', 'd', 'a'])
    expect(ids({ column: 'number', direction: 'desc' })).toEqual(['a', 'c', 'd', 'b'])
  })

  it('orders the kind, the other party and the account by the alphabet, whatever the capitals', () => {
    expect(ids({ column: 'kind', direction: 'asc' })).toEqual(['b', 'a', 'c', 'd'])
    // The supplier of a received invoice, the customer of an issued one; "Ș" among the S.
    expect(ids({ column: 'party', direction: 'asc' })).toEqual(['d', 'b', 'a', 'c'])
    expect(ids({ column: 'party', direction: 'desc' })).toEqual(['c', 'a', 'b', 'd'])
    expect(ids({ column: 'account', direction: 'asc' })).toEqual(['c', 'a', 'd', 'b'])
  })

  it('orders dates from the oldest and totals from the smallest', () => {
    expect(ids({ column: 'date', direction: 'asc' })).toEqual(['b', 'c', 'd', 'a'])
    expect(ids({ column: 'date', direction: 'desc' })).toEqual(['a', 'c', 'd', 'b'])
    expect(ids({ column: 'total', direction: 'asc' })).toEqual(['d', 'a', 'c', 'b'])
    expect(ids({ column: 'total', direction: 'desc' })).toEqual(['b', 'c', 'a', 'd'])
  })

  it('compares totals as numbers, not as text', () => {
    const totals = [invoice('x', { total_with_vat: '900.00' }), invoice('y', { total_with_vat: '1000.00' }), invoice('z', { total_with_vat: '-5.00' })]

    expect(sortFileInvoices(totals, { column: 'total', direction: 'asc' }).map((each) => each.id)).toEqual(['z', 'x', 'y'])
  })

  it('keeps the order of the file between two that are the same, both ways', () => {
    expect(ids({ column: 'date', direction: 'asc' }).filter((id) => id === 'c' || id === 'd')).toEqual(['c', 'd'])
    expect(ids({ column: 'date', direction: 'desc' }).filter((id) => id === 'c' || id === 'd')).toEqual(['c', 'd'])
  })

  it('orders an invoice with accounts on its lines by the account the list shows', () => {
    const split = invoice('s', {
      cont: null,
      line_accounts: [{ line: 1, cont: '302' }, { line: 2, cont: '302' }, { line: 3, cont: '624' }] as Invoice['line_accounts'],
    })

    expect(sortFileInvoices([invoice('k', { cont: '401' }), split], { column: 'account', direction: 'asc' }).map((each) => each.id)).toEqual(['s', 'k'])
  })

  it('leaves the list given as it was', () => {
    sortFileInvoices(file, { column: 'total', direction: 'asc' })

    expect(file.map((each) => each.id)).toEqual(['a', 'b', 'c', 'd'])
  })
})

describe('pressing a column heading', () => {
  it('orders ascending first, then descending, then ascending again', () => {
    expect(nextSort(null, 'total')).toEqual({ column: 'total', direction: 'asc' })
    expect(nextSort({ column: 'total', direction: 'asc' }, 'total')).toEqual({ column: 'total', direction: 'desc' })
    expect(nextSort({ column: 'total', direction: 'desc' }, 'total')).toEqual({ column: 'total', direction: 'asc' })
  })

  it('starts ascending on another column', () => {
    expect(nextSort({ column: 'total', direction: 'desc' }, 'date')).toEqual({ column: 'date', direction: 'asc' })
  })

  it('is said in words under the table', () => {
    expect(sortedLine({ column: 'total', direction: 'desc' })).toBe('Ordonate după total, de la cel mai mare.')
    expect(sortedLine({ column: 'total', direction: 'asc' })).toBe('Ordonate după total, de la cel mai mic.')
    expect(sortedLine({ column: 'date', direction: 'asc' })).toBe('Ordonate după dată, cele mai vechi întâi.')
    expect(sortedLine({ column: 'date', direction: 'desc' })).toBe('Ordonate după dată, cele mai noi întâi.')
    expect(sortedLine({ column: 'number', direction: 'asc' })).toBe('Ordonate după numărul facturii, de la A la Z.')
    expect(sortedLine({ column: 'party', direction: 'desc' })).toBe('Ordonate după furnizor sau client, de la Z la A.')
    expect(sortedLine({ column: 'kind', direction: 'asc' })).toBe('Ordonate după fel: întâi cele emise.')
    expect(sortedLine({ column: 'kind', direction: 'desc' })).toBe('Ordonate după fel: întâi cele primite.')
    expect(sortedLine({ column: 'account', direction: 'asc' })).toBe('Ordonate după cont, crescător.')
    expect(sortedLine({ column: 'account', direction: 'desc' })).toBe('Ordonate după cont, descrescător.')
  })
})

describe('the rows under an open invoice', () => {
  const lines = [
    { number: 1, description: 'Ciment 40 kg', details: null, quantity: '30', unit_name: 'BUC', value: '510.00', vat_percent: '19' },
    { number: 2, description: 'Transport marfă', details: 'Livrare la șantier', quantity: '1', unit_name: 'BUC', value: '120.00', vat_percent: '19' },
  ]
  const document = {
    lines,
    adjustments: [
      { number: 3, description: 'Discount comercial', value: '-30.00', is_charge: false, reason: 'Discount comercial', amount: '30.00' },
      { number: 4, description: 'Taxă suplimentară', value: '12.00', is_charge: true, reason: null, amount: '12.00' },
    ],
  }

  it('are its lines, then each discount or charge on the whole invoice, each with its own account', () => {
    const accounts = [{ line: 1, cont: '302' }, { line: 2, cont: '624' }, { line: 3, cont: '609' }, { line: 4, cont: null }] as NonNullable<Invoice['line_accounts']>

    const rows = lineRows(document as never, accounts, '302')

    expect(rows.map((row) => [row.number, row.description, row.value, row.cont])).toEqual([
      [1, 'Ciment 40 kg', '510.00', '302'], [2, 'Transport marfă', '120.00', '624'],
      [3, 'Discount comercial', '-30.00', '609'], [4, 'Taxă suplimentară', '12.00', null],
    ])
    expect(rows[1].details).toBe('Livrare la șantier')
    expect(rows[0].entry).toBe(accounts[0])
    expect(rows[2].entry).toBe(accounts[2])
    expect(rows.map((row) => row.wholeInvoice)).toEqual([false, false, true, true])
    // A discount has no quantity of its own.
    expect([rows[2].quantity, rows[2].unit_name]).toEqual([null, null])
  })

  it('carry the account of the invoice when the invoice has one for all its lines', () => {
    const rows = lineRows(document as never, null, '6022')

    expect(rows.map((row) => [row.cont, row.entry])).toEqual([['6022', null], ['6022', null], ['6022', null], ['6022', null]])
  })
})
