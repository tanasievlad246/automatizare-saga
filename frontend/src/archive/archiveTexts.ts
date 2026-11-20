import { countOf, formatFromWhen, formatWhen } from '../format'
import type { ClientTab, SagaImportRef, SagaImportSource } from '../types'

// What "?fel=" says for each tab; the received invoices are the tab of an address that says nothing.
const TAB_IN_ADDRESS: Partial<Record<ClientTab, string>> = { issued: 'emise', saga: 'saga', archive: 'arhiva' }

/** Which tab of a client's screen the address asks for: "?fel=emise", "?fel=saga", "?fel=arhiva", or the received invoices. */
export function tabFrom(search: URLSearchParams): ClientTab {
  const asked = search.get('fel')
  const found = Object.entries(TAB_IN_ADDRESS).find(([, written]) => written === asked)
  return (found?.[0] as ClientTab | undefined) ?? 'received'
}

/** The address of a tab: each starts whole, at its first page. */
export function searchForTab(tab: ClientTab): Record<string, string> {
  const written = TAB_IN_ADDRESS[tab]
  return written ? { fel: written } : {}
}

/** The four tabs, each counted once what it counts is known: invoices, files waiting for SAGA, confirmed imports. */
export function clientTabs(
  received: number | undefined, issued: number | undefined, files: number | undefined, imports: number | undefined,
): { value: ClientTab; label: string }[] {
  const counted = (label: string, count: number | undefined) => (count === undefined ? label : `${label} (${count})`)
  return [
    { value: 'received', label: counted('Facturi primite', received) },
    { value: 'issued', label: counted('Facturi emise', issued) },
    { value: 'saga', label: counted('Fișiere pentru SAGA', files) },
    { value: 'archive', label: counted('Arhivă', imports) },
  ]
}

export const ARCHIVE_TEXT = {
  intro: 'Fișierele pentru SAGA confirmate ca importate, fiecare cu facturile din el, cel mai nou primul. Un import se confirmă din automatizare sau cu butonul „Da, am importat” de sub lista de facturi. Fișierul se păstrează aici așa cum l-a primit SAGA.',
  emptyTitle: 'Nu există încă niciun import în arhivă.',
  emptyText: 'Când automatizarea sau butonul „Da, am importat” confirmă că SAGA a primit fișierul, fișierul și facturile lui apar aici.',
  older: 'Facturile marcate ca importate înainte de versiunea 0.13.0 nu au un import în arhivă: atunci fișierul se ștergea.',
  gone: 'Fișierul nu mai este în arhivă.',
}

/** On the card of what waits for SAGA, when the file changed between reading it and confirming. */
export const CHANGED_MEANWHILE = {
  title: 'Fișierul s-a schimbat de când ați deschis pagina',
  text: 'Între timp fișierul a fost scris din nou: a intrat sau a ieșit o factură, ori s-a schimbat un cont. Nu s-a marcat nimic. Mai sus se vede acum fișierul așa cum este. Importați-l în SAGA, apoi confirmați din nou.',
}

/** "Import de azi, 10:42", "Import din 14.11.2026, 16:05". */
export function importTitle(importedAt: string, now = new Date()): string {
  return `Import ${formatFromWhen(importedAt, now)}`
}

export function sourceLabel(source: SagaImportSource): string {
  return source === 'api' ? 'Din automatizare' : 'De pe ecran'
}

/** "12 facturi: 7 primite, 5 emise", "4 facturi primite", with ", câte un fișier pentru fiecare" for a file per invoice. */
export function countsLine({ invoices, received, issued, files }: { invoices: number; received: number; issued: number; files: number }): string {
  const said = received > 0 && issued > 0
    ? `${countOf(invoices, 'o factură', 'facturi')}: ${countOf(received, 'o primită', 'primite')}, ${countOf(issued, 'o emisă', 'emise')}`
    : issued > 0
      ? countOf(invoices, 'o factură emisă', 'facturi emise')
      : countOf(invoices, 'o factură primită', 'facturi primite')
  return files > 1 ? `${said}, câte un fișier pentru fiecare` : said
}

/** Invoices of an import taken off "imported" since: they wait in the file for SAGA again. */
export function unmarkedLine(count: number): string | null {
  if (count === 0) return null
  return count === 1
    ? 'O factură nu mai este marcată ca importată, așa că este din nou în fișierul pentru SAGA.'
    : `${countOf(count, '', 'facturi')} nu mai sunt marcate ca importate, așa că sunt din nou în fișierul pentru SAGA.`
}

/** On an invoice's screen: "Importată în SAGA azi, la 10:42, din automatizare.", "… pe 14.11.2026, la 16:05, …". */
export function importedLine(saga: SagaImportRef, now = new Date()): string {
  const [day, time] = formatWhen(saga.imported_at, now).split(', ')
  const when = `${/^\d/.test(day) ? `pe ${day}` : day}, la ${time}`
  return `Importată în SAGA ${when}, ${saga.source === 'api' ? 'din automatizare' : 'de pe ecran'}.`
}

/** After "Da, am importat": what was marked, and where the file went. */
export function confirmedToast(invoices: number, files: number): string {
  const marked = invoices === 1
    ? 'Factura este marcată ca importată.'
    : `Cele ${countOf(invoices, '', 'facturi')} sunt marcate ca importate.`
  return `${marked} ${files > 1 ? 'Fișierele sunt acum în arhivă.' : 'Fișierul este acum în arhivă.'}`
}
