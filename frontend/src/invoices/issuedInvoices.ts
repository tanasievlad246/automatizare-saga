import { countOf } from '../format'
import type { Invoice } from '../types'

/** An invoice the client issued itself: ANAF lists it as "FACTURA TRIMISA". */
export function isIssued(invoice: Pick<Invoice, 'message_type'>): boolean {
  return invoice.message_type.toUpperCase().startsWith('FACTURA TRIMISA')
}

/** What the card on a client's screen says about its issued invoices, shown or hidden. */
export function issuedSummary(count: number): string {
  if (count === 0) return 'Programul nu a descărcat nicio factură emisă de acest client.'
  return count === 1
    ? 'Programul a descărcat și o factură emisă de acest client. Ea nu primește cont și nu se scrie pentru SAGA; o puteți doar vedea.'
    : `Programul a descărcat și ${countOf(count, 'o factură emisă', 'facturi emise')} de acest client. Ele nu primesc cont și nu se scriu pentru SAGA; le puteți doar vedea.`
}

/** How many issued invoices are listed at first. A client can have thousands; that many rows stall the page. */
export const MOST_ISSUED_SHOWN = 200

/** The newest on top: by the date on the invoice, then by ANAF's number for it. One without a date goes last. */
export function newestFirst(invoices: Invoice[]): Invoice[] {
  return [...invoices].sort(
    (one, other) =>
      (other.invoice_issue_date ?? '').localeCompare(one.invoice_issue_date ?? '') ||
      other.id.localeCompare(one.id, undefined, { numeric: true }),
  )
}

/** Said under the list while it holds only the newest; null when all of them are on screen. */
export function notAllShown(total: number): string | null {
  return total > MOST_ISSUED_SHOWN
    ? `Se văd cele mai noi ${MOST_ISSUED_SHOWN} din ${countOf(total, 'o factură emisă', 'facturi emise')}.`
    : null
}

/** What stands in place of the received invoices when a client has none. */
export function whenNoneReceived(everDownloaded: boolean): string {
  return everDownloaded
    ? 'Nicio factură primită în perioada descărcată până acum. Pentru zile mai vechi, apăsați „Descarcă facturile” și alegeți zilele.'
    : 'Nu ați descărcat încă facturi pentru acest client. Apăsați „Descarcă facturile”.'
}

/** On the screen of an issued invoice, in place of the account and of the file for SAGA. */
export const ISSUED_INVOICE = {
  title: 'Factură emisă',
  text: 'Este o factură pe care clientul a emis-o, nu una primită. Programul nu îi alege cont și nu o scrie pentru SAGA.',
}
