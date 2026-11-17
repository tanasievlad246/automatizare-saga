import { pageFrom } from '@/components/paging'
import { countOf } from '../format'
import { searchWords, wordsFound } from '../textSearch'
import type { Invoice } from '../types'

/** Whose name a list is about: the supplier of a received invoice, or the buyer of an issued one. */
export type Party = 'supplier' | 'customer'

export const ORDERS = ['noi', 'vechi', 'nume', 'total-mare', 'total-mic'] as const
export type Order = (typeof ORDERS)[number]

/** What is chosen above a list of invoices; it is kept in the page's address. */
export type ListState = { page: number; text: string; from: string; until: string; cont: string; order: Order }

/** Every invoice, the newest first, on the first page. */
export const DEFAULT_LIST: ListState = { page: 1, text: '', from: '', until: '', cont: '', order: 'noi' }

/** The choice "Fără cont încă" of the account list. */
export const NO_ACCOUNT = 'fara'

/** How many invoices one page holds. */
export const INVOICES_PER_PAGE = 25

// The names in the address; the issued list puts "emise-" in front of each.
const KEYS = { page: 'pagina', text: 'cauta', from: 'de-la', until: 'pana-la', cont: 'cont', order: 'ordine' } as const
const DAY = /^\d{4}-\d{2}-\d{2}$/

/** A day written "2026-10-31" that is on the calendar: the date field could not show "2026-02-31". */
function isRealDay(text: string): boolean {
  if (!DAY.test(text)) return false
  const day = new Date(`${text}T00:00:00Z`)
  return !Number.isNaN(day.getTime()) && day.toISOString().slice(0, 10) === text
}

/** What the address says is chosen above one list; anything it does not know is left as for the whole list. */
export function readListState(search: URLSearchParams, prefix = ''): ListState {
  const read = (key: keyof typeof KEYS) => search.get(prefix + KEYS[key]) ?? ''
  const day = (key: 'from' | 'until') => (isRealDay(read(key)) ? read(key) : '')
  const order = read('order')
  return {
    page: pageFrom(read('page') || null),
    text: read('text'),
    from: day('from'),
    until: day('until'),
    cont: read('cont'),
    order: (ORDERS as readonly string[]).includes(order) ? (order as Order) : 'noi',
  }
}

/**
 * The address after a change above one list. What equals the whole list is left out, the rest of
 * the address is kept, and any change but the page's goes back to the first page.
 */
export function writeListState(search: URLSearchParams, prefix: string, changes: Partial<ListState>): URLSearchParams {
  const written = new URLSearchParams(search)
  for (const [key, value] of Object.entries(changes) as [keyof ListState, string | number][]) {
    const name = prefix + KEYS[key]
    if (value === DEFAULT_LIST[key]) written.delete(name)
    else written.set(name, String(value))
  }
  if (Object.keys(changes).some((key) => key !== 'page')) written.delete(prefix + KEYS.page)
  return written
}

/** "Arată toate facturile": no search, no period, no account, the first page; the order stays. */
export function clearFilters(search: URLSearchParams, prefix: string): URLSearchParams {
  const written = new URLSearchParams(search)
  for (const key of ['page', 'text', 'from', 'until', 'cont'] as const) written.delete(prefix + KEYS[key])
  return written
}

/** Whether a search, a day or an account narrows the list. Another order or page does not, nor a search of signs alone. */
export function filtersOn(state: ListState): boolean {
  return Boolean(searchWords(state.text).length || state.from || state.until || state.cont)
}

/** The day on the invoice, "2026-10-31", without the time zone some suppliers write after it ("+02:00"). */
const dayOf = (invoice: Invoice) => (invoice.invoice_issue_date ?? '').slice(0, 10)

/** The accounts an invoice's lines are on, and whether some line, or the whole invoice, has none yet. */
function accountsOf(invoice: Invoice): { conts: string[]; missing: boolean } {
  const entries = invoice.line_accounts
  if (!entries) return { conts: invoice.cont ? [invoice.cont] : [], missing: !invoice.cont }
  return {
    conts: entries.flatMap((entry) => (entry.cont ? [entry.cont] : [])),
    missing: entries.length === 0 || entries.some((entry) => !entry.cont),
  }
}

