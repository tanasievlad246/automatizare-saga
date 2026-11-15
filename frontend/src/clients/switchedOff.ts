import { countOf } from '../format'
import type { Client } from '../types'

/** The clients whose invoices are downloaded: the ones that are switched on, in their order. */
export const switchedOn = (clients: Client[]): Client[] => clients.filter((client) => client.enabled)

/** What the first screen says about the clients that are off; null while every client is on. */
export function switchedOffLine(on: number, off: number): string | null {
  if (off === 0) return null
  if (on === 0) return 'Toți clienții sunt opriți. Porniți cel puțin unul ca să descărcați facturi.'
  const whoIsOff = off === 1 ? 'Un client este oprit.' : `${countOf(off, 'un client', 'clienți')} sunt opriți.`
  return `Se descarcă ${on} din cei ${countOf(on + off, 'un client', 'clienți')}. ${whoIsOff}`
}
