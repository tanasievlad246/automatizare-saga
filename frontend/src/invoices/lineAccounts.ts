import { countOf, formatPercent } from '../format'
import type { Invoice, InvoiceLine, LineAccount } from '../types'

/**
 * What the window for an account is about: one line of the invoice, or all of them at once.
 * `followers`: for the largest line, the lines that take its account.
 */
export type LineTarget =
  | { entry: LineAccount; description: string; details: string | null; value: string | null; followers: number[] }
  | 'all'

const CHOSEN_BY: Record<string, (entry: LineAccount) => string> = {
  rules: (entry) => (entry.rule ? `după regula „${entry.rule}”` : 'după o regulă a dumneavoastră'),
  jev: (entry) => `ales de Jev, sigur ${formatPercent(entry.confidence)}`,
  jev_accepted: () => 'propus de Jev, acceptat de dumneavoastră',
  human: () => 'ales de dumneavoastră',
  follows: () => 'ca linia cea mai mare',
  invoice: () => 'contul facturii, păstrat la împărțire',
}

// Why a line waits, from the program's English reason; the first that fits.
const WAITING_BECAUSE: [(reason: string) => boolean, string][] = [
  [(reason) => reason.startsWith('The same invoice'), 'factura pare trimisă de două ori'],
  [(reason) => reason.startsWith('The rules were skipped') && reason.includes('OpenRouter is not set up'), 'regulile au fost sărite, iar Jev nu este pornit'],
  [(reason) => reason.includes('OpenRouter is not set up'), 'nicio regulă nu se potrivește, iar Jev nu este pornit'],
  [(reason) => reason.includes('no accounts for Jev'), 'nicio regulă nu se potrivește, iar Jev nu are conturi din care să aleagă'],
  [(reason) => reason.startsWith('Jev declined'), 'Jev nu a vrut să răspundă'],
  [(reason) => reason.startsWith('Jev found that none'), 'Jev nu a găsit un cont potrivit'],
  [(reason) => reason.startsWith('Jev could not decide'), 'Jev nu a dat un răspuns folosibil'],
  [(reason) => reason.includes('do not fit'), 'linia și lista de conturi nu încap într-o întrebare pentru Jev'],
  [(reason) => reason.startsWith('Waiting: OpenRouter failed'), 'Jev nu a putut fi întrebat încă; programul încearcă din nou la următoarea descărcare'],
]

/** Under a line's account: who chose it; for a line that waits, what Jev proposed or why there is nothing. */
export function whoChoseLine(entry: LineAccount): string {
  if (entry.cont) return CHOSEN_BY[entry.method ?? '']?.(entry) ?? 'ales de dumneavoastră'
  if (entry.method === 'follows') return 'primește contul liniei celei mai mari, după ce îl alegeți'
  if (entry.suggested_cont) {
    return entry.confidence === null
      ? `Jev propune ${entry.suggested_cont}, fără să spună cât de sigur este`
      : `Jev propune ${entry.suggested_cont}, sigur doar ${formatPercent(entry.confidence)}`
  }
  return whyWaiting(entry.reason) ?? 'alegeți contul acestei linii'
}

/** Why a line (or an invoice) waits for a person, from the program's English reason; null when it is not one of these. */
export function whyWaiting(reason: string): string | null {
  return WAITING_BECAUSE.find(([fits]) => fits(reason))?.[1] ?? null
}

/** The number of the largest line, whatever its sign, the first of equals: the one the program decides by. */
export function largestLine(lines: { number: number; value: string }[]): number | null {
  let largest: { number: number; size: number } | null = null
  for (const line of lines) {
    const size = Math.abs(Number(line.value))
    if (largest === null || size > largest.size) largest = { number: line.number, size }
  }
  return largest?.number ?? null
}

/**
 * What the window is about when a line's number, or "all", is chosen on an invoice with an
 * account on each line. Nothing for a line the invoice does not have.
 */
export function lineTarget(
  document: { lines: Pick<InvoiceLine, 'number' | 'description' | 'details' | 'value'>[] },
  entries: LineAccount[] | null, choosing: number | 'all' | null,
): LineTarget | null {
  if (choosing === 'all') return 'all'
  const line = document.lines.find((each) => each.number === choosing)
  const entry = entries?.find((each) => each.line === choosing)
  if (!line || !entry) return null
  // The lines that take the largest line's account change with it: its window says so.
  const followers = (entries ?? []).filter((each) => each.method === 'follows').map((each) => each.line)
  return {
    entry, description: line.description, details: line.details, value: line.value,
    followers: line.number === largestLine(document.lines) ? followers : [],
  }
}

const INVOICE_CHOSEN_BY: Record<string, (invoice: Invoice) => string> = {
  rules: () => 'ales de o regulă a dumneavoastră',
  jev: (invoice) => `ales de Jev, sigur ${formatPercent(invoice.confidence)}`,
  jev_accepted: () => 'propus de Jev, acceptat de dumneavoastră',
  human: () => 'ales de dumneavoastră',
}

/** Beside the one account of an invoice, in a sentence: who chose it. Null when that is not known. */
export function whoChoseInvoice(invoice: Pick<Invoice, 'classification_method' | 'confidence'>): string | null {
  return INVOICE_CHOSEN_BY[invoice.classification_method ?? '']?.(invoice as Invoice) ?? null
}

/** The accounts the lines are on, with how many lines each; the most used first, then in line order. */
export function accountsUsed(entries: LineAccount[]): { cont: string; lines: number }[] {
  const counted = new Map<string, number>()
  for (const entry of entries) if (entry.cont) counted.set(entry.cont, (counted.get(entry.cont) ?? 0) + 1)
  return [...counted].map(([cont, lines]) => ({ cont, lines })).sort((one, other) => other.lines - one.lines)
}

/** The lines that wait for a choice. One that only takes the largest line's account needs none of its own. */
export function linesLeft(entries: LineAccount[]): number {
  return entries.filter((entry) => !entry.cont && entry.method !== 'follows').length
}

/** Said on the invoice while some lines have no account. */
export function linesLeftNote(left: number): string {
  return left === 1
    ? 'O linie nu are încă un cont. Factura intră în fișierul pentru SAGA după ce îl alegeți.'
    : `${countOf(left, 'o linie', 'linii')} nu au încă un cont. Factura intră în fișierul pentru SAGA după ce le alegeți.`
}

/**
 * The "Cont" column of a list: the invoice's account (its largest line's, once every line has
 * one), then how many other accounts its lines are on, or how many lines still wait.
 */
export function listAccount(invoice: Invoice): { main: string | null; more: string | null } {
  const entries = invoice.line_accounts
  if (!entries) return { main: invoice.cont, more: null }
  const used = accountsUsed(entries)
  const main = invoice.cont ?? used[0]?.cont ?? null
  const left = linesLeft(entries)
  const others = used.filter((account) => account.cont !== main).length
  return {
    main,
    more: left ? countOf(left, 'o linie fără cont', 'linii fără cont') : others ? `+${others}` : null,
  }
}
