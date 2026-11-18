// The words of "Clasifică din nou": the invoices to check, sent back through the rules and Jev.

import { countDoing, countOf, formatUsd } from '../format'
import type { ClassifyAgainResult } from '../types'

export const CLASSIFY_AGAIN_TITLE = 'Clasifică din nou facturile de verificat'

/** Under the button: when it is worth pressing. */
export const WHEN_TO_USE = 'Ați adăugat o regulă sau ați schimbat conturile? Clasificați din nou, ca regulile și Jev să încerce iar.'

/** What classifying again leaves as it is. */
export const KEPT = [
  'liniile cărora le-ați ales deja contul;',
  'liniile care au deja cont de la Jev, dacă nu li se potrivește acum o regulă;',
  'facturile cu cont și cele importate în SAGA.',
]

export const JEV_TICK = {
  label: 'Întreabă-l din nou și pe Jev',
  help: 'Fiecare întrebare se plătește, ca la descărcare, și poate dura câteva minute. Fără bifă se aplică doar regulile: gratuit, în câteva secunde.',
}

/**
 * What waits for an account: `review` to check, `waiting` for Jev. With `issued` (on a client's
 * screen), the invoices to check are named by kind; without it, as the client list always said.
 */
export function toCheckLine(review: number, waiting: number, issued?: number): string {
  const forJev = countOf(waiting, 'O factură așteaptă', 'facturi așteaptă')
  if (review === 0) return `${forJev} contul: Jev nu a răspuns la ultima descărcare.`
  const toCheck = issued === undefined ? listToCheck(review) : clientToCheck(review, issued)
  return waiting ? `${toCheck} ${forJev} contul de la Jev.` : toCheck
}

function listToCheck(review: number): string {
  return countOf(review, 'O factură este de verificat: trebuie să îi alegeți contul.', 'facturi sunt de verificat: trebuie să le alegeți contul.')
}

function clientToCheck(review: number, issued: number): string {
  if (issued === review) return `${countOf(review, 'O factură emisă este de verificat', 'facturi emise sunt de verificat')}.`
  const toCheck = countOf(review, 'O factură este de verificat', 'facturi sunt de verificat')
  if (issued === 0) return `${toCheck}.`
  return `${toCheck}: ${countOf(review - issued, 'una primită', 'primite')} și ${countOf(issued, 'una emisă', 'emise')}.`
}

/** Under the window's title: the one client, or how many. */
export function forWhom(clients: { name: string; cui: string }[]): string {
  if (clients.length === 1) return `${clients[0].name} · CUI ${clients[0].cui}`
  return `La cei ${countOf(clients.length, 'un client', 'clienți')} cu facturi de verificat`
}

/** The window's first sentence, with the tick for Jev on or off. */
export function introLine(total: number, jev: boolean): string {
  const rules = total === 1
    ? 'Factura trece din nou prin regulile dumneavoastră.'
    : `Cele ${countOf(total, '', 'facturi')} trec din nou prin regulile dumneavoastră.`
  if (!jev) return `${rules} Jev nu este întrebat.`
  return total === 1
    ? `${rules} Dacă nu o decide nicio regulă, este întrebat Jev.`
    : `${rules} Pentru ce nu decide nicio regulă este întrebat Jev.`
}

/** The button that starts it, with how many invoices it sends. */
export function startLabel(total: number): string {
  return total === 1 ? 'Clasifică din nou factura' : `Clasifică din nou cele ${countOf(total, '', 'facturi')}`
}

/**
 * How one client went. `jevStoppedBefore`: Jev was left out because it stopped answering at a
 * client before this one, not because the tick was off.
 */
export function outcomeLine(result: ClassifyAgainResult, jevStoppedBefore = false): string {
  if (result.total === 0) return 'nu mai are facturi de verificat.'
  const { classified, review, waiting, skipped } = result
  const parts: string[] = []
  if (classified === 0 && review === result.total) {
    parts.push(review === 1 ? 'factura rămâne de verificat' : `nicio factură nu a primit cont; cele ${review} rămân de verificat`)
  } else {
    if (classified) parts.push(countDoing(classified, 'o factură a primit cont', 'au primit cont'))
    if (review) parts.push(countDoing(review, 'una rămâne de verificat', 'rămân de verificat'))
  }
  if (waiting) parts.push(countDoing(waiting, 'una așteaptă încă răspunsul lui Jev', 'așteaptă încă răspunsul lui Jev'))
  if (skipped) parts.push(countDoing(skipped, 'una nu se poate citi și a fost lăsată deoparte', 'nu se pot citi și au fost lăsate deoparte'))
  const done = parts.join(', ')
  if (result.jev_stopped) {
    return `${done}. Jev nu a răspuns, așa că facturile de după au rămas cum erau. Verificați cheia OpenRouter și creditul din cont.`
  }
  if (!result.jev_asked) {
    return jevStoppedBefore ? `${done}. Jev nu a mai fost întrebat, fiindcă nu a răspuns la un client de dinainte.` : `${done} · doar după reguli`
  }
  return result.jev_calls ? `${done} · Jev: ${countOf(result.jev_calls, 'o întrebare', 'întrebări')}, ${formatUsd(result.jev_cost_usd)}` : done
}
