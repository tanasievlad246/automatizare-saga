import { describe, expect, it } from 'vitest'
import type { Invoice } from '../../types'
import { pickerLine, usableInvoices } from './savedInvoices'

const invoice = (id: string, date: string | null, number: string | null = 'A1') =>
  ({ id, invoice_issue_date: date, invoice_number: number }) as Invoice

describe('the saved invoices offered for a trial', () => {
  it('leaves out messages that are not invoices, newest first, and cuts at the limit', () => {
    const all = [invoice('1', '2026-01-01'), invoice('2', null, null), invoice('3', '2026-03-01'), invoice('4', '2026-02-01')]
    expect(usableInvoices(all, 2).map((i) => i.id)).toEqual(['3', '4'])
  })

  it('words the sentence from the number listed', () => {
    expect(pickerLine(1, 'Alfa SRL')).toBe('Ultima factură primită de Alfa SRL')
    expect(pickerLine(0, 'Alfa SRL')).toBe('Facturile primite de Alfa SRL')
    expect(pickerLine(3, 'Alfa SRL')).toBe('Ultimele 3 facturi primite de Alfa SRL')
    expect(pickerLine(20, 'Alfa SRL')).toBe('Ultimele 20 de facturi primite de Alfa SRL')
  })
})
