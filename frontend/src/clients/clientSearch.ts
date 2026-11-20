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

/** Who is on and who is off, by CUI: taken when the list is opened, for the order it keeps. */
export function whoIsOn(clients: Pick<Client, 'cui' | 'enabled'>[]): Map<string, boolean> {
  return new Map(clients.map((client) => [client.cui, client.enabled]))
}

/**
 * The clients that are on first, then those that are off, each group in the order given. A new
 * list. `atOpen`: how each stood when the list was opened (whoIsOn). A client switched since
 * stays where it was, so its row does not jump away at the press and can be switched back; it
 * moves the next time the list is opened. One added since, and all of them while `atOpen` is
 * not known yet, go by how they stand now.
 */
export function onFirst<T extends Pick<Client, 'cui' | 'enabled'>>(clients: T[], atOpen: ReadonlyMap<string, boolean> | null): T[] {
  const wasOn = (client: T) => atOpen?.get(client.cui) ?? client.enabled
  return [...clients.filter(wasOn), ...clients.filter((client) => !wasOn(client))]
}

/** Under the search field: how many of the clients are seen; null while all of them are. */
export function shownLine(shown: number, all: number): string | null {
  if (shown === all) return null
  return `${shown === 1 ? 'Se vede' : 'Se văd'} ${countOf(shown, 'un client', 'clienți')} din ${all}.`
}
