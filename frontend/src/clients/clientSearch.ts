import { countOf } from '../format'
import { searchWords, wordsFound } from '../textSearch'
import type { Client } from '../types'

/**
 * The clients found by what was typed, in their order: every word has to be in the name or in the CUI.
 * Nothing typed finds everyone.
 */
export function searchClients<T extends Pick<Client, 'name' | 'cui'>>(clients: T[], typed: string): T[] {
  const words = searchWords(typed)
  if (words.length === 0) return clients
  return clients.filter((client) => wordsFound(words, [client.name], [client.cui]))
}

const romanian = new Intl.Collator('ro', { sensitivity: 'base' })

/**
 * The clients by name as Romanian is ordered: the database sorts letter codes, which puts a name
 * starting with Ș, Ț, Ă or Î after Z, on the last page. A new list; the one given is left as it was.
 */
export function byName<T extends Pick<Client, 'name' | 'cui'>>(clients: T[]): T[] {
  return [...clients].sort((one, other) => romanian.compare(one.name, other.name) || one.cui.localeCompare(other.cui))
}

/** Under the search field: how many of the clients are seen; null while all of them are. */
export function shownLine(shown: number, all: number): string | null {
  if (shown === all) return null
  return `${shown === 1 ? 'Se vede' : 'Se văd'} ${countOf(shown, 'un client', 'clienți')} din ${all}.`
}
