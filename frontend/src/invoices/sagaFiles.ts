import { countOf, folderOf } from '../format'
import { goesToSales } from './issuedInvoices'
import type { Invoice, SagaFilePer, SagaState } from '../types'

/** The two ways the invoices waiting for SAGA are put in files. Exactly one is in force. */
export const SAGA_WAYS: { value: SagaFilePer; title: string; text: string }[] = [
  {
    value: 'client',
    title: 'Un singur fișier pentru fiecare client',
    text: 'Toate facturile gata de import ale clientului stau într-un fișier. În SAGA îl importați o singură dată.',
  },
  {
    value: 'invoice',
    title: 'Câte un fișier pentru fiecare factură',
    text: 'Fiecare factură gata de import are fișierul ei, în folderul clientului.',
  },
]

/** Where ready invoices are: a file that holds them all, or the folder their own files are in. */
export type ReadyPlace = { path: string; invoices: Invoice[] }

/** The places to import from: one, once the folder is up to date. An invoice in no file is left out. */
export function readyPlaces(ready: Invoice[], filePer: SagaFilePer): ReadyPlace[] {
  const places = new Map<string, Invoice[]>()
  for (const invoice of ready) {
    if (!invoice.saga_xml_path) continue
    const path = filePer === 'client' ? invoice.saga_xml_path : folderOf(invoice.saga_xml_path)
    places.set(path, [...(places.get(path) ?? []), invoice])
  }
  return [...places].map(([path, invoices]) => ({ path, invoices }))
}

/**
 * Whether the client's folder may differ from what the screen shows: the program could not
 * bring it up to date, or a ready invoice is in no file. Nothing is marked as imported from
 * the list while that lasts, so that no invoice SAGA never got is ticked.
 */
export function isStale(ready: Invoice[], saga: SagaState): boolean {
  return saga.problem !== null || !saga.up_to_date || ready.some((invoice) => !invoice.saga_xml_path)
}

/** Said of the folder, not of a file: a file may be missing, old, or one too many. */
export const NOT_UP_TO_DATE = {
  title: 'Folderul pentru SAGA nu este la zi',
  text: 'Programul nu a putut scrie sau șterge un fișier din el. De obicei fișierul este deschis în SAGA: închideți acolo fereastra de import, apoi apăsați butonul.',
  retry: 'Încearcă din nou',
  first: 'Întâi aduceți folderul la zi cu „Încearcă din nou”, apoi importați în SAGA.',
  still: 'Tot nu s-a putut. Închideți fereastra de import din SAGA, apoi încercați din nou.',
}

export function placeLine(count: number, filePer: SagaFilePer): string {
  if (filePer === 'client') {
    return count === 1 ? 'O factură gata este în fișierul de mai jos:' : `${countOf(count, '', 'facturi gata sunt')} într-un singur fișier:`
  }
  return count === 1
    ? 'O factură gata este în folderul de mai jos, în fișierul ei:'
    : `${countOf(count, '', 'facturi gata sunt')} în folderul de mai jos, fiecare în fișierul ei:`
}

/** The count is on the button: if SAGA imported fewer, the difference is seen before the press. */
export function importedButton(count: number): string {
  return count === 1 ? 'Da, am importat factura' : `Da, am importat cele ${countOf(count, '', 'facturi')}`
}

/** On one invoice's screen: what to know about its place in the files for SAGA, beyond the path. */
export function fileCardNote(invoice: Invoice, saga: SagaState): string | null {
  if (saga.problem || !saga.up_to_date) {
    return `Folderul pentru SAGA al acestui client nu este la zi, așa că fișierul poate să nu arate ce vedeți aici. Deschideți lista de facturi a clientului și apăsați acolo „${NOT_UP_TO_DATE.retry}”.`
  }
  if (invoice.saga_xml_path) {
    // SAGA files an invoice among the sales by its supplier: the client itself.
    const sales = goesToSales(invoice) ? 'În SAGA ajunge în „Ieșiri”' : null
    if (saga.file_per !== 'client') return sales && `${sales}.`
    const shared = 'Factura este în fișierul clientului, împreună cu celelalte facturi gata de import'
    return sales ? `${shared}. ${sales}:` : `${shared}:`
  }
  const hasAccount = invoice.classification_status === 'classified'
  if (invoice.uploaded_to_accounting) {
    return hasAccount
      ? 'Factura este marcată ca importată, așa că nu mai este în fișierul pentru SAGA. Dacă scoateți bifa, intră la loc.'
      : 'Factura este marcată ca importată și nu are cont, așa că nu este în fișierul pentru SAGA.'
  }
  if (hasAccount) {
    return `Factura are cont, dar nu este încă în fișierul pentru SAGA. Deschideți lista de facturi a clientului și apăsați acolo „${NOT_UP_TO_DATE.retry}”.`
  }
  return invoice.line_accounts
    ? 'Factura intră în fișierul pentru SAGA imediat ce toate liniile au un cont.'
    : 'Factura intră în fișierul pentru SAGA imediat ce are un cont.'
}
