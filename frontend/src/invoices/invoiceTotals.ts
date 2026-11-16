import { formatMoney } from '../format'
import type { InvoiceDocument } from '../types'

/** One row of the totals under an invoice. `large` is the last row, what the reader looks for. */
export type TotalRow = { label: string; amount: string; weight: 'plain' | 'bold' | 'large' }

// Amounts stay the text the invoice carries: they are compared with zero and stripped of
// their sign, never added up here. A document read by an older program may lack a field.
const written = (amount: string | null | undefined) => (amount != null && Number(amount) !== 0 ? amount.trim() : null)
const isNegative = (amount: string | null | undefined) => amount?.trim().startsWith('-') === true
const withoutSign = (amount: string) => amount.replace(/^[-+]/, '')

/**
 * What the paid amount (BT-113) of this invoice means, if it has one. On an ordinary
 * invoice a negative one is an earlier unpaid balance the supplier adds to what is due,
 * and a positive one was paid already, on the spot or before. On a credit note, or an
 * invoice that is itself negative, it may be money given back: it is then shown as written.
 */
function paidAmount(document: InvoiceDocument): { kind: 'earlier-debt' | 'paid' | 'as-written'; amount: string } | null {
  const amount = written(document.total_prepaid)
  if (!amount) return null
  if (document.is_credit_note || isNegative(document.total_with_vat)) return { kind: 'as-written', amount }
  return { kind: isNegative(amount) ? 'earlier-debt' : 'paid', amount }
}

/**
 * The totals as a person adds them up. Most invoices have three rows. One that asks for
 * another sum than it is worth also says why: an earlier unpaid balance, something
 * already paid, or a rounding.
 */
export function totalRows(document: InvoiceDocument): TotalRow[] {
  // One minus sign for the whole block: the one put before what is taken off.
  const money = (amount: string | null | undefined) => formatMoney(amount, document.currency).replace(/^-/, '−')
  const paid = paidAmount(document)
  const rounding = written(document.total_rounding)
  const rows: TotalRow[] = [
    { label: 'Fără TVA', amount: money(document.total_without_vat), weight: 'plain' },
    { label: 'TVA', amount: money(document.total_vat), weight: 'plain' },
  ]
  if (!paid && !rounding) return [...rows, { label: 'Total', amount: money(document.total_payable), weight: 'large' }]

  rows.push({ label: 'Total factură', amount: money(document.total_with_vat), weight: 'bold' })
  if (paid?.kind === 'earlier-debt') {
    rows.push({ label: 'Datorie restantă (sold anterior)', amount: money(withoutSign(paid.amount)), weight: 'plain' })
  } else if (paid?.kind === 'paid') {
    rows.push({ label: 'Deja plătit', amount: `−${money(paid.amount)}`, weight: 'plain' })
  } else if (paid) {
    rows.push({ label: 'Sumă plătită', amount: money(paid.amount), weight: 'plain' })
  }
  if (rounding) rows.push({ label: 'Rotunjire', amount: money(rounding), weight: 'plain' })
  return [...rows, { label: 'De plată', amount: money(document.total_payable), weight: 'large' }]
}

/**
 * Why what is left to pay is not what the invoice is worth, and which of the two SAGA gets.
 * `goesToSaga` is false for an invoice the client issued: nothing is written for SAGA from it.
 */
export function totalsNote(document: InvoiceDocument, goesToSaga: boolean): string | null {
  const paid = paidAmount(document)
  if (!paid || paid.kind === 'as-written') return null
  const worth = formatMoney(document.total_with_vat, document.currency)
  return paid.kind === 'earlier-debt'
    ? `Suma de plată cuprinde și o datorie mai veche, care nu face parte din această factură.${goesToSaga ? ` În fișierul pentru SAGA intră doar valoarea facturii: ${worth}.` : ''}`
    : `Din suma de plată s-a scăzut ce s-a plătit deja.${goesToSaga ? ` În fișierul pentru SAGA intră valoarea întreagă a facturii: ${worth}.` : ''}`
}
