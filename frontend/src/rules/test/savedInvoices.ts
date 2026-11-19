import { countOf } from '../../format'
import type { Invoice } from '../../types'

/** Newest first, at most `limit`, without the messages that could not be read as invoices (no number). */
export function usableInvoices(invoices: Invoice[], limit: number): Invoice[] {
  return invoices
    .filter((invoice) => invoice.invoice_number !== null)
    .sort((a, b) => (b.invoice_issue_date ?? '').localeCompare(a.invoice_issue_date ?? ''))
    .slice(0, limit)
}

/** "Ultimele 20 de facturi primite de X": the number is the one listed. */
export function pickerLine(count: number, clientName: string): string {
  if (count === 0) return `Facturile primite de ${clientName}`
  return count === 1 ? `Ultima factură primită de ${clientName}` : `Ultimele ${countOf(count, '', 'facturi primite')} de ${clientName}`
}
