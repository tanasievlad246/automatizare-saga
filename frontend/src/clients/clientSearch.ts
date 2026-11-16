import { countOf } from '../format'
import type { Client } from '../types'

/**
 * A text as it is compared: lower case, without diacritics (the old cedilla letters too) and without dots or
 * other signs, so "brutaria" finds "Brutăria" and "srl" finds "S.R.L.".
 */
function plain(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, '')
    .replace(/\s+/g, ' ')
    .trim()
}

/** A CUI as it is compared: its digits, whether it is written with "RO" or not. */
const digitsOf = (cui: string) => plain(cui).replace(/^ro\s*(?=\d)/, '')

/**
 * The clients found by what was typed, in their order: every word has to be in the name or in the CUI.
 * Nothing typed finds everyone.
 */
export function searchClients<T extends Pick<Client, 'name' | 'cui'>>(clients: T[], typed: string): T[] {
  // "RO 12345674" is one CUI, not the word "ro" and a number.
  const words = plain(typed).replace(/\bro (?=\d)/g, 'ro').split(' ').filter(Boolean)
  if (words.length === 0) return clients
  return clients.filter((client) => {
    const name = plain(client.name)
    const cui = digitsOf(client.cui)
    return words.every((word) => name.includes(word) || cui.includes(digitsOf(word)))
  })
}

/** Under the search field: how many of the clients are seen; null while all of them are. */
export function shownLine(shown: number, all: number): string | null {
  if (shown === all) return null
  return `${shown === 1 ? 'Se vede' : 'Se văd'} ${countOf(shown, 'un client', 'clienți')} din ${all}.`
}
