import { countOf } from '../format'
import type { Client } from '../types'

/** The clients whose invoices are downloaded: the ones that are switched on, in their order. */
export const switchedOn = (clients: Client[]): Client[] => clients.filter((client) => client.enabled)

/** What the schedule's screen says about the clients that are off; null while every client is on. */
export function switchedOffLine(on: number, off: number): string | null {
  if (off === 0) return null
  if (on === 0) return 'Toți clienții sunt opriți. Porniți cel puțin unul ca să descărcați facturi.'
  const whoIsOff = off === 1 ? 'Un client este oprit.' : `${countOf(off, 'un client', 'clienți')} sunt opriți.`
  return `Se descarcă ${on} din cei ${countOf(on + off, 'un client', 'clienți')}. ${whoIsOff}`
}

/** How the whole list stands: every client on, none of them, or some. */
export type AllSwitch = 'all' | 'some' | 'none'

/** What the check in the list's header shows: a tick, a dash or nothing. */
export function allSwitch(on: number, off: number): AllSwitch {
  if (off === 0) return 'all'
  return on === 0 ? 'none' : 'some'
}

/** Beside "Toți clienții" in the header: how many are on and off, and why nothing downloads when none is. */
export function headerLine(on: number, off: number): string {
  const all = on + off
  if (off === 0) return all === 1 ? 'Singurul client este pornit' : `Toți cei ${all} sunt porniți`
  if (on === 0) {
    return all === 1
      ? 'Singurul client este oprit. Porniți-l ca să descărcați facturi.'
      : `Toți cei ${all} sunt opriți. Porniți cel puțin unul ca să descărcați facturi.`
  }
  return `${on} ${on === 1 ? 'pornit' : 'porniți'} · ${off} ${off === 1 ? 'oprit' : 'opriți'}`
}

/**
 * In the header while some clients are off: why they are not where their name would put them.
 * Said of the opening of the list: a client switched since is still in its place.
 */
export const ON_FIRST = 'Când deschideți lista, clienții porniți sunt primii.'

/** "toți cei 5 clienți", "toți cei 25 de clienți". */
const everyOne = (count: number) => `toți cei ${countOf(count, '', 'clienți')}`

/**
 * The window that asks before every client is switched: one press changes them all and cannot
 * be taken back in one step. `someHidden`: a search shows only a part of the list.
 */
export function switchAllQuestion(
  turnOn: boolean, on: number, off: number, someHidden: boolean,
): { title: string; lines: string[]; note: string | null; confirm: string } {
  const all = on + off
  const hidden = someHidden ? ['Se schimbă toți clienții, și cei care nu se văd acum în listă.'] : []
  if (!turnOn) {
    return {
      title: 'Opriți toți clienții?',
      lines: [
        all === 1 ? 'Se oprește singurul client.' : `Se opresc ${everyOne(all)}.`,
        'După oprire, programul nu mai descarcă facturi de la ANAF pentru niciun client, nici la descărcarea automată, până îi porniți din nou.',
        ...hidden,
      ],
      note: 'Facturile descărcate până acum rămân, cu conturile lor și cu fișierele pentru SAGA.',
      confirm: 'Da, oprește-i pe toți',
    }
  }
  const who = all === 1
    ? 'Se pornește singurul client.'
    : on === 0
      ? `Se pornesc ${everyOne(all)}.`
      : off === 1
        ? 'Se pornește clientul oprit.'
        : `Se pornesc cei ${countOf(off, '', 'clienți')} opriți.`
  const whose = off === 1 ? 'lui' : 'lor' // one client switched on, or several
  return {
    title: 'Porniți toți clienții?',
    lines: [
      who,
      on === 0
        ? `De acum, facturile ${whose} se descarcă, și la descărcarea automată.`
        : `De acum, facturile ${whose} se descarcă împreună cu ale celorlalți, și la descărcarea automată.`,
      ...hidden,
    ],
    note: null,
    confirm: 'Da, pornește-i pe toți',
  }
}

/** After every client was switched: how they all stand now. */
export function switchedAllToast(enabled: boolean, all: number): string {
  if (all === 1) return enabled ? 'Clientul este pornit.' : 'Clientul este oprit.'
  const said = everyOne(all)
  return `${said.charAt(0).toUpperCase()}${said.slice(1)} sunt ${enabled ? 'porniți' : 'opriți'}.`
}