/** The invoices that fit the search, the period and the account, in the order given. */
export function filterInvoices(invoices: Invoice[], state: ListState, party: Party): Invoice[] {
  const words = searchWords(state.text)
  return invoices.filter((invoice) => {
    const [name, cui] = party === 'supplier' ? [invoice.supplier_name, invoice.supplier_cui] : [invoice.customer_name, invoice.customer_cui]
    if (words.length && !wordsFound(words, [name, invoice.invoice_number], [cui])) return false
    const day = dayOf(invoice)
    if ((state.from || state.until) && !day) return false
    if (state.from && day < state.from) return false
    if (state.until && day > state.until) return false
    if (state.cont) {
      const { conts, missing } = accountsOf(invoice)
      if (state.cont === NO_ACCOUNT ? !missing : !conts.includes(state.cont)) return false
    }
    return true
  })
}

/** The choices of the account list: all, none yet, then every account the invoices are on, as in the chart of accounts. */
export function accountOptions(invoices: Invoice[], descriptions: Record<string, string>, chosen: string): { value: string; label: string }[] {
  const used = new Set(invoices.flatMap((invoice) => accountsOf(invoice).conts))
  // An account chosen earlier stays on offer, so the list says what is chosen even when no invoice is on it now.
  if (chosen && chosen !== NO_ACCOUNT) used.add(chosen)
  const conts = [...used].sort((one, other) => (one < other ? -1 : one > other ? 1 : 0))
  return [
    { value: '', label: 'Toate conturile' },
    { value: NO_ACCOUNT, label: 'Fără cont încă' },
    ...conts.map((cont) => ({ value: cont, label: descriptions[cont] ? `${cont} · ${shortName(descriptions[cont])}` : cont })),
  ]
}

const LONGEST_NAME = 38

/**
 * An account's description is written for Jev, often a long sentence: the list shows what comes
 * before its first ":" or ".", cut at a word with "…" when that is still long.
 */
function shortName(description: string): string {
  const name = description.split(/[:.]/)[0].trim()
  if (name.length <= LONGEST_NAME) return name
  const cut = name.slice(0, LONGEST_NAME + 1).replace(/\s+\S*$/, '')
  return `${cut.replace(/[,;]$/, '')}…`
}

/** The orders a list can be put in, in words. */
export function orderOptions(party: Party): { value: Order; label: string }[] {
  return [
    { value: 'noi', label: 'Cele mai noi întâi' },
    { value: 'vechi', label: 'Cele mai vechi întâi' },
    { value: 'nume', label: party === 'supplier' ? 'Furnizorul, de la A la Z' : 'Cumpărătorul, de la A la Z' },
    { value: 'total-mare', label: 'Totalul, cel mai mare întâi' },
    { value: 'total-mic', label: 'Totalul, cel mai mic întâi' },
  ]
}

const byName = new Intl.Collator('ro', { sensitivity: 'base' })
const byNumber = new Intl.Collator(undefined, { numeric: true })

// Newest first: by the date on the invoice, then by ANAF's number for it. One without a date goes last.
const newest = (one: Invoice, other: Invoice) =>
  dayOf(other).localeCompare(dayOf(one)) || byNumber.compare(other.id, one.id)

// Oldest first, but one without a date still last.
const oldest = (one: Invoice, other: Invoice) =>
  Number(!dayOf(one)) - Number(!dayOf(other)) || dayOf(one).localeCompare(dayOf(other)) || byNumber.compare(one.id, other.id)

/** A value that can be compared, or null; a missing one goes last whichever way the list runs. */
function lastWhenMissing<T>(one: T | null, other: T | null, compare: (one: T, other: T) => number): number {
  if (one === null || other === null) return Number(one === null) - Number(other === null)
  return compare(one, other)
}

const totalOf = (invoice: Invoice) => {
  const total = Number.parseFloat(invoice.total_with_vat ?? '')
  return Number.isFinite(total) ? total : null
}

/** A new list in the order chosen; the one given is left as it was. Ties go newest first. */
export function sortInvoices(invoices: Invoice[], order: Order, party: Party): Invoice[] {
  const nameOf = (invoice: Invoice) => (party === 'supplier' ? invoice.supplier_name : invoice.customer_name) || null
  const compare: Record<Order, (one: Invoice, other: Invoice) => number> = {
    noi: newest,
    vechi: oldest,
    nume: (one, other) => lastWhenMissing(nameOf(one), nameOf(other), byName.compare) || newest(one, other),
    'total-mare': (one, other) => lastWhenMissing(totalOf(one), totalOf(other), (a, b) => b - a) || newest(one, other),
    'total-mic': (one, other) => lastWhenMissing(totalOf(one), totalOf(other), (a, b) => a - b) || newest(one, other),
  }
  return [...invoices].sort(compare[order])
}

/** Over a narrowed list: how many invoices are seen of all the client's. */
export function foundLine(shown: number, all: number): string {
  return `${shown === 1 ? 'Se vede' : 'Se văd'} ${countOf(shown, 'o factură', 'facturi')} din ${all}.`
}
