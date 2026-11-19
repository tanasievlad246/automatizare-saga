// The words of "Hotărăște din nou…" (an invoice or one of its lines decided again), of
// "Împarte pe linii", and of an invoice imported in SAGA whose account has to change.

import { countOf } from '../format'
import type { TrialAsk } from '../types'

export const DECIDE_AGAIN = {
  open: 'Hotărăște din nou…',
  title: 'Hotărăște din nou contul facturii',
  question: 'Cum se hotărăște?',
  happens: 'Ce se întâmplă',
  button: 'Hotărăște din nou',
  busy: 'Se hotărăște…',
  done: 'Contul a fost hotărât din nou.',
}

/** The two ways, each with a line on what it does. Jev is asked about each line, or about the invoice. */
export function decideAgainChoices(perLine: boolean): { value: TrialAsk; label: string; help: string }[] {
  return [
    {
      value: 'rules_then_jev',
      label: 'Cu regulile, apoi Jev',
      help: 'Ca la o descărcare: întâi regulile dumneavoastră; Jev este întrebat doar despre ce nu hotărăște nicio regulă.',
    },
    {
      value: 'jev_only',
      label: 'Doar cu Jev',
      help: perLine
        ? 'Regulile sunt sărite: Jev este întrebat despre fiecare linie, chiar și unde o regulă se potrivește. Așa vedeți ce ar alege Jev singur.'
        : 'Regulile sunt sărite: Jev este întrebat despre factură, chiar dacă o regulă se potrivește. Așa vedeți ce ar alege Jev singur.',
    },
  ]
}

/** "Ce se întâmplă": from the start, the shape kept, and what is left for a person. */
export function decideAgainPoints({ perLine, lines }: { perLine: boolean; lines: number }): string[] {
  const shape = perLine
    ? 'Factura este pe linii și rămâne pe linii: fiecare linie primește contul ei.'
    : lines > 1
      ? 'Factura are un singur cont și rămâne așa: contul se alege după linia cea mai mare. Ca liniile să primească conturi diferite, folosiți întâi „Împarte pe linii”.'
      : null
  return [
    perLine
      ? 'Factura se hotărăște de la început. Contul de acum și conturile pe care le-ați ales pe linii se hotărăsc și ele din nou.'
      : 'Factura se hotărăște de la început. Contul de acum se hotărăște și el din nou.',
    ...(shape ? [shape] : []),
    'Ce nu poate hotărî nimeni vine la verificat. Fiecare întrebare pentru Jev costă puțin.',
  ]
}

/** Why "Doar cu Jev" is off. */
export const NO_JEV = 'Jev nu este pornit. Puneți cheia OpenRouter la „Chei și parole”.'

/** In the window of one line. */
export const LINE_AGAIN = {
  heading: 'Sau hotărăște din nou această linie',
  rules: 'Cu regulile, apoi Jev',
  jev: 'Doar cu Jev',
  note: '„Cu regulile, apoi Jev” face ce face o descărcare. „Doar cu Jev” sare peste reguli. Fiecare întrebare pentru Jev costă puțin.',
  done: (line: number) => `Linia ${line} a fost hotărâtă din nou. Ce s-a ales se vede și la „Cum s-a ales contul”.`,
}

/** For the largest line: the lines that take its account and so change with it. */
export function followersNote(followers: number[]): string | null {
  if (followers.length === 0) return null
  const which = followers.length === 1 ? `Linia ${followers[0]} ia` : `Liniile ${numbers(followers)} iau`
  return `Este linia cea mai mare. ${which} contul ei, așa că se schimbă odată cu ea.`
}

/** "4", "4 și 5", "2, 4 și 5". */
function numbers(list: number[]): string {
  return list.length < 2 ? list.join('') : `${list.slice(0, -1).join(', ')} și ${list.at(-1)}`
}

export const SPLIT = {
  button: 'Împarte pe linii',
  done: 'Factura este acum pe linii. Alegeți sau hotărâți din nou contul fiecărei linii, cu „Schimbă”.',
}

/** Beside "Împarte pe linii": what it does, for an invoice of `lines` lines on `cont`. */
export function splitNote(lines: number, cont: string): string {
  const all = lines === 2 ? 'Ambele linii sunt' : `Toate cele ${countOf(lines, '', 'linii')} sunt`
  return `${all} pe contul ${cont}. Ca să le dați conturi diferite, împărțiți factura pe linii: fiecare pornește cu ${cont}, apoi o schimbați sau o hotărâți din nou.`
}

/** An invoice imported in SAGA keeps its account here; how to change it all the same. */
export function importedSteps(perLine: boolean): { intro: string; steps: string[] } {
  return {
    intro: perLine
      ? 'Factura este deja în SAGA, cu aceste conturi. Dacă trebuie schimbate:'
      : 'Factura este deja în SAGA, cu acest cont. Dacă trebuie schimbat:',
    steps: [
      'ștergeți factura din SAGA;',
      'scoateți bifa „Am importat factura în SAGA”, mai jos;',
      perLine ? 'alegeți conturile noi;' : 'alegeți contul nou;',
      'importați factura din nou în SAGA.',
    ],
  }
}
