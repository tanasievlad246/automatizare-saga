import { countOf, formatMoney } from '../format'
import { isIssued } from '../invoices/issuedInvoices'
import { listAccount } from '../invoices/lineAccounts'
import { NOT_UP_TO_DATE } from '../invoices/sagaFiles'
import type { Invoice, InvoiceDocument, LineAccount } from '../types'

/** What the "Fișiere pentru SAGA" tab says around its files. */
export const FILES_TAB = {
  intro: 'Acestea sunt fișierele din folderul clientului care nu sunt încă importate în SAGA. Importați-le în SAGA, apoi apăsați „Da, am importat” de mai jos.',
  emptyTitle: 'Nu este niciun fișier de importat în SAGA pentru acest client.',
  emptyText: 'Un fișier apare aici când o factură primește un cont și nu este încă marcată ca importată. Ce s-a importat deja este la fila „Arhivă”.',
  staleTitle: NOT_UP_TO_DATE.title,
  // True also when no file is listed and nothing is ready: the button is under the tab whenever the folder is not up to date.
  staleText: `Ce se vede aici poate să nu fie ce este acum în folder. Apăsați „${NOT_UP_TO_DATE.retry}”, mai jos.`,
  missing: 'Fișierul lipsește din folder.',
  xmlButton: 'Vezi XML-ul',
  xmlExplanation: 'Așa este fișierul în folderul clientului. Pe acesta îl importă SAGA.',
  xmlGone: 'Fișierul nu mai este în folderul clientului.',
  fileOrder: 'Ordinea este cea din fișier: întâi factura care așteaptă de cel mai mult timp.',
  backToFileOrder: 'Înapoi la ordinea din fișier',
  afterAChange: 'Când schimbați un cont, programul scrie fișierul din nou. Dacă l-ați importat deja în SAGA, importați-l încă o dată.',
  oneAccount: 'Contul facturii, pentru toate liniile:',
}

export const FILES_PER_PAGE = 20
export const LINES_PER_PAGE = 10

/** The invoices a file holds, in the order it has them. One that is in neither list is left out. */
export function invoicesOf(ids: string[], received: Invoice[] | undefined, issued: Invoice[] | undefined): Invoice[] {
  const known = new Map([...(received ?? []), ...(issued ?? [])].map((invoice) => [invoice.id, invoice]))
  return ids.flatMap((id) => known.get(id) ?? [])
}

/** What the invoices are worth together, each currency apart: lei first, then by the alphabet. Added in cents. */
export function fileTotals(invoices: Invoice[]): { currency: string; amount: string }[] {
  const cents = new Map<string, number>()
  for (const invoice of invoices) {
    if (invoice.total_with_vat === null || invoice.total_with_vat === '') continue
    const currency = invoice.currency || 'RON'
    cents.set(currency, (cents.get(currency) ?? 0) + Math.round(Number(invoice.total_with_vat) * 100))
  }
  return [...cents]
    .sort(([one], [other]) => (one === 'RON' ? -1 : other === 'RON' ? 1 : one.localeCompare(other)))
    .map(([currency, sum]) => ({ currency, amount: (sum / 100).toFixed(2) }))
}

function totalsInWords(invoices: Invoice[]): string {
  return fileTotals(invoices).map(({ currency, amount }) => formatMoney(amount, currency)).join(' + ')
}

