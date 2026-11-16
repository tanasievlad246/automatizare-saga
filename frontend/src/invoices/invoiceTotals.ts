import { formatMoney } from '../format'
import type { InvoiceDocument } from '../types'

/** One row of the totals under an invoice. `large` is the last row, what the reader looks for. */
export type TotalRow = { label: string; amount: string; weight: 'plain' | 'bold' | 'large' }

// Amounts stay the text the invoice carries: they are compared with zero and stripped of
// their sign, never added up here.
const written = (amount: string | null) => (amount !== null && Number(amount) !== 0 ? amount.trim() : null)
const isNegative = (amount: string) => amount.startsWith('-')
const withoutSign = (amount: string) => amount.replace(/^[-+]/, '')

/**
 * The totals as a person adds them up. Most invoices have three rows. One that asks for
 * another sum than it is worth also says why: an earlier unpaid balance (which suppliers
 * write as a negative paid amount), an advance already paid, or a rounding.
 */
export function totalRows(document: InvoiceDocument): TotalRow[] {
  const money = (amount: string | null) => formatMoney(amount, document.currency)
  const prepaid = written(document.total_prepaid)
  const rounding = written(document.total_rounding)
  const rows: TotalRow[] = [
    { label: 'Fără TVA', amount: money(document.total_without_vat), weight: 'plain' },
    { label: 'TVA', amount: money(document.total_vat), weight: 'plain' },
  ]
  if (!prepaid && !rounding) return [...rows, { label: 'Total', amount: money(document.total_payable), weight: 'large' }]

  rows.push({ label: 'Total factură', amount: money(document.total_with_vat), weight: 'bold' })
  if (prepaid) {
    rows.push(
      isNegative(prepaid)
        ? { label: 'Datorie restantă (sold anterior)', amount: money(withoutSign(prepaid)), weight: 'plain' }
        : { label: 'Plătit în avans', amount: `−${money(prepaid)}`, weight: 'plain' },
    )
  }
  if (rounding) {
    const amount = isNegative(rounding) ? `−${money(withoutSign(rounding))}` : money(rounding)
    rows.push({ label: 'Rotunjire', amount, weight: 'plain' })
  }
  return [...rows, { label: 'De plată', amount: money(document.total_payable), weight: 'large' }]
}

/**
 * Why what is left to pay is not what the invoice is worth, and which of the two SAGA gets.
 * `goesToSaga` is false for an invoice the client issued: nothing is written for SAGA from it.
 */
export function totalsNote(document: InvoiceDocument, goesToSaga: boolean): string | null {
  const prepaid = written(document.total_prepaid)
  if (!prepaid) return null
  const worth = formatMoney(document.total_with_vat, document.currency)
  return isNegative(prepaid)
    ? `Suma de plată cuprinde și o datorie mai veche, care nu face parte din această factură.${goesToSaga ? ` În fișierul pentru SAGA intră doar valoarea facturii: ${worth}.` : ''}`
    : `Din suma de plată s-a scăzut ce s-a plătit în avans.${goesToSaga ? ` În fișierul pentru SAGA intră valoarea întreagă a facturii: ${worth}.` : ''}`
}
