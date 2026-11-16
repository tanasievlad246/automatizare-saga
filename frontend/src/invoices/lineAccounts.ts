import { countOf, formatPercent } from '../format'
import type { Invoice, LineAccount } from '../types'

const CHOSEN_BY: Record<string, (entry: LineAccount) => string> = {
  rules: (entry) => (entry.rule ? `după regula „${entry.rule}”` : 'după o regulă a dumneavoastră'),
  jev: (entry) => `ales de Jev, sigur ${formatPercent(entry.confidence)}`,
  jev_accepted: () => 'propus de Jev, acceptat de dumneavoastră',
  human: () => 'ales de dumneavoastră',
  follows: () => 'ca linia cea mai mare',
}

// Why a line waits, from the program's English reason; the first that fits.
const WAITING_BECAUSE: [(reason: string) => boolean, string][] = [
  [(reason) => reason.startsWith('The same invoice'), 'factura pare trimisă de două ori'],
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
  return WAITING_BECAUSE.find(([fits]) => fits(entry.reason))?.[1] ?? 'alegeți contul acestei linii'
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