function capitalised(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/**
 * A file in words: "12 facturi" and their total, and, when it holds both kinds, each kind's
 * part ("7 primite: 3.486,20 lei · 5 emise: 10.717,20 lei"). `count` is how many the file holds,
 * said alone while its invoices are not in the lists yet.
 */
export function fileSummary(invoices: Invoice[], count = invoices.length): { count: string; total: string; kinds: string | null } {
  const issued = invoices.filter(isIssued)
  const received = invoices.filter((invoice) => !isIssued(invoice))
  if (invoices.length === 0) return { count: capitalised(countOf(count, 'o factură', 'facturi')), total: '', kinds: null }
  const both = issued.length > 0 && received.length > 0
  const said = both
    ? countOf(invoices.length, 'o factură', 'facturi')
    : issued.length > 0
      ? countOf(issued.length, 'o factură emisă', 'facturi emise')
      : countOf(received.length, 'o factură primită', 'facturi primite')
  return {
    count: capitalised(said),
    total: totalsInWords(invoices),
    kinds: both
      ? `${countOf(received.length, 'o primită', 'primite')}: ${totalsInWords(received)} · ${countOf(issued.length, 'o emisă', 'emise')}: ${totalsInWords(issued)}`
      : null,
  }
}

export type SortColumn = 'number' | 'kind' | 'party' | 'date' | 'total' | 'account'
export type Sort = { column: SortColumn; direction: 'asc' | 'desc' }

/** The columns of the table, in the order they are drawn. */
export const COLUMNS: { column: SortColumn; label: string; numeric?: boolean }[] = [
  { column: 'number', label: 'Factura' },
  { column: 'kind', label: 'Felul' },
  { column: 'party', label: 'Furnizor sau client' },
  { column: 'date', label: 'Data' },
  { column: 'total', label: 'Total', numeric: true },
  { column: 'account', label: 'Cont' },
]

export function kindOf(invoice: Invoice): string {
  return isIssued(invoice) ? 'emisă' : 'primită'
}

/** The supplier of a received invoice, the customer of an issued one. */
export function partyOf(invoice: Invoice): string | null {
  return isIssued(invoice) ? invoice.customer_name : invoice.supplier_name
}

// Whatever the capitals, "Ș" among the S, and numbers inside a text in their own order: FV-9 before FV-10.
const BY_THE_ALPHABET = new Intl.Collator('ro', { numeric: true, sensitivity: 'base' })
// Accounts as a chart of accounts lists them: 6022 before 626.
const AS_WRITTEN = new Intl.Collator('ro', { sensitivity: 'base' })

const COMPARE: Record<SortColumn, (one: Invoice, other: Invoice) => number> = {
  number: (one, other) => BY_THE_ALPHABET.compare(one.invoice_number ?? '', other.invoice_number ?? ''),
  kind: (one, other) => BY_THE_ALPHABET.compare(kindOf(one), kindOf(other)),
  party: (one, other) => BY_THE_ALPHABET.compare(partyOf(one) ?? '', partyOf(other) ?? ''),
  date: (one, other) => (one.invoice_issue_date ?? '').localeCompare(other.invoice_issue_date ?? ''),
  total: (one, other) => Number(one.total_with_vat ?? 0) - Number(other.total_with_vat ?? 0),
  account: (one, other) => AS_WRITTEN.compare(listAccount(one).main ?? '', listAccount(other).main ?? ''),
}

/**
 * A new list in the order chosen; the one given is left as it was. With no order chosen it is
 * the order of the file. Two that are the same keep the order of the file, both ways.
 */
export function sortFileInvoices(invoices: Invoice[], sort: Sort | null): Invoice[] {
  if (!sort) return [...invoices]
  const turn = sort.direction === 'asc' ? 1 : -1
  return [...invoices].sort((one, other) => turn * COMPARE[sort.column](one, other))
}

/** A press on a column's heading: ascending first, then the other way with every press. */
export function nextSort(current: Sort | null, column: SortColumn): Sort {
  return { column, direction: current?.column === column && current.direction === 'asc' ? 'desc' : 'asc' }
}

const IN_WORDS: Record<SortColumn, { asc: string; desc: string }> = {
  number: { asc: 'numărul facturii, de la A la Z', desc: 'numărul facturii, de la Z la A' },
  kind: { asc: 'fel: întâi cele emise', desc: 'fel: întâi cele primite' },
  party: { asc: 'furnizor sau client, de la A la Z', desc: 'furnizor sau client, de la Z la A' },
  date: { asc: 'dată, cele mai vechi întâi', desc: 'dată, cele mai noi întâi' },
  total: { asc: 'total, de la cel mai mic', desc: 'total, de la cel mai mare' },
  account: { asc: 'cont, crescător', desc: 'cont, descrescător' },
}

/** Under the table, while a column orders it: "Ordonate după total, de la cel mai mare." */
export function sortedLine(sort: Sort): string {
  return `Ordonate după ${IN_WORDS[sort.column][sort.direction]}.`
}

/** What the heading's button says to a screen reader: where a press takes the order. */
export function sortLabel(label: string, sort: Sort | null, column: SortColumn): string {
  const next = nextSort(sort, column)
  return `${label}: ordonează după ${IN_WORDS[column][next.direction]}`
}

/** One row under an open invoice: a line of it, or a discount or charge on the whole invoice. */
export type LineRow = {
  number: number // as SAGA's file numbers it: a discount or a charge comes after the invoice's own lines
  wholeInvoice: boolean // a discount or a charge on the whole invoice
  description: string
  details: string | null
  quantity: string | null
  unit_name: string | null
  value: string
  vat_percent: string | null
  cont: string | null
  entry: LineAccount | null // the row's own account, when the invoice has one on each line
}

/**
 * The rows SAGA gets for one invoice: its lines, then each discount or charge on the whole
 * invoice, which SAGA books as a line. Each with its account: its own when the invoice has one
 * on each line, the invoice's when it has one for all of them.
 */
export function lineRows(
  document: Pick<InvoiceDocument, 'lines' | 'adjustments'>, accounts: LineAccount[] | null, invoiceCont: string | null,
): LineRow[] {
  const accountOf = new Map(accounts?.map((entry) => [entry.line, entry]))
  const lines = document.lines.map((line): LineRow => {
    const entry = accountOf.get(line.number) ?? null
    return {
      number: line.number, wholeInvoice: false, description: line.description, details: line.details, quantity: line.quantity,
      unit_name: line.unit_name, value: line.value, vat_percent: line.vat_percent,
      cont: accounts ? (entry?.cont ?? null) : invoiceCont, entry,
    }
  })
  const adjustments = document.adjustments.map((adjustment): LineRow => {
    const entry = accountOf.get(adjustment.number) ?? null
    return {
      number: adjustment.number, wholeInvoice: true, description: adjustment.description, details: null,
      quantity: null, unit_name: null, value: adjustment.value, vat_percent: adjustment.vat_percent ?? null,
      cont: accounts ? (entry?.cont ?? null) : invoiceCont, entry,
    }
  })
  return [...lines, ...adjustments]
}
