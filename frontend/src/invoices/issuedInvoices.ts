import { countOf } from '../format'
import type { Invoice, InvoiceKind } from '../types'

/** An invoice the client issued itself: ANAF lists it as "FACTURA TRIMISA". */
export function isIssued(invoice: Pick<Invoice, 'message_type'>): boolean {
  return (invoice.message_type ?? '').toUpperCase().startsWith('FACTURA TRIMISA')
}

/** Which of a client's two lists the address asks for: "?fel=emise" is the issued one. */
export function kindFrom(search: URLSearchParams): InvoiceKind {
  return search.get('fel') === 'emise' ? 'issued' : 'received'
}

/** The two tabs over a client's invoices, with how many there are of each once that is known. */
export function kindTabs(received: number | undefined, issued: number | undefined): { value: InvoiceKind; label: string }[] {
  const counted = (label: string, count: number | undefined) => (count === undefined ? label : `${label} (${count})`)
  return [
    { value: 'received', label: counted('Facturi primite', received) },
    { value: 'issued', label: counted('Facturi emise', issued) },
  ]
}

const NEVER_DOWNLOADED = 'Nu ați descărcat încă facturi pentru acest client. Apăsați „Descarcă facturile”.'
const OLDER_DAYS = 'Pentru zile mai vechi, apăsați „Descarcă facturile” și alegeți zilele.'

/** What stands in place of the received invoices when a client has none. */
export function whenNoneReceived(everDownloaded: boolean): string {
  return everDownloaded ? `Nicio factură primită în perioada descărcată până acum. ${OLDER_DAYS}` : NEVER_DOWNLOADED
}

/** What stands in place of the issued invoices when a client has none. */
export function whenNoneIssued(everDownloaded: boolean): string {
  return everDownloaded ? `Nicio factură emisă în perioada descărcată până acum. ${OLDER_DAYS}` : NEVER_DOWNLOADED
}

// The program's reasons for an invoice whose parties do not fit its kind, said in Romanian.
const MISFITS: [string, string][] = [
  ['The client invoiced itself', 'Factura este emisă de client către el însuși. Hotărâți dacă trebuie înregistrată și cum.'],
  [
    'The supplier on this issued invoice is not the client',
    'Furnizorul de pe această factură emisă nu este clientul, așa că SAGA nu ar pune-o la „Ieșiri”. Verificați dacă factura este a acestui client.',
  ],
  [
    'The client is the supplier of this received invoice',
    'Clientul este furnizorul acestei facturi primite, așa că SAGA ar pune-o la „Ieșiri”. Verificați dacă factura este a acestui client.',
  ],
]

/**
 * Why an invoice waits because its parties do not fit its kind (SAGA files an invoice by its
 * supplier), or null when it waits for another reason.
 */
export function misfitReason(reason: string | null): string | null {
  return MISFITS.find(([start]) => reason?.startsWith(start))?.[1] ?? null
}

/**
 * Beside the file for SAGA: how many of its invoices are of each kind, and where SAGA puts
 * them. Nothing for received invoices alone, which is how it always was.
 */
export function kindsLine(received: number, issued: number): string | null {
  if (issued === 0) return null
  if (received === 0) {
    return issued === 1
      ? 'Este o factură emisă: în SAGA ajunge în „Ieșiri”.'
      : 'Toate sunt facturi emise: în SAGA ajung în „Ieșiri”.'
  }
  const receivedPart = received === 1 ? 'una primită' : countOf(received, '', 'primite')
  const issuedPart = issued === 1 ? 'una emisă' : countOf(issued, '', 'emise')
  const counted = `${receivedPart} și ${issuedPart}`
  const receivedGo = received === 1 ? 'cea primită ajunge' : 'cele primite ajung'
  const issuedGo = issued === 1 ? 'cea emisă' : 'cele emise'
  return `${counted.charAt(0).toUpperCase()}${counted.slice(1)}. În SAGA, ${receivedGo} în „Intrări”, iar ${issuedGo} în „Ieșiri”.`
}
