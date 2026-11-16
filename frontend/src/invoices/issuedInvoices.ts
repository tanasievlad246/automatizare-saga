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

/** What stands in place of the received invoices when a client has none. */
export function whenNoneReceived(everDownloaded: boolean): string {
  return everDownloaded
    ? 'Nicio factură primită în zilele descărcate până acum. Pentru zile mai vechi, apăsați „Descarcă facturile” și alegeți zilele.'
    : 'Nu ați descărcat încă facturi pentru acest client. Apăsați „Descarcă facturile”.'
}

/** On the screen of an issued invoice, in place of the account and of the file for SAGA. */
export const ISSUED_INVOICE = {
  title: 'Factură emisă',
  text: 'Este o factură pe care clientul a emis-o, nu una primită. Programul nu îi alege cont și nu o scrie pentru SAGA.',
}
